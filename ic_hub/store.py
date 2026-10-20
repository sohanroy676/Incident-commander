"""Optional local persistence for the hub: run history as JSON files and a hash-chained audit log.

Both live under one directory the operator names with `--data-dir`; without it nothing is written.
File names are built only from run ids the hub generated (16 hex characters), never from request
text, and every read re-checks the id before touching the disk.

The audit log is append-only JSONL. Each line carries `prev` (the previous line's hash) and `hash`
(SHA-256 over `prev` and the line's other fields). That makes an edit, deletion or reordering in
the middle of the file detectable. It is tamper-evident only: it is not signed, has no identity,
and removing lines from the end cannot be detected without keeping the head hash somewhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

GENESIS = "0" * 64
RUN_ID = re.compile(r"[0-9a-f]{16}")
MAX_HISTORY = 200
MAX_RECORD_BYTES = 1_048_576
MAX_AUDIT_BYTES = 8 * 1024 * 1024
MAX_DETAIL_CHARS = 200
MAX_DETAIL_FIELDS = 12
SIMILAR_LIMIT = 5
AUDIT_TAIL = 50


def _printable(value: object, limit: int = MAX_DETAIL_CHARS) -> str:
    text = "".join(c if c.isprintable() else " " for c in str(value))
    return text[:limit]


def _digest(prev: str, body: dict[str, object]) -> str:
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()


class Store:
    """History and audit under `directory`. One instance per server; thread-safe."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self._runs = self.directory / "runs"
        self._audit = self.directory / "audit.jsonl"
        self._runs.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.max_runs = MAX_HISTORY
        self.max_audit_bytes = MAX_AUDIT_BYTES
        self.audit_full = False
        self.last_error: str | None = None
        self._seq, self._head = self._load_head()

    # -- run history --------------------------------------------------------

    def _run_path(self, run_id: object) -> Path | None:
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            return None
        return self._runs / f"{run_id}.json"

    def save_run(self, record: dict[str, object]) -> bool:
        """Write one run record atomically; False (with `last_error`) if it was not stored."""
        path = self._run_path(record.get("run_id"))
        if path is None:
            return False
        try:
            data = json.dumps({**record, "saved_at": time.time()}, allow_nan=False).encode("utf-8")
            if len(data) > MAX_RECORD_BYTES:
                self.last_error = "run record larger than the size cap; not stored"
                return False
            with self._lock:
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, path)
                self._prune()
            return True
        except (OSError, ValueError) as exc:
            self.last_error = f"{type(exc).__name__}: could not store the run"
            return False

    def _prune(self) -> None:
        files = sorted(self._runs.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for old in files[: max(0, len(files) - self.max_runs)]:
            old.unlink(missing_ok=True)

    def get_run(self, run_id: object) -> dict[str, object] | None:
        path = self._run_path(run_id)
        if path is None:
            return None
        try:
            if path.stat().st_size > MAX_RECORD_BYTES:
                return None
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(record, dict) or record.get("run_id") != run_id:
            return None
        return record

    def list_runs(self) -> list[dict[str, object]]:
        """Summaries, newest first. Unreadable or mismatched files are skipped."""
        rows = []
        for path in self._runs.glob("*.json"):
            record = self.get_run(path.stem)
            if record is None:
                continue
            rows.append({k: v for k, v in record.items() if k != "result"})
        rows.sort(key=lambda r: float(r.get("saved_at") or 0.0), reverse=True)  # type: ignore[arg-type]
        return rows

    def similar(self, run_id: str, service: object, runbook: object) -> list[dict[str, object]]:
        """Earlier runs on the same service or with the same runbook. Advisory text for a human."""
        found = []
        for row in self.list_runs():
            if row.get("run_id") == run_id:
                continue
            reasons = []
            if service and row.get("service") == service:
                reasons.append("same service")
            if runbook and row.get("runbook") == runbook:
                reasons.append("same runbook")
            if reasons:
                found.append({**row, "reason": " and ".join(reasons)})
        return found[:SIMILAR_LIMIT]

    # -- audit log ----------------------------------------------------------

    def _load_head(self) -> tuple[int, str]:
        seq, head = 0, GENESIS
        try:
            with self._audit.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        entry = json.loads(line)
                        seq, head = int(entry["seq"]), str(entry["hash"])
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            pass
        return seq, head

    def append(self, event: str, **detail: object) -> bool:
        """Add one audit entry. Details are short printable strings; False if it was not written."""
        fields = {
            _printable(k, 40): _printable(v) for k, v in list(detail.items())[:MAX_DETAIL_FIELDS]
        }
        with self._lock:
            try:
                if self._audit.exists() and self._audit.stat().st_size > self.max_audit_bytes:
                    self.audit_full = True
                    return False
                body: dict[str, object] = {
                    "seq": self._seq + 1,
                    "ts": round(time.time(), 3),
                    "event": _printable(event, 40),
                    "detail": fields,
                    "prev": self._head,
                }
                entry = {**body, "hash": _digest(self._head, body)}
                with self._audit.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(entry, sort_keys=True) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                self.last_error = f"{type(exc).__name__}: could not append to the audit log"
                return False
            self._seq, self._head = entry["seq"], entry["hash"]  # type: ignore[assignment]
            return True

    def verify(self) -> dict[str, object]:
        """Recompute the chain. `ok` is False at the first line that does not fit."""
        prev, count = GENESIS, 0
        problem: str | None = None
        bad_seq: int | None = None
        try:
            lines = self._audit.read_text(encoding="utf-8").split("\n")
        except FileNotFoundError:
            lines = []
        except (OSError, UnicodeDecodeError):
            return self._verdict(False, 0, None, "the audit log cannot be read", GENESIS)
        if lines and lines[-1] == "":
            lines.pop()
        for number, line in enumerate(lines, start=1):
            try:
                entry = json.loads(line)
                body = {k: v for k, v in entry.items() if k != "hash"}
                good = (
                    entry["seq"] == number
                    and entry["prev"] == prev
                    and entry["hash"] == _digest(prev, body)
                )
            except (ValueError, KeyError, TypeError, AttributeError):
                good = False
            if not good:
                problem, bad_seq = "chain broken: line does not match its predecessor", number
                break
            prev, count = entry["hash"], number
        return self._verdict(problem is None, count, bad_seq, problem, prev)

    def _verdict(
        self, ok: bool, entries: int, bad_seq: int | None, reason: str | None, head: str
    ) -> dict[str, object]:
        return {
            "ok": ok,
            "entries": entries,
            "first_bad_line": bad_seq,
            "reason": reason,
            "head": head,
            "audit_full": self.audit_full,
            "note": "tamper-evident only: not signed, and a removed tail cannot be detected",
        }

    def tail(self, limit: int = AUDIT_TAIL) -> list[dict[str, object]]:
        try:
            lines = self._audit.read_text(encoding="utf-8").splitlines()[-limit:]
        except (OSError, UnicodeDecodeError):
            return []
        entries = []
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries
