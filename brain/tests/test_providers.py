from __future__ import annotations

import pytest

from mira.config import settings
from mira.llm.router import LLMRouter
from mira.llm.subscription import (
    ClaudeCodeProvider,
    CodexProvider,
    _conversation_to_text,
)


@pytest.fixture
def router() -> LLMRouter:
    return LLMRouter()


def _no_clis(monkeypatch) -> None:
    monkeypatch.setattr(ClaudeCodeProvider, "available", staticmethod(lambda *_a: False))
    monkeypatch.setattr(CodexProvider, "available", staticmethod(lambda *_a: False))


def _both_clis(monkeypatch) -> None:
    monkeypatch.setattr(ClaudeCodeProvider, "available", staticmethod(lambda *_a: True))
    monkeypatch.setattr(CodexProvider, "available", staticmethod(lambda *_a: True))


# ---- privacy guard ----


def test_private_prompt_forces_local(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(settings, "provider", "auto")
    assert router.choose("my password is hunter2") == "local"
    assert router.choose("Мой секрет 123") == "local"


# ---- auto chain ----


def test_auto_prefers_api_key(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(settings, "provider", "auto")
    _both_clis(monkeypatch)
    assert router.choose("write an essay about the sea") == "cloud"


def test_auto_falls_to_claude_code_without_key(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "provider", "auto")
    monkeypatch.setattr(ClaudeCodeProvider, "available", staticmethod(lambda *_a: True))
    monkeypatch.setattr(CodexProvider, "available", staticmethod(lambda *_a: True))
    assert router.choose("hello there") == "claude_code"


def test_auto_falls_to_codex_when_only_codex(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "provider", "auto")
    monkeypatch.setattr(ClaudeCodeProvider, "available", staticmethod(lambda *_a: False))
    monkeypatch.setattr(CodexProvider, "available", staticmethod(lambda *_a: True))
    assert router.choose("hello there") == "codex"


def test_auto_falls_to_local_when_nothing(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    monkeypatch.setattr(settings, "provider", "auto")
    _no_clis(monkeypatch)
    assert router.choose("hello there") == "local"


# ---- explicit preference ----


def test_provider_subscription_prefers_claude_code(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(settings, "provider", "subscription")
    _both_clis(monkeypatch)
    assert router.choose("anything") == "claude_code"


def test_provider_subscription_uses_codex_if_no_claude(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider", "subscription")
    monkeypatch.setattr(ClaudeCodeProvider, "available", staticmethod(lambda *_a: False))
    monkeypatch.setattr(CodexProvider, "available", staticmethod(lambda *_a: True))
    assert router.choose("anything") == "codex"


def test_provider_explicit_codex(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider", "codex")
    assert router.choose("anything") == "codex"


def test_provider_explicit_local(router, monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider", "local")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")
    assert router.choose("anything") == "local"


# ---- hints override everything except privacy ----


def test_hint_aliases(router) -> None:
    assert router.choose("x", hint="subscription") == "claude_code"
    assert router.choose("x", hint="claude") == "claude_code"
    assert router.choose("x", hint="codex") == "codex"
    assert router.choose("x", hint="api") == "cloud"
    assert router.choose("x", hint="ollama") == "local"


# ---- conversation flattening ----


def test_conversation_to_text_plain() -> None:
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "how are you"},
    ]
    out = _conversation_to_text(msgs)
    assert "User: hi" in out
    assert "Assistant: hello" in out
    assert out.strip().endswith("User: how are you")


def test_conversation_to_text_blocks() -> None:
    msgs = [
        {"role": "user", "content": "open safari"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "doing it"},
            {"type": "tool_use", "name": "open_url"},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "content": "opened"},
        ]},
    ]
    out = _conversation_to_text(msgs)
    assert "doing it" in out
    assert "[used tool open_url]" in out
    assert "[tool result] opened" in out


# ---- availability shape ----


def test_availability_keys(monkeypatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    _no_clis(monkeypatch)
    avail = LLMRouter.availability()
    assert set(avail) == {"cloud", "claude_code", "codex", "local"}
    assert avail["cloud"] is False
    assert avail["local"] is True


# ---- provider labels ----


def test_provider_labels() -> None:
    assert ClaudeCodeProvider(model="opus").label == "claude-code:opus"
    assert ClaudeCodeProvider().label == "claude-code:default"
    assert CodexProvider(model="gpt-5-codex").label == "codex:gpt-5-codex"
    assert CodexProvider().label == "codex:default"
