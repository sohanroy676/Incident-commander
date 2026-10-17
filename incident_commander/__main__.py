"""CLI: python -m incident_commander tools|investigate <ALERT>|gates (more arrive per version)."""

from __future__ import annotations

import argparse
import sys

from .approval import ApprovalGate, ScriptedResponder
from .blast_radius import classify_remediation
from .clocks import ControlClock, DataClock
from .config import (
    APPROVAL_DEADLINE_S,
    APPROVAL_DEMO_SLEEP_S,
    APPROVAL_TICK_S,
    DATA_CLOCK_START_OFFSET_S,
    LOOKBACK_S,
    PRIMARY_ONCALL,
    SECONDARY_ONCALL,
    STATIC_RANKER_ORDER,
)
from .executor import Executor
from .fixtures.runbooks import RUNBOOKS
from .investigator import ToolBox, investigate
from .report import (
    EXECUTION_HEADER,
    M3_TITLE,
    M4_TITLE,
    M5_TITLE,
    PrintTrace,
    classify_decision,
    decision,
    header,
    kv,
    m1_report,
    verdict_decision,
)
from .retrieval import StaticRanker
from .tools import (
    get_dependencies,
    get_deployments,
    get_error_rate,
    get_latency,
    get_logs,
)
from .types import Alert
from .world import SimWorld


def _lookup(world: SimWorld, alert_id: str) -> Alert | None:
    try:
        return world.alert(alert_id)
    except KeyError:
        print(
            f"unknown alert: {alert_id} (known: {', '.join(world.alert_ids())})",
            file=sys.stderr,
        )
        return None


def cmd_tools(alert_id: str) -> int:
    world = SimWorld()
    alert = _lookup(world, alert_id)
    if alert is None:
        return 2
    clock = DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S)
    start, end = alert.fired_at - LOOKBACK_S, alert.fired_at
    observations = [
        get_latency(world, clock, alert.service, start, end),
        get_error_rate(world, clock, alert.service, start, end),
        get_deployments(world, clock, alert.service, start, end),
        get_dependencies(world, clock, alert.service, end),
        get_logs(world, clock, alert.service, start, end),
    ]
    print(m1_report(alert, observations))
    return 0


def cmd_investigate(alert_id: str) -> int:
    world = SimWorld()
    alert = _lookup(world, alert_id)
    if alert is None:
        return 2
    ranker = StaticRanker(STATIC_RANKER_ORDER)
    order = ",".join(c.runbook_id for c in ranker.rank(alert.summary))
    print(header(3, M3_TITLE))
    print(
        kv(alert=alert.alert_id, ranker=ranker.label, order=order)
        + "   # stub deliberately wrong-first"
    )
    clock = DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S)
    result = investigate(alert, ranker, ToolBox(world, clock), trace=PrintTrace())
    print(verdict_decision(alert.alert_id, result.verdict))
    return 0


def _matched_action(world: SimWorld, alert: Alert) -> str | None:
    """The action of the runbook the Investigator matched (silent run), or None."""
    clock = DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S)
    ranker = StaticRanker(STATIC_RANKER_ORDER)
    verdict = investigate(alert, ranker, ToolBox(world, clock)).verdict
    return RUNBOOKS[verdict.runbook_id].action if verdict.runbook_id else None


def cmd_gates() -> int:
    """M4 classification, M5 time-boxed approval on the real clock, and an execute/retry demo."""
    world = SimWorld()
    alerts = [world.alert("ALRT-9001"), world.alert("ALRT-9002")]
    actions = {}
    print(header(4, M4_TITLE))
    for alert in alerts:
        action = _matched_action(world, alert)
        if action is None:
            print(f"no matched runbook for {alert.alert_id}", file=sys.stderr)
            return 1
        actions[alert.alert_id] = action
        print(classify_decision(alert, classify_remediation(action)))

    print(header(5, M5_TITLE))
    clock = ControlClock()
    trace = PrintTrace(clock)
    window = APPROVAL_DEADLINE_S
    responder = ScriptedResponder({PRIMARY_ONCALL: (0.05, "approve")})
    gate = ApprovalGate(clock, responder, PRIMARY_ONCALL, SECONDARY_ONCALL, window, APPROVAL_TICK_S)
    page = gate.new_page(PRIMARY_ONCALL, SECONDARY_ONCALL)
    trace.emit("PAGE", target=page.target, window_s=window)
    check = page.check(clock.now())
    print(decision("page_check", case="immediate", window_s=window, escalated=check.escalated))
    trace.emit("SLEEP", real_seconds=APPROVAL_DEMO_SLEEP_S)
    clock.sleep(APPROVAL_DEMO_SLEEP_S)
    check = page.check(clock.now())
    print(
        decision(
            "page_check",
            case="after_sleep",
            window_s=window,
            escalated=check.escalated,
            **{"from": check.from_, "to": check.to},
        )
    )
    answered = gate.new_page(PRIMARY_ONCALL, SECONDARY_ONCALL)
    clock.sleep(0.1)
    if responder.poll(answered.target, clock.now() - answered.issued_at) == "approve":
        answered.acknowledge()
    check = answered.check(clock.now())
    print(
        decision(
            "page_check",
            case="answered_in_time",
            escalated=check.escalated,
            reason=check.reason,
        )
    )

    print(EXECUTION_HEADER)
    alert = alerts[1]
    action = actions[alert.alert_id]
    executor = Executor(world, DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S))
    for _ in range(2):  # the second call is the retry
        result = executor.execute(action, alert.service, alert.alert_id, None)
        print(
            decision(
                "execute",
                alert=alert.alert_id,
                action=action,
                status=result.status,
                execution_id=result.execution_id,
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m incident_commander")
    sub = parser.add_subparsers(dest="command", required=True)
    tools = sub.add_parser("tools", help="M1: query the five signal tools for an alert")
    tools.add_argument("alert_id")
    investigate_cmd = sub.add_parser(
        "investigate", help="M3: investigate an alert with the stub ranker"
    )
    investigate_cmd.add_argument("alert_id")
    sub.add_parser("gates", help="M4/M5: classification, time-boxed approval, idempotent execution")
    args = parser.parse_args(argv)
    if args.command == "gates":
        return cmd_gates()
    if args.command == "investigate":
        return cmd_investigate(args.alert_id)
    return cmd_tools(args.alert_id)


if __name__ == "__main__":
    sys.exit(main())
