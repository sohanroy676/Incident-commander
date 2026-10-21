"""Runs the graded Commander on a background thread and keeps the finished trace for replay.

The hub never edits a decision: it builds a world, picks a responder, calls `Commander.run`, and
reports what the case holds. DECISION lines come from `report.case_decision_lines`, the same
function the CLI and the scenarios use.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping

from ic_plus.clientcfg import client_from_env
from ic_plus.explainer import FALLBACK_LABEL, explain, template_answer
from ic_plus.llm_client import LLMClient
from ic_plus.narrator import build_facts
from ic_plus.x3 import advised_orders, advised_orders_of, run_x3
from incident_commander.approval import ScriptedResponder
from incident_commander.blast_radius import classify_remediation
from incident_commander.commander import Case, Commander, IllegalTransition
from incident_commander.config import (
    ACTION_PROPERTIES,
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
from incident_commander.fixtures.golden import GOLDEN_ALERTS, GOLDEN_SERVICES
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.fixtures.services import REMEDIATION_EFFECTS, SERVICES, ServiceSpec
from incident_commander.postmortem import OutboxNotifier, render
from incident_commander.predicates import PREDICATES
from incident_commander.report import case_decision_lines
from incident_commander.retrieval import HybridRanker
from incident_commander.types import Alert, Runbook, TraceEvent
from incident_commander.world import SimWorld

from .charts import build_chart, diff_runs
from .responder import WebResponder
from .schema import (
    BUILTIN_ALERTS,
    BUILTIN_SERVICES,
    INTAKE_SEVERITY,
    MAX_INTAKE,
    MAX_UPLOADS,
    PREDICATE_HELP,
    Upload,
    ValidationError,
    validate_alertmanager,
    validate_runbooks,
    validate_upload,
)
from .store import Store
from .world import HubWorld

MAX_CONCURRENT_RUNS = 2
MAX_STORED_RUNS = 50
MAX_RUNBOOK_SETS = 5
MAX_RUN_EVENTS = 500  # live trace events kept per run; a run emits about 25
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
        self.started = time.monotonic()
        self.ended: float | None = None
        self.runbooks: tuple[Runbook, ...] | None = None  # None: the built-in corpus
        self._events: list[dict[str, object]] = []
        self._events_lock = threading.Lock()

    def runbook_map(self) -> dict[str, Runbook] | None:
        return None if self.runbooks is None else {r.runbook_id: r for r in self.runbooks}

    def add_event(self, event: TraceEvent) -> None:
        """The Commander's on_event observer: runs on the run thread, only appends a copy."""
        with self._events_lock:
            if len(self._events) < MAX_RUN_EVENTS:
                self._events.append(event_json(event))

    def events_after(self, seq: int) -> list[dict[str, object]]:
        """Live events with a sequence number above `seq`, oldest first (a snapshot copy)."""
        with self._events_lock:
            return [e for e in self._events if int(e["seq"]) > seq]  # type: ignore[call-overload]

    def stream_view(self) -> dict[str, object]:
        """The small, changing part of the view: what the approval stream sends."""
        pending = self.responder.pending() if self.responder and self.status == "running" else None
        return {"status": self.status, "pending": pending, "error": self.error}

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

    def __init__(
        self, client_factory: ClientFactory = client_from_env, store: Store | None = None
    ) -> None:
        self._client_factory = client_factory
        self.store = store
        self._lock = threading.Lock()
        self._uploads: list[Upload] = []
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._active = 0
        # alert_id -> display-only Alertmanager text; nothing in it reaches a run
        self._intake: dict[str, dict[str, object]] = {}
        self._counts: dict[str, int] = {"incident_runs_started": 0}
        self._approvals: dict[str, int] = {}
        # set id -> (runbooks, SHA-256 of their canonical JSON); held in memory like uploads
        self._runbook_sets: OrderedDict[str, tuple[tuple[Runbook, ...], str]] = OrderedDict()

    # -- uploads and alerts -------------------------------------------------

    def add_upload(self, raw: object) -> Upload:
        with self._lock:
            if len(self._uploads) - len(self._intake) >= MAX_UPLOADS:
                raise ValidationError({"upload": f"at most {MAX_UPLOADS} uploads"})
            services = BUILTIN_SERVICES | {u.service.name for u in self._uploads}
            alerts = BUILTIN_ALERTS | {u.alert.alert_id for u in self._uploads}
            upload = validate_upload(raw, services, alerts)
            self._uploads.append(upload)
        self._audit("upload_added", alert_id=upload.alert.alert_id, service=upload.service.name)
        return upload

    # -- runbook sets -------------------------------------------------------

    def add_runbooks(self, raw: object) -> dict[str, object]:
        """Validate a runbook set and keep it (the oldest of MAX_RUNBOOK_SETS is dropped)."""
        books = validate_runbooks(raw)
        digest = hashlib.sha256(
            json.dumps([dataclasses.asdict(b) for b in books], sort_keys=True).encode()
        ).hexdigest()
        with self._lock:
            effect_actions = {action for _, action in REMEDIATION_EFFECTS}
            effect_actions |= {action for u in self._uploads for action in u.effects}
            set_id = secrets.token_hex(8)
            self._runbook_sets[set_id] = (books, digest)
            while len(self._runbook_sets) > MAX_RUNBOOK_SETS:
                self._runbook_sets.popitem(last=False)
        warnings = [
            f"{b.runbook_id}: no service has a remediation effect for {b.action}, "
            "so verification would reopen the case"
            for b in books
            if b.action not in effect_actions
        ]
        self._audit("runbooks_added", set_id=set_id, sha256=digest, count=len(books))
        return {"set_id": set_id, "sha256": digest, "warnings": warnings}

    def runbook_set(self, set_id: object) -> tuple[tuple[Runbook, ...], str] | None:
        """The stored set for a run request, None for the built-in corpus; unknown ids are an error."""
        if set_id is None:
            return None
        with self._lock:
            found = self._runbook_sets.get(str(set_id))
        if found is None:
            raise ValidationError({"runbook_set": "unknown or expired runbook set"})
        return found

    def add_intake(self, raw: object) -> list[dict[str, str]]:
        """Alertmanager webhook -> alerts on services the hub already holds.

        Labels and annotations are kept as display text beside the alert and are never read by a
        run. A repeated fingerprint on the same service returns the earlier alert id.
        """
        with self._lock:
            drafts = validate_alertmanager(raw, self._reference_alert)
            known = {
                (str(m["fingerprint"]), str(m["service"])): aid
                for aid, m in self._intake.items()
                if m["fingerprint"]
            }
            fresh = [
                d for d in drafts if (d.fingerprint, d.service) not in known or not d.fingerprint
            ]
            if len(self._intake) + len(fresh) > MAX_INTAKE:
                raise ValidationError({"alerts": f"at most {MAX_INTAKE} Alertmanager alerts"})
            accepted = []
            for draft in drafts:
                key = (draft.fingerprint, draft.service)
                if draft.fingerprint and key in known:
                    accepted.append(
                        {"alert_id": known[key], "service": draft.service, "status": "duplicate"}
                    )
                    continue
                ref = self._reference_alert(draft.service)
                if ref is None:  # cannot happen: validated above under the same lock
                    raise ValidationError({"alerts": f"no reference alert for {draft.service}"})
                alert = Alert(
                    "AM-" + secrets.token_hex(4),
                    draft.service,
                    ref.fired_at,  # the service's own incident time: startsAt is wall-clock text
                    INTAKE_SEVERITY,
                    draft.metric,
                    draft.summary,
                )
                self._uploads.append(Upload(self._service_spec(draft.service), alert, {}))
                self._intake[alert.alert_id] = {
                    "service": draft.service,
                    "fingerprint": draft.fingerprint,
                    "labels": dict(draft.labels),
                    "annotations": dict(draft.annotations),
                    "starts_at": draft.starts_at,
                }
                known[key] = alert.alert_id
                accepted.append(
                    {"alert_id": alert.alert_id, "service": draft.service, "status": "added"}
                )
        added = [a["alert_id"] for a in accepted if a["status"] == "added"]
        if added:
            self._audit("alertmanager_intake", count=len(added), alert_ids=",".join(added))
        return accepted

    def _reference_alert(self, service: str) -> Alert | None:
        """An existing, non-intake alert on this service (caller holds the lock)."""
        pool = [*ALERTS.values(), *GOLDEN_ALERTS.values()]
        pool += [u.alert for u in self._uploads if u.alert.alert_id not in self._intake]
        return next((a for a in pool if a.service == service), None)

    def _service_spec(self, name: str) -> ServiceSpec:
        spec = SERVICES.get(name) or GOLDEN_SERVICES.get(name)
        if spec is not None:
            return spec
        return next(u.service for u in self._uploads if u.service.name == name)

    def uploads(self) -> tuple[Upload, ...]:
        with self._lock:
            return tuple(self._uploads)

    def alert_rows(self) -> list[dict[str, object]]:
        world = HubWorld(self.uploads())
        uploaded = {u.alert.alert_id for u in self.uploads()}
        with self._lock:
            intake = {k: dict(v) for k, v in self._intake.items()}
        rows = []
        for alert_id in world.alert_ids():
            a = world.alert(alert_id)
            if alert_id in intake:
                source = "intake"
            elif alert_id in uploaded:
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
            if alert_id in intake:
                rows[-1]["labels"] = intake[alert_id]["labels"]
                rows[-1]["annotations"] = intake[alert_id]["annotations"]
                rows[-1]["starts_at"] = intake[alert_id]["starts_at"]
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
        chosen = self.runbook_set(req.get("runbook_set"))
        run.runbooks = chosen[0] if chosen else None
        self._admit(run)
        requested = req.get("deadline_s")
        if isinstance(requested, (int, float)):
            deadline = float(requested)
        else:
            deadline = WEB_DEFAULT_DEADLINE_S if mode == "web" else APPROVAL_DEADLINE_S
        if mode == "web" and not playground:
            run.responder = WebResponder(deadline)
        if not playground:
            self._audit(
                "run_started",
                run_id=run.run_id,
                alert_id=run.alert_id,
                mode=mode,
                fix_outcome=req["fix_outcome"],
                what_if=",".join(str(x) for x in req.get("what_if") or ()),  # type: ignore[attr-defined]
                runbooks=chosen[1] if chosen else "builtin",
            )
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
            if run.kind == "run":
                self._counts["incident_runs_started"] += 1
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
                self._audit_job(run)
                run.status = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the page, never silently dropped
                run.error = f"{type(exc).__name__}: {exc}"
                run.status = "error"
            finally:
                run.ended = time.monotonic()
                with self._lock:
                    self._active -= 1

        threading.Thread(target=job, daemon=True).start()

    def metrics(self) -> dict[str, object]:
        """Counters only: no label, log or other free text. Outcome names are fixed vocabularies."""
        with self._lock:
            runs = [r for r in self._runs.values() if r.kind == "run"]
            states: dict[str, int] = {}
            seconds = []
            for r in runs:
                if r.status == "done" and r.result is not None:
                    state = str(r.result.get("state"))
                    states[state] = states.get(state, 0) + 1
                if r.status == "done" and r.ended is not None:
                    seconds.append(r.ended - r.started)
            return {
                "runs_started": self._counts["incident_runs_started"],
                "runs_running": sum(r.status == "running" for r in runs),
                "runs_done": sum(r.status == "done" for r in runs),
                "runs_failed": sum(r.status == "error" for r in runs),
                "states": states,
                "approvals": dict(self._approvals),
                "mean_run_s": round(sum(seconds) / len(seconds), 3) if seconds else None,
                "intake_alerts": len(self._intake),
                "uploads": len(self._uploads) - len(self._intake),
                "scope": f"state and timing cover the last {MAX_STORED_RUNS} stored runs",
            }

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
        ranker = HybridRanker(run.runbooks or tuple(RUNBOOKS.values()))
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
                case = commander.run(
                    world.alert(run.alert_id),
                    fix_outcome=str(req["fix_outcome"]),
                    runbooks=run.runbook_map(),
                    on_event=run.add_event,
                )
                run.case, run.commander = case, commander
                run.result = {**self._summary(case), "chart": build_chart(world, case)}
                self._persist(run, req)
            run.status = "done"
        except Exception as exc:  # noqa: BLE001 - reported to the page, never silently dropped
            run.error = f"{type(exc).__name__}: {exc}"
            run.status = "error"
        finally:
            if run.responder is not None:
                run.responder.close()
            run.ended = time.monotonic()
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
            case = commander.run(
                world.alert(alert_id),
                fix_outcome=str(req["fix_outcome"]),
                runbooks=run.runbook_map(),
            )
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
        pending = run.responder.pending()
        outcome = run.responder.submit(nonce, decision)
        with self._lock:
            self._approvals[outcome] = self._approvals.get(outcome, 0) + 1
        self._audit(
            "approval_answer",
            run_id=run_id,
            target=pending["target"] if pending else "",
            decision=decision if decision in ("approve", "deny") else "invalid",
            outcome=outcome,
        )
        return outcome

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
        self._persist(run, None)
        self._audit("published", run_id=run_id, alert_id=run.alert_id)
        return run.result

    # -- history and audit (only when the server was started with a data directory) --------

    def _audit(self, event: str, **detail: object) -> None:
        if self.store is not None:
            self.store.append(event, **detail)

    def _persist(self, run: Run, req: Mapping[str, object] | None) -> None:
        """Store the finished run and note it in the audit log. Never fails the run."""
        if self.store is None or run.case is None or run.result is None:
            return
        case = run.case
        verdict = case.investigation.verdict if case.investigation else None
        saved = self.store.save_run(
            {
                "run_id": run.run_id,
                "alert_id": run.alert_id,
                "service": case.alert.service,
                "runbook": verdict.runbook_id if verdict else None,
                "mode": run.mode,
                "state": case.state,
                "published": bool(run.result.get("published")),
                "result": run.result,
            }
        )
        if req is not None:
            self._audit(
                "run_finished",
                run_id=run.run_id,
                alert_id=run.alert_id,
                state=case.state,
                handoff_reason=case.handoff_reason or "",
                stored=saved,
            )

    def _audit_job(self, run: Run) -> None:
        result = run.result or {}
        if run.kind == "explain":
            self._audit(
                "explain_finished",
                run_id=run.run_id,
                alert_id=run.alert_id,
                llm=run.mode,
                status=result.get("status"),
                remote=result.get("remote"),
            )
        elif run.kind == "evaluate":
            self._audit(
                "evaluate_finished",
                run_id=run.run_id,
                llm=run.mode,
                decisions_changed=result.get("decisions_changed"),
                remote=result.get("remote"),
            )

    def history(self) -> dict[str, object]:
        if self.store is None:
            return {"enabled": False, "runs": [], "write_error": None}
        return {
            "enabled": True,
            "runs": self.store.list_runs(),
            "write_error": self.store.last_error,
        }

    def history_get(self, run_id: str) -> dict[str, object]:
        record = self.store.get_run(run_id) if self.store else None
        if record is None:
            raise NotFound("no such stored run")
        return record

    def audit(self) -> dict[str, object]:
        if self.store is None:
            return {"enabled": False, "entries": [], "verify": None}
        return {"enabled": True, "entries": self.store.tail(), "verify": self.store.verify()}

    def similar(self, run_id: str) -> dict[str, object]:
        """Earlier stored runs like this one. Advisory only: nothing here reaches a decision."""
        if self.store is None:
            return {"enabled": False, "runs": []}
        with self._lock:
            live = self._runs.get(run_id)
        if live is not None and live.case is not None:
            case = live.case
            verdict = case.investigation.verdict if case.investigation else None
            service: object = case.alert.service
            runbook: object = verdict.runbook_id if verdict else None
        else:
            record = self.store.get_run(run_id)
            if record is None:
                raise NotFound("no such run")
            service, runbook = record.get("service"), record.get("runbook")
        return {"enabled": True, "runs": self.store.similar(run_id, service, runbook)}

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


def builtin_catalog() -> dict[str, object]:
    """What the runbook editor offers: the built-in corpus, the nine predicates, the four actions."""
    return {
        "runbooks": [
            {
                **dataclasses.asdict(b),
                "signature": list(b.signature),
                "follow_ups": list(b.follow_ups),
            }
            for b in RUNBOOKS.values()
        ],
        "predicates": [
            {"id": p, "tool": PREDICATES[p].tool, "help": PREDICATE_HELP[p]} for p in PREDICATES
        ],
        "actions": [
            {
                "id": a,
                "tier": classify_remediation(a).tier,
                "requires_approval": classify_remediation(a).requires_approval,
            }
            for a in ACTION_PROPERTIES
        ],
    }
