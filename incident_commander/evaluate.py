"""Evaluation: golden set, differential planted-log attack, naive baseline (PHASE5 7.13).

The golden set is a regression check on fixtures we authored, not an accuracy claim. Nothing
here feeds back into a decision: results are only reported.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from .commander import Case, Commander
from .fixtures.alerts import ALERTS
from .fixtures.golden import (
    ATTACK_ALERT_ID,
    ATTACK_SERVICE,
    ATTACKS,
    GOLDEN_ALERTS,
    GOLDEN_EXPECTED,
    GOLDEN_SERVICES,
)
from .fixtures.runbooks import RUNBOOKS
from .fixtures.services import SERVICES
from .report import case_decision_lines
from .retrieval import Ranker
from .types import Alert, AttackResult, GoldenResult, NaiveResult
from .world import SimWorld

CommanderFactory = Callable[[SimWorld], Commander]

# Expected answers for the three demo alerts ("none": no runbook fits, a human takes over).
DEMO_EXPECTED: dict[str, tuple[str, str]] = {
    "ALRT-9001": ("RB-101", "rollback_deployment"),
    "ALRT-9002": ("RB-102", "restart_service"),
    "ALRT-9003": ("none", "none"),
}


def golden_world(planted_logs: Mapping[str, tuple[str, ...]] | None = None) -> SimWorld:
    """Golden services beside the demo ones, so G-3's dependency and the attack target exist."""
    return SimWorld(
        services={**SERVICES, **GOLDEN_SERVICES},
        alerts={**ALERTS, **GOLDEN_ALERTS},
        planted_logs=planted_logs,
    )


def run_golden(commander_factory: CommanderFactory) -> list[GoldenResult]:
    """Each golden incident on its own fresh world; pass = verdict, runbook and action as expected."""
    results = []
    for g in GOLDEN_EXPECTED:
        world = golden_world()
        case = commander_factory(world).run(world.alert(g.alert_id))
        verdict = case.investigation.verdict
        passed = (
            verdict.kind == "matched"
            and verdict.runbook_id == g.expected_runbook
            and case.action == g.expected_action
        )
        results.append(
            GoldenResult(
                g.golden_id,
                g.alert_id,
                verdict.kind,
                verdict.runbook_id,
                case.action,
                g.expected_runbook,
                g.expected_action,
                passed,
            )
        )
    return results


def attack_differential(commander_factory: CommanderFactory) -> AttackResult:
    """ALRT-9001 clean vs. with text planted in its service's logs.

    Asserts both (a) the exact Observations handed to the Investigator and (b) the decision
    lines are identical, for the first attack and for each extra variant.
    """

    def run(planted: tuple[str, ...]) -> Case:
        world = golden_world({ATTACK_SERVICE: planted} if planted else None)
        return commander_factory(world).run(world.alert(ATTACK_ALERT_ID))

    clean = run(())
    clean_inputs = clean.investigation.observations
    clean_lines = case_decision_lines(clean)
    outcomes = []
    for name, text in ATTACKS:
        attacked = run((text,))
        outcomes.append(
            (
                name,
                attacked.investigation.observations == clean_inputs,
                case_decision_lines(attacked) == clean_lines,
            )
        )
    verdict = clean.investigation.verdict
    return AttackResult(
        ATTACK_ALERT_ID,
        verdict.kind,
        verdict.runbook_id,
        clean.action,
        inputs_identical=all(i for _, i, _ in outcomes),
        decision_lines_identical=all(d for _, _, d in outcomes),
        variants=tuple((n, i and d) for n, i, d in outcomes),
    )


def naive_baseline(ranker: Ranker, alerts: Iterable[Alert]) -> list[NaiveResult]:
    """Approach A: run the top-ranked runbook's action with no investigation."""
    expected = dict(DEMO_EXPECTED)
    expected.update({g.alert_id: (g.expected_runbook, g.expected_action) for g in GOLDEN_EXPECTED})
    results = []
    for alert in alerts:
        top = ranker.rank(alert.summary)[0].runbook_id
        action = RUNBOOKS[top].action
        want_runbook, want_action = expected[alert.alert_id]
        results.append(
            NaiveResult(
                alert.alert_id, top, action, want_runbook, want_action, action == want_action
            )
        )
    return results
