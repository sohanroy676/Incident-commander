"""Runs the graded Commander on a background thread and keeps the finished trace for replay.

The hub never edits a decision: it builds a world, picks a responder, calls `Commander.run`, and
reports what the case holds. DECISION lines come from `report.case_decision_lines`, the same
function the CLI and the scenarios use.
"""

from __future__ import annotations

import dataclasses
import math
import secrets
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping

from ic_plus.clientcfg import client_from_env
from ic_plus.explainer import FALLBACK_LABEL, explain, template_answer
from ic_plus.llm_client import LLMClient
from ic_plus.narrator import build_facts
from ic_plus.x3 import advised_orders, advised_orders_of, run_x3
from incident_commander.approval import ScriptedResponder
from incident_commander.commander import Case, Commander, IllegalTransition
from incident_commander.config import (
    APPROVAL_DEADLINE_S,
    DEMO_SECONDARY_DELAY_S,
    SECONDARY_ONCALL,
)
from incident_commander.evaluate import (
    attack_differential,
    golden_world,
    naive_baseline,
    run_golden,
)
from incident_commander.fixtures.alerts import ALERTS
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.postmortem import OutboxNotifier, render
from incident_commander.report import case_decision_lines
from incident_commander.retrieval import HybridRanker
from incident_commander.types import TraceEvent
from incident_commander.world import SimWorld

from .charts import build_chart, diff_runs
from .responder import WebResponder
from .schema import (
    BUILTIN_ALERTS,
    BUILTIN_SERVICES,
    MAX_UPLOADS,
    Upload,
    ValidationError,
    validate_upload,
)
from .world import HubWorld

MAX_CONCURRENT_RUNS = 2
MAX_STORED_RUNS = 50
WEB_DEFAULT_DEADLINE_S = 20.0
STALE_DEPLOYMENTS_LAG_S = 900.0  # same lag as the ic_plus stale_data scenario


ClientFactory = Callable[[str], tuple[LLMClient | None, list[str]]]
# x3 swaps a function in the graded commander module for one run; one swap at a time.
_X3_LOCK = threading.Lock()


class TooManyRuns(Exception):
    """The concurrent-run cap is reached."""


class NotFound(Exception):
    """No such run or alert."""


class Conflict(Exception):
    """The run is not in a state that allows this."""


