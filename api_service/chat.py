from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from shared.schemas import SearchResult


class GenerationError(RuntimeError):
    """Raised when the chat generator cannot produce a usable response."""


class ChatCompletionClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Generate one assistant message from OpenAI-compatible chat messages."""


@dataclass(frozen=True)
class AnswerabilityConfig:
    """Thresholds used to decide whether retrieved evidence is sufficient."""

    min_top_score: float
    min_usable_chunks: int


@dataclass(frozen=True)
class GroundingConfig:
    """Limits that keep chat prompts within a bounded context size."""

    max_context_chunks: int
    max_chunk_chars: int


class ReadableResponse(Protocol):
    def read(self) -> bytes:
        """Read the raw response body bytes."""


class OpenAIChatCompletionClient:
    """HTTP client for Ollama's OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: int,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key.strip() if api_key else None

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Generate one non-streaming chat completion."""
        payload = json.dumps(
            {
                "model": self.model_name,
                "messages": messages,
                "stream": False,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(
            url=f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = _read_json_response(response)
        except error.HTTPError as exc:
            detail = _read_http_error_detail(exc)
            raise GenerationError(f"Ollama chat HTTP error: {detail}") from exc
        except error.URLError as exc:
            raise GenerationError(f"Ollama chat unavailable: {exc.reason}") from exc

        return _parse_chat_completion(body)


def assess_answerability(
    results: list[SearchResult],
    config: AnswerabilityConfig,
) -> str | None:
    """Return a refusal reason when retrieval is too weak for generation."""
    if len(results) < config.min_usable_chunks:
        return "Retrieved evidence is insufficient to answer reliably."
    if results[0].score < config.min_top_score:
        return "Top retrieved evidence is below the answerability threshold."
    return None


def select_grounding_citations(
    citations: list[SearchResult],
    config: GroundingConfig,
) -> list[SearchResult]:
    """Return the top-ranked citations that may be used as generation context."""
    return citations[: config.max_context_chunks]


def build_grounded_messages(
    query: str,
    citations: list[SearchResult],
    config: GroundingConfig,
) -> list[dict[str, str]]:
    """Build a compact grounded chat prompt with citation boundaries."""
    context_blocks = []
    for index, citation in enumerate(citations, start=1):
        location_parts = [citation.source_path]
        if citation.page_number is not None:
            location_parts.append(f"page {citation.page_number}")
        if citation.heading_path:
            location_parts.append(" > ".join(citation.heading_path))
        elif citation.section_title:
            location_parts.append(citation.section_title)

        context_blocks.append(
            "\n".join(
                [
                    f"[{index}] chunk_id={citation.chunk_id}",
                    f"source={'; '.join(location_parts)}",
                    citation.text[: config.max_chunk_chars],
                ]
            )
        )

    system_prompt = (
        "Answer only from the provided context. If the context does not contain "
        "enough information, say that you do not have enough information. Cite "
        "supporting context with bracketed citation numbers like [1]."
    )
    user_prompt = "\n\n".join(
        [
            "Context:",
            "\n\n".join(context_blocks),
            "Question:",
            query,
        ]
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _read_json_response(response: ReadableResponse) -> dict[str, object]:
    try:
        raw_body = response.read()
        if not isinstance(raw_body, bytes):
            raise GenerationError("Ollama chat returned a non-bytes response.")
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GenerationError("Ollama chat returned an invalid JSON response.") from exc

    if not isinstance(body, dict):
        raise GenerationError("Ollama chat returned a non-object response.")
    return body


def _read_http_error_detail(exc: error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except UnicodeDecodeError:
        return "<non-UTF-8 response body>"


def _parse_chat_completion(body: dict[str, object]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GenerationError("Ollama chat response missing choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise GenerationError("Ollama chat response contains an invalid choice.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise GenerationError("Ollama chat response missing message.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GenerationError("Ollama chat response missing content.")

    return content
