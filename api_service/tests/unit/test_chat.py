from __future__ import annotations

from email.message import Message
from io import BytesIO
from typing import Any
from urllib import error

import pytest

from api_service import chat
from api_service.chat import GenerationError, OpenAIChatCompletionClient


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_openai_chat_client_posts_chat_completions_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        captured["timeout"] = timeout
        return FakeResponse(b'{"choices":[{"message":{"content":"Grounded answer [1]."}}]}')

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    answer = OpenAIChatCompletionClient(
        "http://ollama:11434",
        model_name="gemma3:4b",
        timeout_seconds=120,
    ).complete([{"role": "user", "content": "hello"}])

    assert answer == "Grounded answer [1]."
    assert captured["url"] == "http://ollama:11434/v1/chat/completions"
    assert captured["timeout"] == 120
    assert b'"model": "gemma3:4b"' in captured["body"]
    assert b'"stream": false' in captured["body"]
    assert "Authorization" not in captured["headers"]


def test_openai_chat_client_sends_configured_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        captured["headers"] = dict(req.header_items())
        return FakeResponse(b'{"choices":[{"message":{"content":"Grounded answer [1]."}}]}')

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    OpenAIChatCompletionClient(
        "http://ollama:11434",
        model_name="gemma3:4b",
        timeout_seconds=120,
        api_key="secret-token",
    ).complete([{"role": "user", "content": "hello"}])

    assert captured["headers"]["Authorization"] == "Bearer secret-token"


def test_openai_chat_client_rejects_invalid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(b"<html>not json</html>")

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    with pytest.raises(GenerationError, match="invalid JSON response"):
        OpenAIChatCompletionClient("http://ollama", "gemma3:4b", 120).complete([])


def test_openai_chat_client_rejects_missing_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(b'{"choices":[]}')

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    with pytest.raises(GenerationError, match="missing choices"):
        OpenAIChatCompletionClient("http://ollama", "gemma3:4b", 120).complete([])


def test_openai_chat_client_handles_non_utf8_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        raise error.HTTPError(
            url="http://ollama/v1/chat/completions",
            code=502,
            msg="Bad Gateway",
            hdrs=Message(),
            fp=BytesIO(b"\xff"),
        )

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    with pytest.raises(GenerationError, match="<non-UTF-8 response body>"):
        OpenAIChatCompletionClient("http://ollama", "gemma3:4b", 120).complete([])
