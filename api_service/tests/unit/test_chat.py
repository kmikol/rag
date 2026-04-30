from __future__ import annotations

from email.message import Message
from io import BytesIO
from typing import Any, Literal
from urllib import error

import pytest

from api_service import chat
from api_service.chat import (
    AnswerabilityConfig,
    GenerationError,
    GenerationOptions,
    GoogleGenerateContentLLMClient,
    OpenAICompatibleLLMClient,
    assess_answerability,
)
from shared.schemas import RetrievalSourceScore, SearchResult


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

    answer = OpenAICompatibleLLMClient(
        "http://llm.example/v1/chat/completions",
        model_name="gemma3:4b",
        timeout_seconds=120,
    ).complete(
        [{"role": "user", "content": "hello"}],
        GenerationOptions(temperature=0.2, max_tokens=64),
    )

    assert answer == "Grounded answer [1]."
    assert captured["url"] == "http://llm.example/v1/chat/completions"
    assert captured["timeout"] == 120
    assert b'"model": "gemma3:4b"' in captured["body"]
    assert b'"stream": false' in captured["body"]
    assert b'"temperature": 0.2' in captured["body"]
    assert b'"max_tokens": 64' in captured["body"]
    assert "Authorization" not in captured["headers"]


def test_openai_chat_client_sends_configured_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        captured["headers"] = dict(req.header_items())
        return FakeResponse(b'{"choices":[{"message":{"content":"Grounded answer [1]."}}]}')

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    OpenAICompatibleLLMClient(
        "http://llm.example/v1/chat/completions",
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
        OpenAICompatibleLLMClient(
            "http://llm.example/v1/chat/completions", "gemma3:4b", 120
        ).complete([])


def test_openai_chat_client_rejects_missing_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(b'{"choices":[]}')

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    with pytest.raises(GenerationError, match="missing choices"):
        OpenAICompatibleLLMClient(
            "http://llm.example/v1/chat/completions", "gemma3:4b", 120
        ).complete([])


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
        OpenAICompatibleLLMClient(
            "http://llm.example/v1/chat/completions", "gemma3:4b", 120
        ).complete([])


def test_google_generate_content_client_posts_native_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int) -> FakeResponse:
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data
        captured["timeout"] = timeout
        return FakeResponse(
            b'{"candidates":[{"content":{"parts":[{"text":"Grounded answer [1]."}]}}]}'
        )

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    answer = GoogleGenerateContentLLMClient(
        endpoint_url="https://generativelanguage.googleapis.com/v1beta",
        model_name="gemma-4-31b-it",
        timeout_seconds=180,
        api_key="secret-token",
    ).complete(
        [
            {"role": "system", "content": "Answer from context."},
            {"role": "user", "content": "Question"},
        ],
        GenerationOptions(temperature=0.1, max_tokens=64),
    )

    assert answer == "Grounded answer [1]."
    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent"
    )
    assert captured["headers"]["X-goog-api-key"] == "secret-token"
    assert captured["timeout"] == 180
    payload = captured["body"]
    assert b'"systemInstruction"' in payload
    assert b'"contents"' in payload
    assert b'"maxOutputTokens": 64' in payload


def test_google_generate_content_client_rejects_missing_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(b'{"candidates":[{"content":{"parts":[]}}]}')

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    with pytest.raises(GenerationError, match="missing text"):
        GoogleGenerateContentLLMClient(
            "https://generativelanguage.googleapis.com/v1beta",
            "gemma-4-31b-it",
            180,
            "secret-token",
        ).complete([{"role": "user", "content": "hello"}])


class FakeStreamingResponse:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = lines

    def __enter__(self) -> FakeStreamingResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        return iter(self.lines)


def test_openai_chat_client_streams_token_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeStreamingResponse:
        return FakeStreamingResponse(
            [
                b'data: {"choices":[{"delta":{"content":"Alpha "}}]}\n',
                b'data: {"choices":[{"delta":{"content":"answer"}}]}\n',
                b"data: [DONE]\n",
            ]
        )

    monkeypatch.setattr(chat.request, "urlopen", fake_urlopen)

    chunks = list(
        OpenAICompatibleLLMClient(
            "http://llm.example/v1/chat/completions",
            model_name="gemma3:4b",
            timeout_seconds=120,
        ).stream_complete([{"role": "user", "content": "hello"}])
    )

    assert chunks == ["Alpha ", "answer"]


def test_answerability_refuses_low_score_dense_only_result() -> None:
    result = _search_result(
        score=0.1,
        retrieval_sources=[RetrievalSourceScore(source="dense", rank=1, score=0.1)],
    )

    reason = assess_answerability(
        [result],
        AnswerabilityConfig(min_top_score=0.5, min_usable_chunks=1),
    )

    assert reason == "Top retrieved evidence is below the answerability threshold."


@pytest.mark.parametrize("source", ["sparse", "text"])
def test_answerability_accepts_rank_one_exact_match_below_score_threshold(
    source: Literal["sparse", "text"],
) -> None:
    result = _search_result(
        score=0.333333,
        retrieval_sources=[RetrievalSourceScore(source=source, rank=1, score=0.2)],
    )

    reason = assess_answerability(
        [result],
        AnswerabilityConfig(min_top_score=0.5, min_usable_chunks=1),
    )

    assert reason is None


def test_answerability_refuses_lower_rank_exact_match_below_score_threshold() -> None:
    result = _search_result(
        score=0.333333,
        retrieval_sources=[RetrievalSourceScore(source="text", rank=2, score=0.2)],
    )

    reason = assess_answerability(
        [result],
        AnswerabilityConfig(min_top_score=0.5, min_usable_chunks=1),
    )

    assert reason == "Top retrieved evidence is below the answerability threshold."


def _search_result(
    score: float,
    retrieval_sources: list[RetrievalSourceScore],
) -> SearchResult:
    return SearchResult(
        score=score,
        text="Alpha content",
        document_id="doc-1",
        document_version_id="version-1",
        chunk_id="chunk-1",
        source_path="/watch/example.md",
        original_filename="example.md",
        page_number=None,
        heading_path=None,
        section_title=None,
        start_offset=None,
        end_offset=None,
        retrieval_sources=retrieval_sources,
    )
