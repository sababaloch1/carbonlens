"""
S4 - LLM access layer.

Everything that talks to OpenAI goes through `LLMClient`, so the rest of the
coach never imports the SDK directly. Tests replace it with a fake
(NFR-4.08), and when no API key is configured `get_llm()` returns None so the
coach falls back to deterministic logic instead of failing (NFR-4.01).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from .config import get_settings

logger = logging.getLogger("carbonlens.coach")


class LLMError(Exception):
    """Raised when the model cannot be reached or returns unusable output."""


@dataclass
class LLMUsage:
    tokens_in: int = 0
    tokens_out: int = 0


class LLMClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, max_tokens: int) -> tuple[dict, LLMUsage]:
        ...

    def chat(self, messages: list[dict], max_tokens: int) -> tuple[str, LLMUsage]:
        ...


class OpenAIClient:
    """Thin wrapper around the OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str, timeout_s: float, max_retries: int):
        from openai import OpenAI  # imported lazily so tests never need the network

        self.model = model
        self._client = OpenAI(api_key=api_key, timeout=timeout_s, max_retries=max_retries)

    def _create(self, messages: list[dict], max_tokens: int, json_mode: bool):
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": 0.3,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            return self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # network, auth, rate limit, timeout ...
            logger.warning("OpenAI call failed: %s", exc.__class__.__name__)
            raise LLMError(f"OpenAI request failed: {exc.__class__.__name__}") from exc

    @staticmethod
    def _usage(resp) -> LLMUsage:
        u = getattr(resp, "usage", None)
        if not u:
            return LLMUsage()
        return LLMUsage(tokens_in=u.prompt_tokens or 0, tokens_out=u.completion_tokens or 0)

    def complete_json(self, system: str, user: str, max_tokens: int) -> tuple[dict, LLMUsage]:
        resp = self._create(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens,
            json_mode=True,
        )
        text = resp.choices[0].message.content or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError("Model returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("Model returned JSON that is not an object")
        return data, self._usage(resp)

    def chat(self, messages: list[dict], max_tokens: int) -> tuple[str, LLMUsage]:
        resp = self._create(messages, max_tokens, json_mode=False)
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise LLMError("Model returned an empty answer")
        return text, self._usage(resp)


def get_llm() -> LLMClient | None:
    """FastAPI dependency. Returns None when OpenAI is not configured."""
    s = get_settings()
    if not s.openai_api_key:
        return None
    return OpenAIClient(s.openai_api_key, s.model, s.timeout_s, s.max_retries)
