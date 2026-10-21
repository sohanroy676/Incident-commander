"""Seeded scenario generator (EXTENSION_PLAN item 39): a robustness check, not an accuracy claim.

Each scenario is a fresh service world built from the fixture helpers (`flat`, `step`, `ramp`) with
parameters drawn from `random.Random(seed)`, so the same seed always gives the same worlds. The
incident class is the label by construction; the graded pipeline then runs on it unchanged and the
runbook it picks is compared with that label in a confusion matrix. This measures consistency on
fixtures we authored, never real-world accuracy. Severity is drawn at random too: a decision that
depended on it would show up as a mismatch. It is not fault injection: nothing random happens at
run time.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

from incident_commander.approval import ScriptedResponder
from incident_commander.commander import Commander
from incident_commander.config import LOOKBACK_S, PRIMARY_ONCALL
from incident_commander.fixtures.alerts import DAY_S, T0
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.fixtures.services import ServiceSpec, flat, ramp, step
from incident_commander.retrieval import HybridRanker
from incident_commander.types import Alert
from incident_commander.world import SimWorld

NONE = "none"
# Incident class -> the runbook the pipeline is expected to pick ("none": a human takes over).
CLASSES: dict[str, str] = {
    "deploy_regression": "RB-101",
    "memory_leak": "RB-102",
    "dependency_down": "RB-103",
    "config_errors": "RB-104",
    "no_fault": NONE,
}
SEVERITIES = ("low", "medium", "high")
_FIRST_DAY = 20  # generated alerts sit well after the demo and golden alerts, one day apart


@dataclass(frozen=True)
class Scenario:
    label: str
    expected: str
    alert: Alert
    services: dict[str, ServiceSpec]


@dataclass(frozen=True)
class GeneratedResult:
    scenario: Scenario
    predicted: str

    @property
    def ok(self) -> bool:
        return self.predicted == self.scenario.expected


def _spec(
    name: str,
    at: float,
    base_ms: float,
    base_err: float,
    latency,
    errors,
    deploys: tuple[tuple[float, str], ...] = (),
    deps: tuple[str, ...] = (),
) -> ServiceSpec:
    return ServiceSpec(name, base_ms, base_err, latency, errors, deploys, at, at - 900, deps)


def build_scenario(rng: random.Random, index: int, label: str) -> Scenario:
    at = T0 + (_FIRST_DAY + index) * DAY_S
    name = f"gen-{index:03d}-service"
    base_ms = rng.uniform(60.0, 200.0)
    base_err = rng.uniform(0.004, 0.012)
    jump = rng.uniform(4.0, 9.0)  # latency multiple, well past the elevated ratio
    deploy_version = f"v{rng.randint(1, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 9)}"
    services: dict[str, ServiceSpec] = {}
    if label == "deploy_regression":
        onset = at - rng.uniform(300.0, 900.0)
        deploys = ((onset - rng.uniform(30.0, 120.0), deploy_version),)
        spec = _spec(
            name,
            at,
            base_ms,
            base_err,
            step(base_ms, onset, base_ms * jump),
            flat(base_err),
            deploys,
        )
    elif label == "memory_leak":
        old = ((at - rng.uniform(12000.0, 20000.0), deploy_version),)  # inside lookback, not window
        latency = ramp(base_ms, at - LOOKBACK_S, at, base_ms * jump)
        spec = _spec(name, at, base_ms, base_err, latency, flat(base_err), old)
    elif label == "dependency_down":
        dep = f"gen-{index:03d}-db"
        onset = at - rng.uniform(600.0, 1200.0)
        spec = _spec(
            name,
            at,
            base_ms,
            base_err,
            step(base_ms, onset, base_ms * jump),
            step(base_err, onset, base_err * rng.uniform(4.0, 8.0)),
            deps=(dep,),
        )
        dep_ms = rng.uniform(50.0, 90.0)
        dep_err = rng.uniform(0.003, 0.006)
        services[dep] = _spec(dep, at, dep_ms, dep_err, flat(dep_ms * 4), flat(dep_err * 5))
    elif label == "config_errors":
        onset = at - rng.uniform(300.0, 900.0)
        deploys = ((onset - rng.uniform(30.0, 120.0), deploy_version),)
        errors = step(base_err, onset, base_err * rng.uniform(4.0, 8.0))
        spec = _spec(name, at, base_ms, base_err, flat(base_ms), errors, deploys)
    elif label == "no_fault":
        spec = _spec(name, at, base_ms, base_err, flat(base_ms), flat(base_err))
    else:
        raise ValueError(f"unknown incident class: {label}")
    services[name] = spec
    alert = Alert(
        f"ALRT-{index + 9500}",
        name,
        at,
        rng.choice(SEVERITIES),
        "latency_ms",
        f"{name} latency and error rate report",
    )
    return Scenario(label, CLASSES[label], alert, services)


def generate(seed: int, count: int) -> list[Scenario]:
    """`count` scenarios cycling through the classes, so every class appears when count >= 5."""
    rng = random.Random(seed)
    labels = tuple(CLASSES)
    return [build_scenario(rng, i, labels[i % len(labels)]) for i in range(count)]


def run_scenario(s: Scenario) -> GeneratedResult:
    world = SimWorld(services=s.services, alerts={s.alert.alert_id: s.alert})
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    commander = Commander(world, ranker, ScriptedResponder({PRIMARY_ONCALL: (0.0, "approve")}))
    case = commander.run(s.alert)
    assert case.investigation is not None
    verdict = case.investigation.verdict
    predicted = verdict.runbook_id if verdict.kind == "matched" and verdict.runbook_id else NONE
    return GeneratedResult(s, predicted)


def confusion(results: list[GeneratedResult]) -> Counter[tuple[str, str]]:
    """(expected, predicted) -> count."""
    return Counter((r.scenario.expected, r.predicted) for r in results)


def format_report(seed: int, results: list[GeneratedResult]) -> list[str]:
    counts = confusion(results)
    columns = [*(rb for rb in CLASSES.values() if rb != NONE), NONE]
    note = "consistency on authored fixtures, not real-world accuracy"
    lines = [
        f"generated: seed={seed} scenarios={len(results)} ({note})",
        "expected\\predicted " + " ".join(f"{c:>7}" for c in columns),
    ]
    for expected in columns:
        lines.append(f"{expected:<18} " + " ".join(f"{counts[(expected, c)]:>7}" for c in columns))
    agree = sum(r.ok for r in results)
    lines.append(f"agree={agree}/{len(results)}")
    for r in results:
        if not r.ok:
            lines.append(
                f"mismatch {r.scenario.alert.alert_id} class={r.scenario.label}"
                f" expected={r.scenario.expected} predicted={r.predicted}"
            )
    return lines
