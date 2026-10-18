"""A human answering the page on the terminal, against the same real deadline (PHASE5 FR-15)."""

from __future__ import annotations

import queue
import sys
import threading
from typing import TextIO

from incident_commander.approval import APPROVE

DENY = "deny"
_ANSWERS = {APPROVE: APPROVE, DENY: DENY}


class CliResponder:
    """`Responder` fed by a text stream (stdin by default).

    A reader thread turns each line into a queued answer, so `poll` never blocks and the
    gate's real deadline still decides. Only the exact words "approve" and "deny" (any
    case) count; anything else is ignored, so noise can never approve a fix. A closed
    stream is simply no answer.
    """

    def __init__(
        self,
        stream: TextIO | None = None,
        out: TextIO | None = None,
        deadline_s: float | None = None,
    ) -> None:
        self._stream = stream if stream is not None else sys.stdin
        self._out = out if out is not None else sys.stdout
        self._deadline_s = deadline_s
        self._lines: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._prompted: set[str] = set()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            while True:
                line = self._stream.readline()
                if line == "":  # EOF
                    return
                self._lines.put(line)
        except (OSError, ValueError):  # stream closed under us: treat as no more answers
            return

    def _prompt(self, target: str) -> None:
        if target in self._prompted:
            return
        self._prompted.add(target)
        limit = f" (deadline {self._deadline_s:g}s)" if self._deadline_s is not None else ""
        print(f"PAGE {target}: approve or deny?{limit} > ", end="", file=self._out, flush=True)

    def poll(self, target: str, elapsed_s: float) -> str | None:
        self._prompt(target)
        while True:
            try:
                line = self._lines.get_nowait()
            except queue.Empty:
                return None
            answer = _ANSWERS.get(line.strip().lower())
            if answer is not None:
                print(answer, file=self._out, flush=True)
                return answer
