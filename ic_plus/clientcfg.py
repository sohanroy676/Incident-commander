"""Builds the LLM client from flags and the dotenv values. The key never leaves this package."""

from __future__ import annotations

from collections.abc import Mapping

from .envfile import load_env
from .llm_client import LLMClient

LOCAL_URL = "http://localhost:11434/v1"


def build_client(
    mode: str, url: str | None, model: str | None, env: Mapping[str, str]
) -> tuple[LLMClient | None, list[str]]:
    """Flags beat the dotenv values beat the local default. (None, missing) means "not configured"."""
    base = url or env.get("LLM_BASE_URL") or (LOCAL_URL if mode == "local" else "")
    name = model or env.get("LLM_MODEL") or ""
    key = env.get("LLM_API_KEY") if mode == "hosted" else None  # local servers ignore keys
    missing = [n for n, v in (("url", base), ("model", name)) if not v]
    if mode == "hosted" and not key:
        missing.append("key")
    if missing:
        return None, missing
    return LLMClient(base, name, key), []


def client_from_env(mode: str) -> tuple[LLMClient | None, list[str]]:
    """The configured client for "local" or "hosted"; callers pass no URL, model or key."""
    return build_client(mode, None, None, load_env())
