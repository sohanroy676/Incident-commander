"""X3: decisions are identical with every LLM role on (AC-23).

For each fixture alert the advisor suggests a tool order, the graded pipeline runs with that order
(`investigate`'s own `tool_order` argument), then the narrator and explainer read the finished case.
The DECISION lines must equal a baseline run with no LLM. `incident_commander/` is never edited:
`advised_orders` only passes the existing argument through for the duration of a run.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from incident_commander import commander as graded_commander
from incident_commander.commander import Case
from incident_commander.evaluate import golden_world
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.investigator import EVIDENCE_TOOLS
from incident_commander.report import case_decision_lines
from incident_commander.retrieval import HybridRanker

from .advisor import advise
from .explainer import explain
from .llm_client import LLMClient
from .narrator import narrate
from .scenarios import _commander

QUESTION = "why did the agent act this way?"
ROLES_LINE = "llm: roles=narrator,explainer,advisor decisions_changed={changed}"


@dataclass(frozen=True)
class X3Row:
    alert_id: str
    advisor: str
    narrator: str
    explainer: str
    order: tuple[str, ...]
    identical: bool

    def line(self) -> str:
        return (
            f"x3 alert={self.alert_id} advisor={self.advisor} narrator={self.narrator} "
            f"explainer={self.explainer} order={','.join(self.order)} identical={self.identical}"
        )


@contextmanager
def advised_orders(orders: Mapping[str, tuple[str, ...]]) -> Iterator[None]:
    """Run the graded pipeline with a tool order per alert id; other alerts keep the fixed order."""
    original = graded_commander.investigate

    def with_order(alert, *args, **kwargs):
        return original(
            alert, *args, tool_order=orders.get(alert.alert_id, EVIDENCE_TOOLS), **kwargs
        )

    graded_commander.investigate = with_order
    try:
        yield
    finally:
        graded_commander.investigate = original


def run_case(alert_id: str, orders: Mapping[str, tuple[str, ...]] | None = None) -> Case:
    """One alert on its own fresh golden world, optionally under advised tool orders."""
    with advised_orders(orders or {}):
        world = golden_world()
        return _commander(world).run(world.alert(alert_id))


def decisions(case: Case) -> tuple[str, ...]:
    return tuple(case_decision_lines(case))


def x3_row(alert_id: str, client: LLMClient | None) -> X3Row:
    """All three roles on one alert; `identical` compares its DECISION lines with the baseline."""
    world = golden_world()
    alert = world.alert(alert_id)
    candidates = HybridRanker(tuple(RUNBOOKS.values())).rank(alert.summary)
    advice = advise(alert, candidates, client)
    baseline = decisions(run_case(alert_id))
    case = run_case(alert_id, {alert_id: advice.order})
    narration = narrate(case, client)
    explanation = explain(case, QUESTION, client)
    return X3Row(
        alert_id,
        advice.status,
        narration.status,
        explanation.status,
        advice.order,
        decisions(case) == baseline,
    )


def run_x3(client: LLMClient | None) -> list[X3Row]:
    return [x3_row(alert_id, client) for alert_id in golden_world().alert_ids()]


def advised_orders_of(rows: list[X3Row]) -> dict[str, tuple[str, ...]]:
    return {row.alert_id: row.order for row in rows}
