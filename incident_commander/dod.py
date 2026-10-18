"""Definition-of-Done gates G1-G6: purity | trace <file> | repro | all."""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "incident_commander"
ALLOWED_IMPORTS = frozenset(sys.stdlib_module_names) | {"sklearn", PACKAGE}
# stdlib modules that would give the graded build network access or a numpy dependency
FORBIDDEN_IMPORTS = frozenset({"socket", "urllib", "http", "requests", "numpy", "ic_plus"})
FORBIDDEN_ENV_NAMES = frozenset({"environ", "getenv", "getenvb"})


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _check_import(module: str, path: str, line: int, out: list[Violation]) -> None:
    top = module.split(".")[0]
    if top in FORBIDDEN_IMPORTS:
        out.append(Violation(path, line, f"forbidden import: {top}"))
    elif top not in ALLOWED_IMPORTS:
        out.append(Violation(path, line, f"import outside stdlib + scikit-learn: {top}"))


def scan_source(source: str, path: str) -> list[Violation]:
    found: list[Violation] = []
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_import(alias.name, path, node.lineno, found)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the package
                continue
            _check_import(node.module or "", path, node.lineno, found)
            if (node.module or "").split(".")[0] == "os":
                for alias in node.names:
                    if alias.name in FORBIDDEN_ENV_NAMES:
                        found.append(
                            Violation(
                                path,
                                node.lineno,
                                f"environment access: os.{alias.name}",
                            )
                        )
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ENV_NAMES:
            found.append(Violation(path, node.lineno, f"environment access: .{node.attr}"))
        elif isinstance(node, ast.Name) and node.id == "ic_plus":
            found.append(Violation(path, node.lineno, "reference to ic_plus"))
    return found


def scan(root: Path) -> tuple[int, list[Violation]]:
    """Scan every .py file under root. Returns (modules scanned, violations)."""
    files = sorted(root.rglob("*.py"))
    violations: list[Violation] = []
    for f in files:
        violations.extend(scan_source(f.read_text(encoding="utf-8"), str(f)))
    return len(files), violations


def purity(root: Path | None = None) -> int:
    root = root or Path(__file__).resolve().parent
    scanned, violations = scan(root)
    if violations:
        print(f"G1 purity: FAIL  (modules scanned: {scanned})")
        for v in violations:
            print(f"  {v}")
        return 1
    print(f"G1 purity: PASS  (modules scanned: {scanned}; allowed imports: stdlib + sklearn)")
    return 0


HEADERS = (
    "== M1 SIGNAL INGESTION ==",
    "== M2 RUNBOOK GROUNDING ==",
    "== M3 INVESTIGATION ==",
    "== M4 BLAST-RADIUS CLASSIFICATION ==",
    "== M5 TIME-BOXED APPROVAL ==",
    "== M6 VERIFIED RESOLUTION ==",
    "== M7 POSTMORTEM DRAFT ==",
    "== M8 EVALUATION ==",
)
# Acceptance values (Outcomes 1-9) that must appear verbatim as whole lines in the trace.
REQUIRED_LINES = (
    "DECISION verdict alert=ALRT-9001 verdict=matched runbook=RB-101 rounds=3",
    "DECISION verdict alert=ALRT-9002 verdict=matched runbook=RB-102 rounds=3",
    (
        "DECISION verdict alert=ALRT-9003 verdict=no_confident_match runbook=none rounds=4"
        " reason=all_refuted"
    ),
    (
        "DECISION page_check case=after_sleep window_s=0.3 escalated=True"
        " from=engineer-priya to=engineer-devon"
    ),
    "DECISION approval alert=ALRT-9001 escalated=True approved_by=engineer-devon",
    "DECISION verify alert=ALRT-9002 status=resolved verified=True baseline_ms=180 observed_ms=195",
    (
        "DECISION verify alert=ALRT-9002 variant=fix_fails status=reopened verified=False"
        " baseline_ms=180 observed_ms=3900"
        ' reason="remediation ran but did not resolve the signal"'
    ),
    "DECISION handoff alert=ALRT-9003 reason=no_confident_match",
    "DECISION golden_summary passed=3 total=3",
)
REQUIRED_PATTERNS = (
    (
        "attack unchanged",
        re.compile(r"^DECISION attack alert=ALRT-9001 .* unchanged=True$", re.MULTILINE),
    ),
    (
        "postmortem drafted with no side effects",
        re.compile(
            r"^DECISION postmortem alert=ALRT-9001 notified=\[\] published=False$", re.MULTILINE
        ),
    ),
)
_EXECUTE = re.compile(
    r"^DECISION execute alert=ALRT-9002 action=restart_service status=(\S+) execution_id=(\S+)$",
    re.MULTILINE,
)
_STAMP = re.compile(r"^\[t\+\d+(?:\.\d+)?s\] ")
_ELAPSED = re.compile(r" elapsed_s=\S+")
REPO_ROOT = Path(__file__).resolve().parent.parent


