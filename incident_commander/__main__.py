"""CLI: python -m incident_commander tools <ALERT> (more commands arrive per version)."""

from __future__ import annotations

import argparse
import sys

from .clocks import DataClock
from .config import DATA_CLOCK_START_OFFSET_S, LOOKBACK_S
from .report import m1_report
from .tools import (
    get_dependencies,
    get_deployments,
    get_error_rate,
    get_latency,
    get_logs,
)
from .world import SimWorld


def cmd_tools(alert_id: str) -> int:
    world = SimWorld()
    try:
        alert = world.alert(alert_id)
    except KeyError:
        print(
            f"unknown alert: {alert_id} (known: {', '.join(world.alert_ids())})",
            file=sys.stderr,
        )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m incident_commander")
    sub = parser.add_subparsers(dest="command", required=True)
    tools = sub.add_parser("tools", help="M1: query the five signal tools for an alert")
    tools.add_argument("alert_id")
    args = parser.parse_args(argv)
    return cmd_tools(args.alert_id)


if __name__ == "__main__":
    sys.exit(main())
