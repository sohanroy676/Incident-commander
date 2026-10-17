"""Definition-of-Done gates. v0.1 ships G1 (purity); trace, repro and all follow in v1.0."""

from __future__ import annotations

import argparse
import ast
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
    args = parser.parse_args(argv)
    return purity(args.root)


if __name__ == "__main__":
    sys.exit(main())
