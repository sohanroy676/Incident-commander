"""CLI: python -m ic_plus run <ALERT>|--all | explain <ALERT> <question> | evaluate | scenario <name>|all
[--llm off|local|hosted]."""

from __future__ import annotations

import argparse
import contextlib
import io
import sys

from incident_commander.__main__ import cmd_evaluate, cmd_run
from incident_commander.commander import Commander
from incident_commander.config import APPROVAL_DEADLINE_S
from incident_commander.fixtures.runbooks import RUNBOOKS
from incident_commander.report import case_decision_lines, event_line, postmortem_decision
from incident_commander.retrieval import HybridRanker
from incident_commander.world import SimWorld

from .approver_cli import CliResponder
from .envfile import load_env
from .explainer import FALLBACK_LABEL, clean_question, explain, template_answer
from .llm_client import LLMClient
from .narrator import UNAVAILABLE_LINE, build_facts, narrate
from .scenarios import SCENARIOS, _commander
from .x3 import ROLES_LINE, advised_orders, advised_orders_of, run_x3

LOCAL_URL = "http://localhost:11434/v1"


def _banner(llm: str, approver: str) -> None:
    print(f"extension: llm={llm} approver={approver}")


def _make_client(args: argparse.Namespace) -> LLMClient | None:
    """Flags beat the dotenv file beat the local default. None means "not configured" (fallback)."""
    env = load_env()
    url = args.llm_url or env.get("LLM_BASE_URL") or (LOCAL_URL if args.llm == "local" else "")
    model = args.model or env.get("LLM_MODEL") or ""
    key = env.get("LLM_API_KEY") if args.llm == "hosted" else None  # local servers ignore keys
    if not url or not model or (args.llm == "hosted" and not key):
        missing = [n for n, v in (("url", url), ("model", model)) if not v]
        if args.llm == "hosted" and not key:
            missing.append("key")
        print(f"llm: not configured (missing {', '.join(missing)})", file=sys.stderr)
        return None
    return LLMClient(url, model, key)


class _Narration:
    """Runs the narrator per case; once the server is unavailable the rest skip the calls."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.on = args.llm != "off"
        self.client = _make_client(args) if self.on else None
        self.down = self.on and self.client is None

    def show(self, case) -> None:
        if not self.on:
            return
        print(f"narrator: alert={case.alert.alert_id}")
        if self.down:
            print(UNAVAILABLE_LINE)
            return
        outcome = narrate(case, self.client)
        self.down = outcome.status == "unavailable"
        for line in outcome.lines:
            print(line)


def _run_cli(alert_id: str, deadline_s: float | None, args: argparse.Namespace) -> int:
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
    _Narration(args).show(case)
    _banner(args.llm, "cli")
    return 0


def _explain(args: argparse.Namespace) -> int:
    """Answer a question about one finished case; the LLM text is labelled and never a decision."""
    world = SimWorld()
    if args.alert_id not in world.alert_ids():
        print(
            f"unknown alert: {args.alert_id} (known: {', '.join(world.alert_ids())})",
            file=sys.stderr,
        )
        return 2
    question = clean_question(args.question)
    if not question:
        print("explain needs a non-empty question", file=sys.stderr)
        return 2
    case = _commander(SimWorld()).run(world.alert(args.alert_id))
    if args.llm == "off":
        print(f"{FALLBACK_LABEL} {template_answer(build_facts(case))}")
    else:
        for line in explain(case, question, _make_client(args)).lines:
            print(line)
    _banner(args.llm, "scripted")
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    """The graded M8 as is, then (LLM on) X3: all roles on every fixture, decisions compared."""
    baseline = io.StringIO()
    with contextlib.redirect_stdout(baseline):
        code = cmd_evaluate()
    print(baseline.getvalue(), end="")
    if args.llm == "off":
        print("llm: off")
        _banner(args.llm, "scripted")
        return code
    rows = run_x3(_make_client(args))
    for row in rows:
        print(row.line())
    changed = sum(not row.identical for row in rows)
    advised = io.StringIO()
    with advised_orders(advised_orders_of(rows)), contextlib.redirect_stdout(advised):
        advised_code = cmd_evaluate()
    if advised.getvalue() != baseline.getvalue() or advised_code != code:
        changed += 1  # the graded evaluation itself differs under the advised orders
    print(ROLES_LINE.format(changed=changed))
    _banner(args.llm, "scripted")
    return 0 if code == 0 and changed == 0 else 1


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
        raise argparse.ArgumentTypeError(
            f"invalid choice: {value!r} (choose from off, local, hosted)"
        )
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ic_plus")
    help_llm = "LLM mode: off (default), local or hosted"
    parser.add_argument("--llm", type=_llm_arg, default="off", help=help_llm)
    # Also accepted after the subcommand; SUPPRESS keeps it from overriding a value given before.
    after = argparse.ArgumentParser(add_help=False)
    after.add_argument("--llm", type=_llm_arg, default=argparse.SUPPRESS, help=help_llm)
    for each in (parser, after):
        default = None if each is parser else argparse.SUPPRESS
        each.add_argument("--llm-url", default=default, help="OpenAI-compatible base URL")
        each.add_argument("--model", default=default, help="model name")
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser(
        "run", parents=[after], help="the graded pipeline, optionally with a human approver"
    )
    run_cmd.add_argument("alert_id", nargs="?")
    run_cmd.add_argument("--all", action="store_true", help="run all three demo alerts")
    run_cmd.add_argument("--approver", choices=("scripted", "cli"), default="scripted")
    run_cmd.add_argument("--deadline", type=float, help="page deadline in seconds (cli approver)")
    explain_cmd = sub.add_parser(
        "explain", parents=[after], help="ask why the agent did what it did on one alert"
    )
    explain_cmd.add_argument("alert_id")
    explain_cmd.add_argument("question")
    sub.add_parser("evaluate", parents=[after], help="M8 plus X3: decisions unchanged with LLM on")
    scenario = sub.add_parser("scenario", parents=[after], help="one extra scenario, or all")
    scenario.add_argument("name", choices=(*SCENARIOS, "all"))
    args = parser.parse_args(argv)
    if args.command == "scenario":
        return _run_scenarios(args.name)
    if args.command == "explain":
        return _explain(args)
    if args.command == "evaluate":
        return _evaluate(args)
    if args.all == (args.alert_id is not None):
        parser.error("run needs exactly one of an alert id or --all")
    if args.deadline is not None and (args.approver != "cli" or args.deadline <= 0):
        parser.error("--deadline needs --approver cli and a positive number")
    if args.approver == "cli":
        if args.all:
            parser.error("--approver cli takes one alert id, not --all")
        return _run_cli(args.alert_id, args.deadline, args)
    code = cmd_run(None if args.all else args.alert_id)
    if args.llm != "off" and code != 2:
        narration = _Narration(args)
        world = SimWorld()
        # The narrator reads separate, identical deterministic cases: cmd_run prints, never returns.
        for known in world.alert_ids() if args.all else (args.alert_id,):
            narration.show(_commander(SimWorld()).run(world.alert(known)))
    _banner(args.llm, "scripted")
    return code


if __name__ == "__main__":
    sys.exit(main())
