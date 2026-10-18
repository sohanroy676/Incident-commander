"""CLI: python -m incident_commander tools|investigate <ALERT>|gates|run <ALERT>|--all."""

from __future__ import annotations

import argparse
import sys

from .approval import ApprovalGate, ScriptedResponder
from .blast_radius import classify_remediation
from .clocks import ControlClock, DataClock
from .commander import Case, Commander
from .config import (
    APPROVAL_DEADLINE_S,
    APPROVAL_DEMO_SLEEP_S,
    APPROVAL_TICK_S,
    DATA_CLOCK_START_OFFSET_S,
    DEMO_SECONDARY_DELAY_S,
    LOOKBACK_S,
    PRIMARY_ONCALL,
    SECONDARY_ONCALL,
    STATIC_RANKER_ORDER,
)
from .evaluate import attack_differential, golden_world, naive_baseline, run_golden
from .executor import Executor
from .fixtures.runbooks import RUNBOOKS
from .investigator import ToolBox, investigate
from .postmortem import OutboxNotifier
from .report import (
    EXECUTION_HEADER,
    M1_TITLE,
    M2_TITLE,
    M3_TITLE,
    M4_TITLE,
    M5_TITLE,
    M6_TITLE,
    M7_TITLE,
    M8_TITLE,
    PrintTrace,
    approval_decision,
    attack_lines,
    classify_decision,
    decision,
    event_line,
    execute_decision,
    golden_decision,
    golden_summary,
    handoff_decision,
    header,
    kv,
    m1_report,
    m2_table,
    naive_table,
    postmortem_decision,
    publish_decision,
    verdict_decision,
    verify_decision,
)
from .retrieval import HybridRanker, StaticRanker
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


def _page_check_demo() -> None:
    """The three M5 page behaviours on the real clock (Outcome 3)."""
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
    _page_check_demo()

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


def _m1_section(world: SimWorld, alert: Alert) -> None:
    clock = DataClock(alert.fired_at + DATA_CLOCK_START_OFFSET_S)
    start, end = alert.fired_at - LOOKBACK_S, alert.fired_at
    observations = [
        get_latency(world, clock, alert.service, start, end),
        get_error_rate(world, clock, alert.service, start, end),
        get_deployments(world, clock, alert.service, start, end),
        get_dependencies(world, clock, alert.service, end),
        get_logs(world, clock, alert.service, start, end),
    ]
    print(m1_report(alert, observations, with_header=False))


def _case_lines(case: Case, *kinds: str) -> None:
    for event in case.trace.events:
        if event.kind in kinds:
            print(event_line(event))


def _new_commander(world: SimWorld) -> Commander:
    script = {SECONDARY_ONCALL: (DEMO_SECONDARY_DELAY_S, "approve")}  # priya never answers
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    return Commander(world, ranker, ScriptedResponder(script))


def cmd_run(alert_id: str | None) -> int:
    """M1-M8 for one alert, or all three. Cases run first (real clock); sections print from the cases."""
    world = SimWorld()
    ids = world.alert_ids() if alert_id is None else (alert_id,)
    alerts = []
    for known in ids:
        alert = _lookup(world, known)
        if alert is None:
            return 2
        alerts.append(alert)
    commander = _new_commander(world)
    cases = [commander.run(a) for a in alerts]
    for case in cases:
        if case.execution is not None and case.alert.alert_id == "ALRT-9002":
            commander.retry_execution(case)  # Outcome 5: a retry must not execute again
    variant = None
    if alert_id is None:  # fix_fails needs a fresh world: the first run already fixed the service
        fresh = SimWorld()
        variant = _new_commander(fresh).run(fresh.alert("ALRT-9002"), fix_outcome="fix_fails")
    drafts = {c.alert.alert_id: c.draft for c in cases}

    print(header(1, M1_TITLE))
    for case in cases:
        _m1_section(world, case.alert)

    print(header(2, M2_TITLE))
    print(kv(ranker=HybridRanker.label))
    for case in cases:
        print(m2_table(case.alert, case.candidates))

    print(header(3, M3_TITLE))
    for case in cases:
        print(kv(alert=case.alert.alert_id))
        _case_lines(case, "ROUND", "HYPOTHESES")
        print(verdict_decision(case.alert.alert_id, case.investigation.verdict))

    print(header(4, M4_TITLE))
    for case in cases:
        if case.classification is not None:
            print(classify_decision(case.alert, case.classification))

    print(header(5, M5_TITLE))
    _page_check_demo()
    for case in cases:
        if case.approval is not None:
            _case_lines(case, "PAGE", "ESCALATE")
            token = case.approval.token
            print(
                approval_decision(
                    case.alert.alert_id,
                    case.approval.escalated,
                    token.approved_by if token else "none",
                )
            )

    print(header(6, M6_TITLE))
    for case in cases:
        aid = case.alert.alert_id
        for result in (case.execution, case.retry):
            if result is not None:
                print(execute_decision(aid, case.action, result))
        if case.verification is not None:
            print(verify_decision(aid, case.verification))
        if case.handoff_reason is not None:
            print(handoff_decision(aid, case.handoff_reason))
    if variant is not None:
        print(verify_decision(variant.alert.alert_id, variant.verification, "fix_fails"))
        print(handoff_decision(variant.alert.alert_id, variant.handoff_reason))

    print(header(7, M7_TITLE))
    for case in cases:
        aid = case.alert.alert_id
        print(postmortem_decision(aid, drafts[aid]))
        print(
            kv(
                alert=aid,
                timeline_events=len(drafts[aid].timeline),
                log_excerpts=len(drafts[aid].untrusted_log_excerpts),
            )
        )
    first = cases[0]
    published = commander.publish(first, OutboxNotifier())  # the explicit, human-triggered step
    _case_lines(first, "PUBLISH")
    print(publish_decision(first.alert.alert_id, published))

    print(header(8, M8_TITLE))
    return 0 if _m8_section() else 1


def _m8_section() -> bool:
    """Golden set and differential attack, each case on its own fresh world; True if all hold."""
    golden = run_golden(_new_commander)
    for result in golden:
        print(golden_decision(result))
    print(golden_summary(golden))
    attack = attack_differential(_new_commander)
    for line in attack_lines(attack):
        print(line)
    return all(r.passed for r in golden) and attack.unchanged


def cmd_evaluate() -> int:
    print(header(8, M8_TITLE))
    return 0 if _m8_section() else 1


def cmd_naive() -> int:
    """Approach A: the top retrieval hit's action with no investigation, on the same fixtures."""
    world = golden_world()
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    results = naive_baseline(ranker, (world.alert(a) for a in world.alert_ids()))
    print(naive_table(results))
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
    run_cmd = sub.add_parser("run", help="M1-M8 end to end for one alert, or --all")
    run_cmd.add_argument("alert_id", nargs="?")
    run_cmd.add_argument("--all", action="store_true", help="run all three demo alerts")
    sub.add_parser("evaluate", help="M8: golden set and planted-log attack")
    sub.add_parser("naive", help="naive baseline: top runbook, no investigation")
    args = parser.parse_args(argv)
    if args.command == "run":
        if args.all == (args.alert_id is not None):
            parser.error("run needs exactly one of an alert id or --all")
        return cmd_run(None if args.all else args.alert_id)
    if args.command == "evaluate":
        return cmd_evaluate()
    if args.command == "naive":
        return cmd_naive()
    if args.command == "gates":
        return cmd_gates()
    if args.command == "investigate":
        return cmd_investigate(args.alert_id)
    return cmd_tools(args.alert_id)


if __name__ == "__main__":
    sys.exit(main())
