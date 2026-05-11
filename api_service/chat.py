from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from email.message import Message
from typing import Protocol
from urllib import error, request

from shared.schemas import SearchResult

logger = logging.getLogger(__name__)
_RETRYABLE_GOOGLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_GOOGLE_GENERATION_MAX_ATTEMPTS = 4


class GenerationError(RuntimeError):
    """Raised when the chat generator cannot produce a usable response."""


@dataclass(frozen=True)
class GenerationOptions:
    """Optional provider-neutral controls for one LLM generation request."""

    temperature: float | None = None
    max_tokens: int | None = None


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate one assistant message from chat messages."""

    def stream_complete(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        """Yield assistant message chunks from one streaming request."""


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


class OpenAICompatibleLLMClient:
    """HTTP client for OpenAI-compatible chat completions endpoints."""

    def __init__(
        self,
        chat_completions_url: str,
        model_name: str,
        timeout_seconds: int,
        api_key: str | None = None,
    ) -> None:
        self.chat_completions_url = chat_completions_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key.strip() if api_key else None

    def complete(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate one non-streaming chat completion."""
        request_body: dict[str, object] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }
        if options is not None:
            if options.temperature is not None:
                request_body["temperature"] = options.temperature
            if options.max_tokens is not None:
                request_body["max_tokens"] = options.max_tokens

        payload = json.dumps(request_body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(
            url=self.chat_completions_url,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = _read_json_response(response)
        except error.HTTPError as exc:
            detail = _read_http_error_detail(exc)
            raise GenerationError(f"LLM chat HTTP error: {detail}") from exc
        except error.URLError as exc:
            raise GenerationError(f"LLM chat unavailable: {exc.reason}") from exc

        return _parse_chat_completion(body)

    def stream_complete(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        """Yield assistant text chunks from an OpenAI-compatible stream."""
        request_body: dict[str, object] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
        }
        if options is not None:
            if options.temperature is not None:
                request_body["temperature"] = options.temperature
            if options.max_tokens is not None:
                request_body["max_tokens"] = options.max_tokens

        payload = json.dumps(request_body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = request.Request(
            url=self.chat_completions_url,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                for raw_line in response:  # type: ignore[attr-defined]
                    if not isinstance(raw_line, bytes):
                        continue
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_payload = line.removeprefix("data:").strip()
                    if data_payload == "[DONE]":
                        break
                    try:
                        body = json.loads(data_payload)
                    except json.JSONDecodeError as exc:
                        raise GenerationError("LLM chat stream returned invalid JSON.") from exc
                    token = _parse_chat_stream_chunk(body)
                    if token:
                        yield token
        except error.HTTPError as exc:
            detail = _read_http_error_detail(exc)
            raise GenerationError(f"LLM chat HTTP error: {detail}") from exc
        except error.URLError as exc:
            raise GenerationError(f"LLM chat unavailable: {exc.reason}") from exc


class GoogleGenerateContentLLMClient:
    """HTTP client for Google AI Studio's native generateContent endpoint."""

    def __init__(
        self,
        endpoint_url: str,
        model_name: str,
        timeout_seconds: int,
        api_key: str | None,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key.strip() if api_key else None

    def complete(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions | None = None,
    ) -> str:
        """Generate one response through Google's native content API."""
        request_body = _build_google_generate_content_request(messages, options)
        payload = json.dumps(request_body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key

        last_error: GenerationError | None = None
        for attempt in range(1, _GOOGLE_GENERATION_MAX_ATTEMPTS + 1):
            req = request.Request(
                url=f"{self.endpoint_url}/models/{self.model_name}:generateContent",
                data=payload,
                headers=headers,
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    body = _read_json_response(response)
                return _parse_google_generate_content(body)
            except error.HTTPError as exc:
                detail = _read_http_error_detail(exc)
                last_error = GenerationError(f"Google generateContent HTTP error: {detail}")
                if not _should_retry_google_http_error(exc, attempt):
                    raise last_error from exc
                wait_seconds = _retry_wait_seconds(attempt, exc.headers)
                logger.warning(
                    "Google generateContent request failed with HTTP %s on attempt %s/%s; "
                    "retrying in %.1fs. Detail: %s",
                    exc.code,
                    attempt,
                    _GOOGLE_GENERATION_MAX_ATTEMPTS,
                    wait_seconds,
                    detail,
                )
                time.sleep(wait_seconds)
            except error.URLError as exc:
                last_error = GenerationError(f"Google generateContent unavailable: {exc.reason}")
                if attempt >= _GOOGLE_GENERATION_MAX_ATTEMPTS:
                    raise last_error from exc
                wait_seconds = _retry_wait_seconds(attempt)
                logger.warning(
                    "Google generateContent request failed with network error on attempt %s/%s; "
                    "retrying in %.1fs. Reason: %s",
                    attempt,
                    _GOOGLE_GENERATION_MAX_ATTEMPTS,
                    wait_seconds,
                    exc.reason,
                )
                time.sleep(wait_seconds)

        if last_error is not None:
            raise last_error
        raise GenerationError("Google generateContent retry loop exited unexpectedly.")

    def stream_complete(
        self,
        messages: list[dict[str, str]],
        options: GenerationOptions | None = None,
    ) -> Iterator[str]:
        raise GenerationError("Google generateContent streaming is not implemented.")


def _parse_chat_stream_chunk(body: dict[str, object]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    delta = first_choice.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def assess_answerability(
    results: list[SearchResult],
    config: AnswerabilityConfig,
) -> str | None:
    """Return a refusal reason when retrieval is too weak for generation."""
    if len(results) < config.min_usable_chunks:
        return "Retrieved evidence is insufficient to answer reliably."
    if results[0].score < config.min_top_score and not _has_rank_one_exact_match(results[0]):
        return "Top retrieved evidence is below the answerability threshold."
    return None


def _has_rank_one_exact_match(result: SearchResult) -> bool:
    return any(
        source.source in {"sparse", "text"} and source.rank == 1
        for source in result.retrieval_sources
    )


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
            raise GenerationError("LLM chat returned a non-bytes response.")
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GenerationError("LLM chat returned an invalid JSON response.") from exc

    if not isinstance(body, dict):
        raise GenerationError("LLM chat returned a non-object response.")
    return body


def _read_http_error_detail(exc: error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except UnicodeDecodeError:
        return "<non-UTF-8 response body>"


def _should_retry_google_http_error(exc: error.HTTPError, attempt: int) -> bool:
    return attempt < _GOOGLE_GENERATION_MAX_ATTEMPTS and exc.code in _RETRYABLE_GOOGLE_STATUS_CODES


def _retry_wait_seconds(attempt: int, headers: Message[str, str] | None = None) -> float:
    """Return Retry-After delay-seconds, else fallback to 1s, 2s, 4s... backoff."""
    retry_after = headers.get("Retry-After") if headers is not None else None
    if isinstance(retry_after, str):
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return float(2 ** (attempt - 1))


def _build_google_generate_content_request(
    messages: list[dict[str, str]],
    options: GenerationOptions | None,
) -> dict[str, object]:
    contents: list[dict[str, object]] = []
    system_parts: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not content:
            continue
        if role == "system":
            system_parts.append({"text": content})
            continue

        google_role = "model" if role == "assistant" else "user"
        contents.append({"role": google_role, "parts": [{"text": content}]})

    body: dict[str, object] = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {"parts": system_parts}

    generation_config: dict[str, object] = {}
    if options is not None:
        if options.temperature is not None:
            generation_config["temperature"] = options.temperature
        if options.max_tokens is not None:
            generation_config["maxOutputTokens"] = options.max_tokens
    if generation_config:
        body["generationConfig"] = generation_config

    return body


def _parse_chat_completion(body: dict[str, object]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GenerationError("LLM chat response missing choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise GenerationError("LLM chat response contains an invalid choice.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise GenerationError("LLM chat response missing message.")

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GenerationError("LLM chat response missing content.")

    return content


def _parse_google_generate_content(body: dict[str, object]) -> str:
    candidates = body.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        prompt_feedback = body.get("promptFeedback")
        if isinstance(prompt_feedback, dict):
            block_reason = prompt_feedback.get("blockReason")
            if isinstance(block_reason, str):
                raise GenerationError(
                    f"Google generateContent blocked request: blockReason={block_reason}."
                )
        raise GenerationError("Google generateContent response missing candidates.")

    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        raise GenerationError("Google generateContent response contains an invalid candidate.")

    content = first_candidate.get("content")
    if not isinstance(content, dict):
        raise GenerationError("Google generateContent response missing content.")

    parts = content.get("parts")
    if not isinstance(parts, list):
        raise GenerationError("Google generateContent response missing parts.")

    text_parts = [
        part.get("text")
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ]
    answer = "".join(text_parts).strip()
    if not answer:
        finish_reason = first_candidate.get("finishReason")
        if isinstance(finish_reason, str):
            raise GenerationError(
                f"Google generateContent response missing text (finishReason={finish_reason})."
            )
        raise GenerationError("Google generateContent response missing text.")
    return answer