def check_trace(text: str) -> list[str]:
    """Problems found in a run trace; empty means it satisfies the output contract (G5)."""
    problems: list[str] = []
    lines = text.splitlines()
    last = -1
    for header in HEADERS:
        at = [i for i, line in enumerate(lines) if line == header]
        if len(at) != 1:
            problems.append(f"header {header!r} appears {len(at)} times, expected 1")
        elif at[0] < last:
            problems.append(f"header {header!r} is out of order")
        else:
            last = at[0]
    for required in REQUIRED_LINES:
        if required not in lines:
            problems.append(f"missing line: {required}")
    for label, pattern in REQUIRED_PATTERNS:
        if not pattern.search(text):
            problems.append(f"missing: {label}")
    executed = _EXECUTE.findall(text)
    if [status for status, _ in executed] != ["executed", "already_executed"]:
        problems.append("ALRT-9002 must execute once, then report already_executed")
    elif executed[0][1] != executed[1][1]:
        problems.append("ALRT-9002 retry returned a different execution_id")
    return problems


def trace(path: Path) -> int:
    problems = check_trace(path.read_text(encoding="utf-8"))
    if problems:
        print(f"G5 trace: FAIL  ({path})")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"G5 trace: PASS  ({path}: 8 headers, {len(REQUIRED_LINES)} acceptance lines)")
    return 0


def normalise(text: str) -> list[str]:
    """Strip the wall-clock parts of a trace so two runs can be compared line by line."""
    return [_ELAPSED.sub("", _STAMP.sub("", line)) for line in text.splitlines()]


def _python(*args: str) -> subprocess.CompletedProcess[str]:
    """One fresh interpreter in the repo root, as a user would start it."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def run_all_once() -> subprocess.CompletedProcess[str]:
    return _python("-m", PACKAGE, "run", "--all")


def repro(first: str | None = None) -> int:
    """G6: two fresh runs give identical normalised output. `first` reuses an earlier run."""
    a = first if first is not None else run_all_once().stdout
    b = run_all_once().stdout
    left, right = normalise(a), normalise(b)
    if not left or left != right:
        print("G6 repro: FAIL")
        for i, (x, y) in enumerate(zip(left, right), start=1):
            if x != y:
                print(f"  line {i}: {x!r} != {y!r}")
                break
        else:
            print(f"  line counts differ: {len(left)} vs {len(right)}")
        return 1
    print(f"G6 repro: PASS  ({len(left)} lines identical after stripping timestamps)")
    return 0


def _unittest(module: str) -> tuple[bool, str]:
    proc = _python("-m", "unittest", module)
    last = (proc.stderr.strip().splitlines() or ["no output"])[-1]
    return proc.returncode == 0, f"{module}: {last}"


def run_gates() -> list[tuple[str, bool, str]]:
    """Run G1-G6; each result is (gate, passed, detail)."""
    results = [("G1 purity", purity() == 0, "AST scan of the package")]
    for gate, module in (
        ("G2 invariants", "tests.test_invariants"),
        ("G3 outcomes", "tests.test_outcomes"),
    ):
        ok, detail = _unittest(module)
        results.append((gate, ok, detail))
    evaluate = _python("-m", PACKAGE, "evaluate")
    ok = evaluate.returncode == 0 and "DECISION golden_summary passed=3 total=3" in evaluate.stdout
    results.append(("G4 evaluation", ok, "golden 3/3 and attack unchanged"))
    demo = run_all_once()  # a fresh run, never a stale traces/run.txt
    problems = check_trace(demo.stdout) if demo.returncode == 0 else ["run --all failed"]
    results.append(("G5 trace", not problems, "; ".join(problems) or "headers and values present"))
    results.append(("G6 repro", repro(demo.stdout) == 0, "two fresh runs, normalised"))
    return results


def run_everything() -> int:
    results = run_gates()
    print()
    for gate, ok, detail in results:
        print(f"{gate:<15}{'PASS' if ok else 'FAIL'}  {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m incident_commander.dod")
    sub = parser.add_subparsers(dest="gate", required=True)
    p = sub.add_parser("purity", help="G1: import and environment purity scan")
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="directory to scan (default: this package)",
    )
    t = sub.add_parser("trace", help="G5: check a saved run trace against the output contract")
    t.add_argument("file", type=Path)
    sub.add_parser("repro", help="G6: two fresh runs compare equal after normalisation")
    sub.add_parser("all", help="G1-G6 in one table")
    args = parser.parse_args(argv)
    if args.gate == "purity":
        return purity(args.root)
    if args.gate == "trace":
        return trace(args.file)
    if args.gate == "repro":
        return repro()
    return run_everything()


if __name__ == "__main__":
    sys.exit(main())
