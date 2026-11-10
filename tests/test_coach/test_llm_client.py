"""Unit tests for the OpenAI wrapper (no network: the SDK call is replaced)."""
from types import SimpleNamespace

import pytest

from api.app.coach import llm as llm_module
from api.app.coach.llm import LLMError, OpenAIClient


def _response(text, prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


@pytest.fixture
def client_and_calls(monkeypatch):
    c = OpenAIClient(api_key="sk-test", model="gpt-4o-mini", timeout_s=5, max_retries=0)
    calls = []

    def install(result):
        def fake_create(**kwargs):
            calls.append(kwargs)
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(c._client.chat.completions, "create", fake_create)
    return c, calls, install


def test_complete_json_parses_and_requests_json_mode(client_and_calls):
    c, calls, install = client_and_calls
    install(_response('{"insights": ["a"]}'))
    data, usage = c.complete_json("sys", "user", 100)
    assert data == {"insights": ["a"]} and usage.tokens_in == 10 and usage.tokens_out == 5
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["model"] == "gpt-4o-mini" and calls[0]["max_completion_tokens"] == 100


def test_invalid_json_raises(client_and_calls):
    c, _, install = client_and_calls
    install(_response("not json"))
    with pytest.raises(LLMError):
        c.complete_json("sys", "user", 100)


def test_sdk_errors_become_llm_error(client_and_calls):
    c, _, install = client_and_calls
    install(TimeoutError("boom"))
    with pytest.raises(LLMError):
        c.chat([{"role": "user", "content": "hi"}], 50)


def test_chat_returns_text(client_and_calls):
    c, calls, install = client_and_calls
    install(_response("  Hello  "))
    text, _ = c.chat([{"role": "user", "content": "hi"}], 50)
    assert text == "Hello" and "response_format" not in calls[0]


def test_get_llm_is_none_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_module.get_llm() is None
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert isinstance(llm_module.get_llm(), OpenAIClient)
