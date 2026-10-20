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
from incident_commander.types import Alert

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

_NAME = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_ALERT_ID = re.compile(r"^[A-Za-z0-9-]{1,32}$")
_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,32}$")

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


def validate_run_request(
    raw: object, known_alerts: frozenset[str], known_services: Callable[[str], bool]
) -> dict[str, object]:
    """A run or playground request: alert_id, mode, fix_outcome, deadline_s, planted_logs, what_if."""
    c = _Collector()
    req = c.obj(
        "request",
        raw,
        ("alert_id", "mode", "fix_outcome", "deadline_s", "planted_logs", "text", "what_if"),
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
    "MAX_BODY_BYTES",
    "MAX_UPLOADS",
    "WHAT_IFS",
    "Upload",
    "ValidationError",
    "parse_diff_request",
    "parse_json",
    "validate_evaluate_request",
    "validate_explain_request",
    "validate_run_request",
    "validate_upload",
]
