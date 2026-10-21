"""Validation of untrusted hub input: upload JSON -> ServiceSpec + Alert + remediation effects.

Everything here is a pure function of its input. Errors are collected per field so the page can
show them next to the form, and every number is bounded: `SimWorld.latency_points` builds one
point per grid step, so an unbounded time or window would build millions of points.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from incident_commander.config import ACTION_PROPERTIES, SAMPLE_INTERVAL_S
from incident_commander.fixtures.alerts import ALERTS, DAY_S, T0
from incident_commander.fixtures.golden import GOLDEN_ALERTS, GOLDEN_SERVICES
from incident_commander.fixtures.services import (
    REMEDIATION_OUTCOMES,
    SERVICES,
    ServiceSpec,
    flat,
    ramp,
    step,
)
from incident_commander.predicates import PREDICATES
from incident_commander.types import Alert, Runbook

MAX_BODY_BYTES = 1_048_576
MAX_UPLOADS = 20
MAX_DEPLOYMENTS = 10
MAX_DEPENDENCIES = 5
MAX_PLANTED_LINES = 5
MAX_PLANTED_CHARS = 300
MAX_SUMMARY_CHARS = 200
MAX_DEADLINE_S = 60.0
WHAT_IFS = ("stale_deployments", "tool_failure")
LLM_MODES = ("off", "local", "hosted")
MAX_QUESTION_CHARS = 200
TIME_MIN = T0 - 400 * DAY_S
TIME_MAX = T0 + 400 * DAY_S
LEVEL_MAX = 1_000_000.0
SEVERITIES = ("low", "medium", "high", "critical")
METRICS = ("latency_ms", "error_rate")
MAX_INTAKE = 20  # Alertmanager alerts held at once, beside the uploads
MAX_INTAKE_PER_POST = 10
MAX_LABELS = 20
MAX_LABEL_CHARS = 100
MAX_ANNOTATIONS = 10
MAX_RUNBOOKS = 8
MAX_SIGNATURE = 6
MAX_FOLLOW_UPS = 3
MAX_TITLE_CHARS = 80
MAX_RUNBOOK_TEXT_CHARS = 1000
MAX_FOLLOW_UP_CHARS = 200
INTAKE_SEVERITY = "medium"  # fixed: no label sets it, and no decision reads it

_NAME = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_ALERT_ID = re.compile(r"^[A-Za-z0-9-]{1,32}$")
_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_RUNBOOK_ID = re.compile(r"^[A-Za-z0-9-]{1,20}$")
_LINE_BREAKS = re.compile(r"[\r\n\t]")
_SET_ID = re.compile(r"^[0-9a-f]{16}$")

# One line per predicate for the editor's catalog; a test keeps these keys equal to PREDICATES.
PREDICATE_HELP = {
    "latency_elevated": "recent latency is at least 2x its baseline",
    "latency_normal": "recent latency is within 1.25x of its baseline",
    "latency_step_change": "latency jumped in one step and was normal before",
    "latency_gradual_trend": "latency climbs steadily with no single jump",
    "error_normal": "error rate is at most 2x its baseline",
    "error_elevated": "error rate is at least 3x its baseline",
    "deploy_in_window": "a deployment happened in the 30 minutes before the alert",
    "no_deploy_in_window": "no deployment in the 30 minutes before the alert",
    "dependency_unhealthy": "a dependency has elevated latency or errors",
    "error_step_change": "error rate jumped in one step and was normal before",
    "error_gradual_trend": "error rate climbs steadily with no single jump",
    "dependency_healthy": "no dependency has elevated latency or errors",
}

BUILTIN_SERVICES = frozenset({*SERVICES, *GOLDEN_SERVICES})
BUILTIN_ALERTS = frozenset({*ALERTS, *GOLDEN_ALERTS})


class ValidationError(Exception):
    """Field-level problems: {path: message}."""

    def __init__(self, fields: Mapping[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in fields.items()))
        self.fields = dict(fields)


@dataclass(frozen=True)
class Upload:
    service: ServiceSpec
    alert: Alert
    effects: Mapping[str, Mapping[str, float]]  # action -> outcome -> latency ms


def parse_json(body: bytes) -> object:
    """Strict JSON: UTF-8, no duplicate keys, no NaN/Infinity, no pathological nesting."""

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate key: {key}")
            out[key] = value
        return out

    def constant(name: str) -> object:
        raise ValueError(f"non-finite number: {name}")

    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise ValidationError({"body": f"not valid JSON: {exc}"}) from None


class _Collector:
    """Gathers field errors instead of stopping at the first one."""

    def __init__(self) -> None:
        self.errors: dict[str, str] = {}

    def fail(self, path: str, message: str) -> None:
        self.errors.setdefault(path, message)

    def obj(self, path: str, value: object, allowed: tuple[str, ...]) -> dict[str, object]:
        if not isinstance(value, dict):
            self.fail(path, "must be an object")
            return {}
        for key in value:
            if key not in allowed:
                self.fail(f"{path}.{key}", "unknown field")
        return value

    def num(
        self, path: str, value: object, lo: float, hi: float, *, lo_open: bool = False
    ) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            self.fail(path, "must be a finite number")
            return lo
        below = value <= lo if lo_open else value < lo
        if below or value > hi:
            self.fail(path, f"must be {'>' if lo_open else '>='} {lo:g} and <= {hi:g}")
            return lo
        return float(value)

    def text(self, path: str, value: object, pattern: re.Pattern[str], what: str) -> str:
        if not isinstance(value, str) or not pattern.match(value):
            self.fail(path, f"must be {what}")
            return ""
        return value

    def free_text(self, path: str, value: object, limit: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            self.fail(path, f"must be a non-empty string of at most {limit} characters")
            return ""
        if not value.isprintable():
            self.fail(path, "must not contain control characters")
            return ""
        return value


def _series(c: _Collector, path: str, raw: object, lo: float, hi: float, *, lo_open: bool):
    kinds = {
        "flat": ("kind", "level"),
        "step": ("kind", "base", "at", "level"),
        "ramp": ("kind", "base", "start", "end", "level"),
    }
    kind = raw.get("kind") if isinstance(raw, dict) else None
    if kind not in kinds:
        c.fail(path, "must be an object with kind flat, step or ramp")
        return flat(lo)
    spec = c.obj(path, raw, kinds[kind])
    for key in kinds[kind][1:]:
        if key not in spec:
            c.fail(f"{path}.{key}", "is required")

    def level(key: str) -> float:
        return c.num(f"{path}.{key}", spec.get(key), lo, hi, lo_open=lo_open)

    def when(key: str) -> float:
        return c.num(f"{path}.{key}", spec.get(key), TIME_MIN, TIME_MAX)

    if kind == "flat":
        return flat(level("level"))
    if kind == "step":
        return step(level("base"), when("at"), level("level"))
    start, end = when("start"), when("end")
    if end <= start:
        c.fail(f"{path}.end", "must be after start")
        end = start + 1.0
    return ramp(level("base"), start, end, level("level"))


def _grid_time(c: _Collector, path: str, value: object) -> float:
    t = c.num(path, value, TIME_MIN, TIME_MAX)
    if t % SAMPLE_INTERVAL_S != 0:
        c.fail(path, f"must be a multiple of {SAMPLE_INTERVAL_S} seconds")
    return t


def validate_upload(
    raw: object, known_services: frozenset[str], known_alerts: frozenset[str]
) -> Upload:
    """Build an Upload or raise ValidationError. `known_*` are the names already taken."""
    c = _Collector()
    top = c.obj("upload", raw, ("service", "alert"))
    svc_raw = c.obj(
        "service",
        top.get("service"),
        (
            "name",
            "baseline_latency_ms",
            "baseline_error_rate",
            "latency",
            "error_rate",
            "deployments",
            "dependencies",
            "anchor",
            "effects",
        ),
    )
    alert_raw = c.obj(
        "alert", top.get("alert"), ("alert_id", "severity", "metric", "summary", "fired_at")
    )

    name = c.text("service.name", svc_raw.get("name"), _NAME, "lowercase letters, digits, hyphens")
    if name in known_services:
        c.fail("service.name", "clashes with an existing service")
    base_lat = c.num(
        "service.baseline_latency_ms",
        svc_raw.get("baseline_latency_ms"),
        0,
        LEVEL_MAX,
        lo_open=True,
    )
    base_err = c.num(
        "service.baseline_error_rate", svc_raw.get("baseline_error_rate"), 0, 1, lo_open=True
    )
    latency = _series(c, "service.latency", svc_raw.get("latency"), 0, LEVEL_MAX, lo_open=True)
    error_rate = _series(c, "service.error_rate", svc_raw.get("error_rate"), 0, 1, lo_open=False)

    deployments = _deployments(c, svc_raw.get("deployments", []))
    dependencies = _dependencies(c, name, svc_raw.get("dependencies", []), known_services)
    effects = _effects(c, svc_raw.get("effects", {}))

    fired_at = _grid_time(c, "alert.fired_at", alert_raw.get("fired_at"))
    anchor = _grid_time(c, "service.anchor", svc_raw["anchor"]) if "anchor" in svc_raw else fired_at
    alert_id = c.text(
        "alert.alert_id", alert_raw.get("alert_id"), _ALERT_ID, "letters, digits, hyphens"
    )
    if alert_id in known_alerts:
        c.fail("alert.alert_id", "clashes with an existing alert")
    severity = alert_raw.get("severity")
    if severity not in SEVERITIES:
        c.fail("alert.severity", f"must be one of {', '.join(SEVERITIES)}")
    metric = alert_raw.get("metric")
    if metric not in METRICS:
        c.fail("alert.metric", f"must be one of {', '.join(METRICS)}")
    summary = c.free_text("alert.summary", alert_raw.get("summary"), MAX_SUMMARY_CHARS)

    if c.errors:
        raise ValidationError(c.errors)
    spec = ServiceSpec(
        name, base_lat, base_err, latency, error_rate, deployments, anchor, anchor, dependencies
    )
    return Upload(
        spec, Alert(alert_id, name, fired_at, str(severity), str(metric), summary), effects
    )


@dataclass(frozen=True)
class IntakeDraft:
    """One accepted Alertmanager alert. Labels and annotations are display text only."""

    service: str
    metric: str
    summary: str
    labels: tuple[tuple[str, str], ...]
    annotations: tuple[tuple[str, str], ...]
    starts_at: str
    fingerprint: str


_LABEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
_FINGERPRINT = re.compile(r"^[A-Za-z0-9]{1,64}$")
_AM_TOP = (
    "version",
    "groupKey",
    "truncatedAlerts",
    "status",
    "receiver",
    "groupLabels",
    "commonLabels",
    "commonAnnotations",
    "externalURL",
    "alerts",
)
_AM_ALERT = ("status", "labels", "annotations", "startsAt", "endsAt", "generatorURL", "fingerprint")


def _text_map(
    c: _Collector, path: str, raw: object, max_items: int, max_value: int
) -> dict[str, str]:
    """A label or annotation map: bounded count, plain keys, printable values (may be empty)."""
    if not isinstance(raw, dict) or len(raw) > max_items:
        c.fail(path, f"must be an object of at most {max_items} entries")
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not _LABEL_KEY.match(key):
            c.fail(f"{path}.{key[:40]}", "key must be letters, digits, underscores")
        elif not isinstance(value, str) or len(value) > max_value or not value.isprintable():
            c.fail(f"{path}.{key}", f"must be printable text of at most {max_value} characters")
        else:
            out[key] = value
    return out


def _plain(c: _Collector, path: str, raw: object, limit: int = 200) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str) or len(raw) > limit or not raw.isprintable():
        c.fail(path, f"must be printable text of at most {limit} characters")
        return ""
    return raw


def validate_alertmanager(
    raw: object, reference: Callable[[str], Alert | None]
) -> tuple[IntakeDraft, ...]:
    """Alertmanager webhook v4 -> drafts, or ValidationError.

    Labels are untrusted text. The only label read as data is `service` (and an optional `metric`),
    and only as an exact-match key into services the hub already holds; severity is never taken
    from a label. `reference(service)` gives an existing alert on that service or None.
    """
    c = _Collector()
    top = c.obj("payload", raw, _AM_TOP)
    if top.get("version") != "4":
        c.fail("version", 'must be "4"')
    if top.get("status", "firing") not in ("firing", "resolved"):
        c.fail("status", "must be firing or resolved")
    for key in ("groupKey", "receiver", "externalURL"):
        _plain(c, key, top.get(key))
    for key, limit in (("groupLabels", MAX_LABELS), ("commonLabels", MAX_LABELS)):
        _text_map(c, key, top.get(key, {}), limit, MAX_LABEL_CHARS)
    _text_map(
        c, "commonAnnotations", top.get("commonAnnotations", {}), MAX_ANNOTATIONS, MAX_SUMMARY_CHARS
    )
    if "truncatedAlerts" in top:
        c.num("truncatedAlerts", top["truncatedAlerts"], 0, 1_000_000)
    alerts = top.get("alerts")
    if not isinstance(alerts, list) or not 1 <= len(alerts) <= MAX_INTAKE_PER_POST:
        c.fail("alerts", f"must be a list of 1 to {MAX_INTAKE_PER_POST} alerts")
        alerts = []
    drafts = []
    for i, item in enumerate(alerts):
        path = f"alerts[{i}]"
        a = c.obj(path, item, _AM_ALERT)
        if a.get("status", "firing") != "firing":
            c.fail(f"{path}.status", "only firing alerts are accepted")
        labels = _text_map(c, f"{path}.labels", a.get("labels"), MAX_LABELS, MAX_LABEL_CHARS)
        notes = _text_map(
            c, f"{path}.annotations", a.get("annotations", {}), MAX_ANNOTATIONS, MAX_SUMMARY_CHARS
        )
        starts_at = _plain(c, f"{path}.startsAt", a.get("startsAt"), 40)
        _plain(c, f"{path}.endsAt", a.get("endsAt"), 40)
        _plain(c, f"{path}.generatorURL", a.get("generatorURL"))
        fingerprint = a.get("fingerprint", "")
        if fingerprint != "" and not (
            isinstance(fingerprint, str) and _FINGERPRINT.match(fingerprint)
        ):
            c.fail(f"{path}.fingerprint", "must be letters and digits, at most 64 characters")
            fingerprint = ""
        service = labels.get("service", "")
        ref = reference(service) if _NAME.match(service) else None
        if ref is None:
            c.fail(f"{path}.labels.service", "must name a service this hub already holds")
            continue
        metric = labels.get("metric", ref.metric)
        if metric not in METRICS:
            c.fail(f"{path}.labels.metric", f"must be one of {', '.join(METRICS)}")
        summary = notes.get("summary") or notes.get("description")
        if summary is None:
            summary = f"Alertmanager alert on {service}"
        elif not summary.strip():
            c.fail(f"{path}.annotations", "summary must not be blank")
        drafts.append(
            IntakeDraft(
                service,
                metric,
                summary,
                tuple(labels.items()),
                tuple(notes.items()),
                starts_at,
                str(fingerprint),
            )
        )
    if c.errors:
        raise ValidationError(c.errors)
    return tuple(drafts)


def _deployments(c: _Collector, raw: object) -> tuple[tuple[float, str], ...]:
    if not isinstance(raw, list) or len(raw) > MAX_DEPLOYMENTS:
        c.fail("service.deployments", f"must be a list of at most {MAX_DEPLOYMENTS} items")
        return ()
    out = []
    for i, item in enumerate(raw):
        path = f"service.deployments[{i}]"
        d = c.obj(path, item, ("at", "version"))
        at = c.num(f"{path}.at", d.get("at"), TIME_MIN, TIME_MAX)
        version = c.text(f"{path}.version", d.get("version"), _VERSION, "a short version label")
        out.append((at, version))
    return tuple(sorted(out))


def _dependencies(c: _Collector, name: str, raw: object, known: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) > MAX_DEPENDENCIES:
        c.fail("service.dependencies", f"must be a list of at most {MAX_DEPENDENCIES} names")
        return ()
    for i, dep in enumerate(raw):
        if not isinstance(dep, str) or dep not in known:
            c.fail(f"service.dependencies[{i}]", "must name an existing service")
        elif dep == name:
            c.fail(f"service.dependencies[{i}]", "a service cannot depend on itself")
    if len(set(map(str, raw))) != len(raw):
        c.fail("service.dependencies", "must not repeat a name")
    return tuple(d for d in raw if isinstance(d, str))


def _effects(c: _Collector, raw: object) -> dict[str, dict[str, float]]:
    c.obj("service.effects", raw, tuple(ACTION_PROPERTIES))
    out: dict[str, dict[str, float]] = {}
    for action, outcomes in raw.items() if isinstance(raw, dict) else ():
        path = f"service.effects.{action}"
        spec = c.obj(path, outcomes, REMEDIATION_OUTCOMES)
        out[action] = {}
        for outcome in REMEDIATION_OUTCOMES:
            if outcome not in spec:
                c.fail(f"{path}.{outcome}", "is required")
            out[action][outcome] = c.num(
                f"{path}.{outcome}", spec.get(outcome), 0, LEVEL_MAX, lo_open=True
            )
    return out


def validate_runbooks(raw: object) -> tuple[Runbook, ...]:
    """A runbook set for a run: {"runbooks": [...]} -> Runbooks, or ValidationError per field.

    A signature must be non-empty (an empty one would be confirmed at once) and use only known
    predicate ids (an unknown one would crash the investigator). The tier is never an input: it
    comes from the action alone, so a custom runbook cannot lower the approval requirement.
    """
    c = _Collector()
    top = c.obj("request", raw, ("runbooks",))
    items = top.get("runbooks")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_RUNBOOKS:
        c.fail("runbooks", f"must be a list of 1 to {MAX_RUNBOOKS} runbooks")
        items = []
    out: list[Runbook] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        path = f"runbooks[{i}]"
        rb = c.obj(path, item, ("runbook_id", "title", "text", "signature", "action", "follow_ups"))
        rid = c.text(
            f"{path}.runbook_id",
            rb.get("runbook_id"),
            _RUNBOOK_ID,
            "1-20 letters, digits or dashes",
        )
        if rid and rid in seen:
            c.fail(f"{path}.runbook_id", "must be unique in the set")
        seen.add(rid)
        title = c.free_text(f"{path}.title", rb.get("title"), MAX_TITLE_CHARS)
        text = rb.get("text")
        if isinstance(
            text, str
        ):  # the corpus text has line breaks; other control characters stay out
            c.free_text(f"{path}.text", _LINE_BREAKS.sub(" ", text), MAX_RUNBOOK_TEXT_CHARS)
        else:
            c.fail(f"{path}.text", "must be a string")
        action = rb.get("action")
        if not isinstance(action, str) or action not in ACTION_PROPERTIES:
            c.fail(f"{path}.action", f"must be one of {', '.join(ACTION_PROPERTIES)}")
        signature = _signature(c, f"{path}.signature", rb.get("signature"))
        follow_ups = _follow_ups(c, f"{path}.follow_ups", rb.get("follow_ups", []))
        out.append(Runbook(rid, title, str(text), signature, str(action), follow_ups))
    if c.errors:
        raise ValidationError(c.errors)
    return tuple(out)


def _signature(c: _Collector, path: str, raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_SIGNATURE:
        c.fail(path, f"must be a list of 1 to {MAX_SIGNATURE} predicate ids")
        return ()
    ids = [p for p in raw if isinstance(p, str) and p in PREDICATES]
    if len(ids) != len(raw):
        c.fail(path, f"must only use these predicates: {', '.join(PREDICATES)}")
    elif len(set(ids)) != len(ids):
        c.fail(path, "must not repeat a predicate")
    return tuple(ids)


def _follow_ups(c: _Collector, path: str, raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) > MAX_FOLLOW_UPS:
        c.fail(path, f"must be a list of at most {MAX_FOLLOW_UPS} strings")
        return ()
    return tuple(
        c.free_text(f"{path}[{i}]", item, MAX_FOLLOW_UP_CHARS) for i, item in enumerate(raw)
    )


def validate_run_request(
    raw: object, known_alerts: frozenset[str], known_services: Callable[[str], bool]
) -> dict[str, object]:
    """A run or playground request: alert_id, mode, fix_outcome, deadline_s, planted_logs, what_if."""
    c = _Collector()
    req = c.obj(
        "request",
        raw,
        (
            "alert_id",
            "mode",
            "fix_outcome",
            "deadline_s",
            "planted_logs",
            "text",
            "what_if",
            "runbook_set",
        ),
    )
    alert_id = req.get("alert_id")
    if not isinstance(alert_id, str) or alert_id not in known_alerts:
        c.fail("alert_id", "must name an existing alert")
    mode = req.get("mode", "scripted")
    if mode not in ("scripted", "silent", "web"):
        c.fail("mode", "must be scripted, silent or web")
    fix_outcome = req.get("fix_outcome", "success")
    if fix_outcome not in REMEDIATION_OUTCOMES:
        c.fail("fix_outcome", f"must be one of {', '.join(REMEDIATION_OUTCOMES)}")
    deadline = req.get("deadline_s")
    if deadline is not None:
        deadline = c.num("deadline_s", deadline, 0, MAX_DEADLINE_S, lo_open=True)
    planted = _planted(c, req.get("planted_logs", {}), known_services)
    what_if = _what_if(c, req.get("what_if", []))
    text = req.get("text")
    if text is not None:
        text = c.free_text("text", text, MAX_PLANTED_CHARS)
    runbook_set = req.get("runbook_set")
    if runbook_set is not None:
        runbook_set = c.text("runbook_set", runbook_set, _SET_ID, "a runbook set id")
    if c.errors:
        raise ValidationError(c.errors)
    return {
        "alert_id": alert_id,
        "mode": mode,
        "fix_outcome": fix_outcome,
        "deadline_s": deadline,
        "planted_logs": planted,
        "text": text,
        "what_if": what_if,
        "runbook_set": runbook_set,
    }


def parse_diff_request(raw: object) -> tuple[str, str]:
    """{"a": run_id, "b": run_id}; ids are the 16 hex characters the hub generated."""
    c = _Collector()
    req = c.obj("request", raw, ("a", "b"))
    ids = []
    for key in ("a", "b"):
        value = req.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{16}", value):
            c.fail(key, "must be a run id")
        ids.append(str(value))
    if c.errors:
        raise ValidationError(c.errors)
    return ids[0], ids[1]


def validate_explain_request(raw: object, known_alerts: frozenset[str]) -> dict[str, object]:
    """{"alert_id", "question", "llm", "acknowledge_remote"}. No URL, model or key is accepted."""
    c = _Collector()
    req = c.obj("request", raw, ("alert_id", "question", "llm", "acknowledge_remote"))
    alert_id = req.get("alert_id")
    if not isinstance(alert_id, str) or alert_id not in known_alerts:
        c.fail("alert_id", "must name an existing alert")
    question = c.free_text("question", req.get("question"), MAX_QUESTION_CHARS)
    llm = _llm_mode(c, req.get("llm", "off"))
    ack = req.get("acknowledge_remote", False)
    if not isinstance(ack, bool):
        c.fail("acknowledge_remote", "must be true or false")
    elif llm == "hosted" and not ack:
        c.fail(
            "acknowledge_remote",
            "hosted mode sends the question and incident facts to a remote service; "
            "set true to confirm",
        )
    if c.errors:
        raise ValidationError(c.errors)
    return {"alert_id": alert_id, "question": question, "llm": llm, "acknowledge_remote": ack}


def validate_evaluate_request(raw: object) -> dict[str, object]:
    """{"llm", "acknowledge_remote"}: the same remote-confirmation rule as the explain box."""
    c = _Collector()
    req = c.obj("request", raw, ("llm", "acknowledge_remote"))
    llm = _llm_mode(c, req.get("llm", "off"))
    ack = req.get("acknowledge_remote", False)
    if not isinstance(ack, bool):
        c.fail("acknowledge_remote", "must be true or false")
    elif llm == "hosted" and not ack:
        c.fail("acknowledge_remote", "hosted mode sends incident facts to a remote service")
    if c.errors:
        raise ValidationError(c.errors)
    return {"llm": llm, "acknowledge_remote": ack}


def _llm_mode(c: _Collector, raw: object) -> str:
    if not isinstance(raw, str) or raw not in LLM_MODES:
        c.fail("llm", f"must be one of {', '.join(LLM_MODES)}")
        return "off"
    return raw


def _what_if(c: _Collector, raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) > len(WHAT_IFS):
        c.fail("what_if", f"must be a list of at most {len(WHAT_IFS)} names")
        return ()
    if not all(isinstance(x, str) and x in WHAT_IFS for x in raw) or len(set(raw)) != len(raw):
        c.fail("what_if", f"must be distinct names from: {', '.join(WHAT_IFS)}")
        return ()
    return tuple(raw)


def _planted(
    c: _Collector, raw: object, known_services: Callable[[str], bool]
) -> dict[str, tuple[str, ...]]:
    if not isinstance(raw, dict):
        c.fail("planted_logs", "must be an object of service -> list of lines")
        return {}
    out = {}
    for service, lines in raw.items():
        path = f"planted_logs.{service}"
        if not known_services(service):
            c.fail(path, "must name an existing service")
        elif not isinstance(lines, list) or not 1 <= len(lines) <= MAX_PLANTED_LINES:
            c.fail(path, f"must be a list of 1 to {MAX_PLANTED_LINES} lines")
        elif not all(isinstance(x, str) and 0 < len(x) <= MAX_PLANTED_CHARS for x in lines):
            c.fail(path, f"each line must be a string of at most {MAX_PLANTED_CHARS} characters")
        else:
            out[service] = tuple(lines)
    return out


__all__ = [
    "INTAKE_SEVERITY",
    "MAX_BODY_BYTES",
    "MAX_INTAKE",
    "MAX_RUNBOOKS",
    "MAX_UPLOADS",
    "PREDICATE_HELP",
    "WHAT_IFS",
    "IntakeDraft",
    "Upload",
    "ValidationError",
    "parse_diff_request",
    "parse_json",
    "validate_alertmanager",
    "validate_evaluate_request",
    "validate_explain_request",
    "validate_run_request",
    "validate_runbooks",
    "validate_upload",
]
