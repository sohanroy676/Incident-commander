"""Provider-agnostic chat client: OpenAI-compatible POST {base_url}/chat/completions.

`chat` never raises: every failure comes back as LLMReply(ok=False, error=...). The API key is
sent only as a bearer header, is never part of repr/str, and is scrubbed from error text.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 20.0
MAX_REPLY_BYTES = 1_000_000
USER_AGENT = "incident-commander-ic-plus/1.0"


@dataclass(frozen=True)
class LLMReply:
    ok: bool
    text: str = ""
    error: str = ""
    model: str = ""


class LLMClient:
    def __init__(
        self, base_url: str, model: str, key: str | None, timeout_s: float = DEFAULT_TIMEOUT_S
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._key = key or None

    def __repr__(self) -> str:
        return f"LLMClient(base_url={self.base_url!r}, model={self.model!r}, key=<hidden>)"

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "<key>") if self._key else text

    def _fail(self, error: str) -> LLMReply:
        return LLMReply(ok=False, error=self._scrub(error)[:200], model=self.model)

    def chat(self, messages: list[dict], json_mode: bool = True) -> LLMReply:
        try:
            return self._chat(messages, json_mode)
        except Exception as exc:  # noqa: BLE001 - the contract is "never raises"
            return self._fail(f"{type(exc).__name__}: {exc}")

    def _chat(self, messages: list[dict], json_mode: bool) -> LLMReply:
        payload: dict = {"model": self.model, "messages": messages, "temperature": 0}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        # Hosted providers behind Cloudflare (Groq) reject the default Python-urllib agent with 403.
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = response.read(MAX_REPLY_BYTES)
        except urllib.error.HTTPError as exc:
            return self._fail(f"http {exc.code}")
        except urllib.error.URLError as exc:
            return self._fail(f"unreachable: {exc.reason}")
        try:
            text = json.loads(body)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return self._fail("malformed response")
        if not isinstance(text, str):
            return self._fail("malformed response")
        return LLMReply(ok=True, text=text, model=self.model)