def jsonable(value: object) -> object:
    """Trace fields to JSON values; anything unusual becomes its text."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return str(value)


def event_json(event: TraceEvent) -> dict[str, object]:
    return {
        "seq": event.seq,
        "kind": event.kind,
        "data_time": event.data_time,
        "elapsed_s": round(event.elapsed_s, 3),
        "fields": {k: jsonable(v) for k, v in event.fields},
    }


class Run:
    def __init__(self, run_id: str, kind: str, alert_id: str, mode: str) -> None:
        self.run_id = run_id
        self.kind = kind  # "run" | "playground"
        self.alert_id = alert_id
        self.mode = mode
        self.status = "running"  # running | done | error
        self.error: str | None = None
        self.responder: WebResponder | None = None
        self.result: dict[str, object] | None = None
        self.case: Case | None = None
        self.commander: Commander | None = None

    def view(self) -> dict[str, object]:
        pending = self.responder.pending() if self.responder and self.status == "running" else None
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "alert_id": self.alert_id,
            "mode": self.mode,
            "status": self.status,
            "pending": pending,
            "error": self.error,
            "result": self.result,
        }


class Hub:
    """Uploads, runs and their limits. One instance per server."""

    def __init__(self, client_factory: ClientFactory = client_from_env) -> None:
        self._client_factory = client_factory
        self._lock = threading.Lock()
        self._uploads: list[Upload] = []
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._active = 0

    # -- uploads and alerts -------------------------------------------------

    def add_upload(self, raw: object) -> Upload:
        with self._lock:
            if len(self._uploads) >= MAX_UPLOADS:
                raise ValidationError({"upload": f"at most {MAX_UPLOADS} uploads"})
            services = BUILTIN_SERVICES | {u.service.name for u in self._uploads}
            alerts = BUILTIN_ALERTS | {u.alert.alert_id for u in self._uploads}
            upload = validate_upload(raw, services, alerts)
            self._uploads.append(upload)
            return upload

    def uploads(self) -> tuple[Upload, ...]:
        with self._lock:
            return tuple(self._uploads)

    def alert_rows(self) -> list[dict[str, object]]:
        world = HubWorld(self.uploads())
        uploaded = {u.alert.alert_id for u in self.uploads()}
        rows = []
        for alert_id in world.alert_ids():
            a = world.alert(alert_id)
            if alert_id in uploaded:
                source = "upload"
            elif alert_id in ALERTS:
                source = "demo"
            else:
                source = "golden"
            rows.append(
                {
                    "alert_id": a.alert_id,
                    "service": a.service,
                    "severity": a.severity,
                    "metric": a.metric,
                    "summary": a.summary,
                    "fired_at": a.fired_at,
                    "source": source,
                }
            )
        return rows

    def known_alerts(self) -> frozenset[str]:
        return frozenset(HubWorld(self.uploads()).alert_ids())

    def has_service(self, name: str) -> bool:
        return HubWorld(self.uploads()).has_service(name)

    # -- runs ---------------------------------------------------------------

    def start(self, req: Mapping[str, object], *, playground: bool = False) -> Run:
        mode = "scripted" if playground else str(req["mode"])
        run = Run(
            secrets.token_hex(8), "playground" if playground else "run", str(req["alert_id"]), mode
        )
        uploads = self.uploads()
        self._admit(run)
        requested = req.get("deadline_s")
        if isinstance(requested, (int, float)):
            deadline = float(requested)
        else:
            deadline = WEB_DEFAULT_DEADLINE_S if mode == "web" else APPROVAL_DEADLINE_S
        if mode == "web" and not playground:
            run.responder = WebResponder(deadline)
        thread = threading.Thread(
            target=self._execute, args=(run, uploads, req, deadline), daemon=True
        )
        thread.start()
        return run

    def _admit(self, run: Run) -> None:
        """Count the run against the concurrency cap and store it, dropping the oldest finished."""
        with self._lock:
            if self._active >= MAX_CONCURRENT_RUNS:
                raise TooManyRuns("too many runs in progress")
            if run.kind == "evaluate" and any(
                r.kind == "evaluate" and r.status == "running" for r in self._runs.values()
            ):
                raise Conflict("an evaluation is already running")
            self._active += 1
            self._runs[run.run_id] = run
            while len(self._runs) > MAX_STORED_RUNS:
                oldest = next((k for k, r in self._runs.items() if r.status != "running"), None)
                if oldest is None:
                    break
                del self._runs[oldest]

    def start_explain(self, req: Mapping[str, object]) -> Run:
        uploads = self.uploads()
        run = Run(secrets.token_hex(8), "explain", str(req["alert_id"]), str(req["llm"]))
        self._admit(run)
        self._launch(run, lambda: self._explain(run, uploads, req))
        return run

    def start_evaluate(self, req: Mapping[str, object]) -> Run:
        run = Run(secrets.token_hex(8), "evaluate", "", str(req["llm"]))
        self._admit(run)
        self._launch(run, lambda: self._evaluate(run))
        return run

    def _launch(self, run: Run, work: Callable[[], dict[str, object]]) -> None:
        def job() -> None:
            try:
                run.result = work()
                run.status = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the page, never silently dropped
                run.error = f"{type(exc).__name__}: {exc}"
                run.status = "error"
            finally:
                with self._lock:
                    self._active -= 1

        threading.Thread(target=job, daemon=True).start()

    def get(self, run_id: str) -> Run:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise NotFound("no such run")
        return run

    def _commander(self, world: SimWorld, run: Run, mode: str, deadline_s: float) -> Commander:
        if mode == "web":
            responder: object = run.responder
        elif mode == "silent":
            responder = ScriptedResponder({})
        else:  # the graded wiring: priya never answers, devon approves after paging
            responder = ScriptedResponder({SECONDARY_ONCALL: (DEMO_SECONDARY_DELAY_S, "approve")})
        ranker = HybridRanker(tuple(RUNBOOKS.values()))
        return Commander(world, ranker, responder, deadline_s=deadline_s)  # type: ignore[arg-type]

    def _execute(
        self, run: Run, uploads: tuple[Upload, ...], req: Mapping[str, object], deadline_s: float
    ) -> None:
        try:
            if run.kind == "playground":
                run.result = self._playground(run, uploads, req, deadline_s)
            else:
                planted = req.get("planted_logs")
                what_if = req.get("what_if") or ()
                alert = HubWorld(uploads).alert(run.alert_id)
                world = HubWorld(
                    uploads,
                    planted if isinstance(planted, dict) and planted else None,
                    tool_lags={"get_deployments": STALE_DEPLOYMENTS_LAG_S}
                    if "stale_deployments" in what_if  # type: ignore[operator]
                    else None,
                    broken_error_rate=alert.service
                    if "tool_failure" in what_if  # type: ignore[operator]
                    else None,
                )
                commander = self._commander(world, run, run.mode, deadline_s)
                case = commander.run(world.alert(run.alert_id), fix_outcome=str(req["fix_outcome"]))
                run.case, run.commander = case, commander
                run.result = {**self._summary(case), "chart": build_chart(world, case)}
            run.status = "done"
        except Exception as exc:  # noqa: BLE001 - reported to the page, never silently dropped
            run.error = f"{type(exc).__name__}: {exc}"
            run.status = "error"
        finally:
            if run.responder is not None:
                run.responder.close()
            with self._lock:
                self._active -= 1

    def _explain(
        self, run: Run, uploads: tuple[Upload, ...], req: Mapping[str, object]
    ) -> dict[str, object]:
        """Run the alert on the graded wiring, then answer the question about the finished case."""
        mode = str(req["llm"])
        world = HubWorld(uploads)
        case = self._commander(world, run, "scripted", APPROVAL_DEADLINE_S).run(
            world.alert(run.alert_id)
        )
        if mode == "off":
            answer = template_answer(build_facts(case))
            return {
                "status": "off",
                "lines": [f"{FALLBACK_LABEL} {answer}"],
                "answer": answer,
                "remote": False,
                "configured": True,
                "missing": [],
            }
        client, missing = self._client_factory(mode)
        outcome = explain(case, str(req["question"]), client)
        return {
            "status": outcome.status,
            "lines": list(outcome.lines),
            "answer": outcome.answer,
            "remote": mode == "hosted" and client is not None,
            "configured": client is not None,
            "missing": missing,
        }

    def _evaluate(self, run: Run) -> dict[str, object]:
        """The graded golden set, attack and naive baseline, then x3 (all LLM roles) on top."""
        mode = run.mode

        def factory(world: SimWorld) -> Commander:
            return self._commander(world, run, "scripted", APPROVAL_DEADLINE_S)

        golden = run_golden(factory)
        attack = attack_differential(factory)
        world = golden_world()
        ranker = HybridRanker(tuple(RUNBOOKS.values()))
        naive = naive_baseline(ranker, (world.alert(a) for a in world.alert_ids()))
        client, missing = (None, []) if mode == "off" else self._client_factory(mode)
        with _X3_LOCK:
            rows = run_x3(client)
            with advised_orders(advised_orders_of(rows)):
                golden_advised = run_golden(factory)
                attack_advised = attack_differential(factory)
        changed = sum(not row.identical for row in rows)
        changed += int(golden_advised != golden or attack_advised != attack)
        return {
            "llm": mode,
            "configured": mode == "off" or client is not None,
            "missing": missing,
            "remote": mode == "hosted" and client is not None,
            "golden": [dataclasses.asdict(g) for g in golden],
            "golden_passed": sum(g.passed for g in golden),
            "attack": {**dataclasses.asdict(attack), "unchanged": attack.unchanged},
            "naive": [dataclasses.asdict(n) for n in naive],
            "naive_wrong": sum(not n.correct for n in naive),
            "x3": [{**dataclasses.asdict(r), "order": list(r.order)} for r in rows],
            "decisions_changed": changed,
        }

    def _playground(
        self, run: Run, uploads: tuple[Upload, ...], req: Mapping[str, object], deadline_s: float
    ) -> dict[str, object]:
        """Same alert twice, the second with a planted log line: the DECISION lines must match."""
        alert_id = str(req["alert_id"])
        text = str(req["text"] or "")
        service = HubWorld(uploads).alert(alert_id).service
        lines = {}
        for label, planted in (("clean", None), ("planted", {service: (text,)})):
            world = HubWorld(uploads, planted)
            commander = self._commander(world, run, "scripted", deadline_s)
            case = commander.run(world.alert(alert_id), fix_outcome=str(req["fix_outcome"]))
            lines[label] = list(case_decision_lines(case))
        return {
            "planted_service": service,
            "planted_text": text,
            "clean_lines": lines["clean"],
            "planted_lines": lines["planted"],
            "unchanged": lines["clean"] == lines["planted"],
        }

    @staticmethod
    def _summary(case: Case) -> dict[str, object]:
        draft = case.draft
        return {
            "state": case.state,
            "handoff_reason": case.handoff_reason,
            "decision_lines": list(case_decision_lines(case)),
            "trace": [event_json(e) for e in case.trace.events],
            "postmortem": render(draft) if draft else None,
            "published": bool(draft and draft.published),
        }

    def approve(self, run_id: str, nonce: object, decision: object) -> str:
        run = self.get(run_id)
        if run.responder is None or run.status != "running":
            raise Conflict("this run is not waiting for a web approval")
        return run.responder.submit(nonce, decision)

    def publish(self, run_id: str) -> dict[str, object]:
        """The explicit, human-triggered side effect. The notifier is the in-memory outbox."""
        run = self.get(run_id)
        if run.case is None or run.commander is None or run.status != "done":
            raise Conflict("this run has no finished draft to publish")
        with self._lock:
            try:
                run.commander.publish(run.case, OutboxNotifier())
            except IllegalTransition as exc:
                raise Conflict(f"already published or not publishable: {exc}") from None
            run.result = {**self._summary(run.case), "chart": (run.result or {}).get("chart")}
        return run.result

    def diff(self, a_id: str, b_id: str) -> dict[str, object]:
        """Compare two finished runs (not playgrounds)."""
        results = []
        for run_id in (a_id, b_id):
            run = self.get(run_id)
            if run.kind != "run" or run.status != "done" or run.result is None:
                raise Conflict(f"run {run_id} is not a finished incident run")
            results.append(run.result)
        return diff_runs(results[0], results[1])

    def postmortem(self, run_id: str) -> object:
        run = self.get(run_id)
        if run.case is None or run.case.draft is None:
            raise Conflict("this run has no postmortem draft")
        return run.case.draft

    @staticmethod
    def postmortem_json(draft: object) -> dict[str, object]:
        return dataclasses.asdict(draft)  # type: ignore[call-overload]
