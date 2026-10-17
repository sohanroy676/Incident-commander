"""CLI: python -m incident_commander tools|investigate <ALERT> (more commands arrive per version)."""

from __future__ import annotations

import argparse
import sys

from .clocks import DataClock
from .config import DATA_CLOCK_START_OFFSET_S, LOOKBACK_S, STATIC_RANKER_ORDER
from .investigator import ToolBox, investigate
from .report import M3_TITLE, PrintTrace, header, kv, m1_report, verdict_decision
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m incident_commander")
    sub = parser.add_subparsers(dest="command", required=True)
    tools = sub.add_parser("tools", help="M1: query the five signal tools for an alert")
    tools.add_argument("alert_id")
    investigate_cmd = sub.add_parser(
        "investigate", help="M3: investigate an alert with the stub ranker"
    )
    investigate_cmd.add_argument("alert_id")
    args = parser.parse_args(argv)
    if args.command == "investigate":
        return cmd_investigate(args.alert_id)
    return cmd_tools(args.alert_id)


if __name__ == "__main__":
    sys.exit(main())
