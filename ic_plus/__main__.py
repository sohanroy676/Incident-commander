"""CLI: python -m ic_plus run <ALERT>|--all | scenario <name>|all   (v1.1: --llm off only)."""

from __future__ import annotations

import argparse
import sys

from incident_commander.__main__ import cmd_run
from incident_commander.commander import Commander
from incident_commander.config import APPROVAL_DEADLINE_S
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.report import case_decision_lines, event_line, postmortem_decision
from incident_commander.retrieval import HybridRanker
from incident_commander.world import SimWorld

from .approver_cli import CliResponder
from .scenarios import SCENARIOS


def _banner(approver: str) -> None:
    print(f"extension: llm=off approver={approver}")


def _run_cli(alert_id: str, deadline_s: float | None) -> int:
    """One alert with a human answering the page on the terminal."""
    world = SimWorld()
    try:
        alert = world.alert(alert_id)
    except KeyError:
        print(f"unknown alert: {alert_id} (known: {', '.join(world.alert_ids())})", file=sys.stderr)
        return 2
    deadline = APPROVAL_DEADLINE_S if deadline_s is None else deadline_s
    responder = CliResponder(deadline_s=deadline)
    ranker = HybridRanker(tuple(RUNBOOKS.values()))
    commander = Commander(world, ranker, responder, deadline_s=deadline)
    case = commander.run(alert)
    print()
    for event in case.trace.events:
        if event.kind in ("PAGE", "ESCALATE"):
            print(event_line(event))
    for line in case_decision_lines(case):
        print(line)
    print(postmortem_decision(alert_id, case.draft))
    _banner("cli")
    return 0


def _run_scenarios(name: str) -> int:
    names = list(SCENARIOS) if name == "all" else [name]
    ok = True
    for each in names:
        result = SCENARIOS[each]()
        print(f"== scenario {result.name} ==")
        for line in result.lines:
            print(line)
        print(f"scenario {result.name}: {'PASS' if result.passed else 'FAIL'}")
        ok = ok and result.passed
    return 0 if ok else 1


def _llm_arg(value: str) -> str:
    if value not in ("off", "local", "hosted"):
        raise argparse.ArgumentTypeError(f"invalid choice: {value!r} (choose from off)")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ic_plus")
    help_llm = "LLM mode (v1.1: off only)"
    parser.add_argument("--llm", type=_llm_arg, default="off", help=help_llm)
    # Also accepted after the subcommand; SUPPRESS keeps it from overriding a value given before.
    after = argparse.ArgumentParser(add_help=False)
    after.add_argument("--llm", type=_llm_arg, default=argparse.SUPPRESS, help=help_llm)
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser(
        "run", parents=[after], help="the graded pipeline, optionally with a human approver"
    )
    run_cmd.add_argument("alert_id", nargs="?")
    run_cmd.add_argument("--all", action="store_true", help="run all three demo alerts")
    run_cmd.add_argument("--approver", choices=("scripted", "cli"), default="scripted")
    run_cmd.add_argument("--deadline", type=float, help="page deadline in seconds (cli approver)")
    scenario = sub.add_parser("scenario", parents=[after], help="one extra scenario, or all")
    scenario.add_argument("name", choices=(*SCENARIOS, "all"))
    args = parser.parse_args(argv)
    if args.llm != "off":
        print(f"--llm {args.llm} is not available until v1.2; use --llm off", file=sys.stderr)
        return 2
    if args.command == "scenario":
        return _run_scenarios(args.name)
    if args.all == (args.alert_id is not None):
        parser.error("run needs exactly one of an alert id or --all")
    if args.deadline is not None and (args.approver != "cli" or args.deadline <= 0):
        parser.error("--deadline needs --approver cli and a positive number")
    if args.approver == "cli":
        if args.all:
            parser.error("--approver cli takes one alert id, not --all")
        return _run_cli(args.alert_id, args.deadline)
    code = cmd_run(None if args.all else args.alert_id)
    _banner("scripted")
    return code


if __name__ == "__main__":
    sys.exit(main())
