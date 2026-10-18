"""Small stdlib parser for the repo-root .env file. The only place ic_plus reads it.

It never reads process variables and never prints values.
"""

from __future__ import annotations

from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE lines; blank lines and # comments skipped; optional `export ` and quotes."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(path: Path | None = None) -> dict[str, str]:
    """Values from the .env file; a missing or unreadable file is just an empty mapping."""
    try:
        return parse_env((path or ENV_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}
