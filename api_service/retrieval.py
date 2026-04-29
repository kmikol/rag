from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from shared.repository import MetadataRepository
from shared.schemas import SearchResult
from shared.vector_index import VectorSearchResult


class RetrievalError(RuntimeError):
    """Raised when retrieval cannot call or parse a required backend response."""


@dataclass(frozen=True)
class QueryEmbedding:
    """Embedding-service response for one interactive search query."""

    embedding: list[float]
    embedding_model_name: str
    dimension: int


class QueryEmbeddingClient(Protocol):
    def embed_query(self, query: str) -> QueryEmbedding:
        """Embed a user query for retrieval."""


class ReadableResponse(Protocol):
    def read(self) -> bytes:
        """Read the raw response body bytes."""


class VectorIndex(Protocol):
    def ensure_collection(self, dimension: int) -> None:
        """Create or verify the vector collection for the embedding dimension."""

    def search(self, query_vector: list[float], limit: int) -> list[VectorSearchResult]:
        """Return ranked dense retrieval candidates."""


class HttpQueryEmbeddingClient:
    """Small HTTP client for the embedding-service single-query API."""

    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def embed_query(self, query: str) -> QueryEmbedding:
        """Embed one search query through `POST /embed`."""
        payload = json.dumps({"text": query}).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = _read_json_response(response)
        except error.HTTPError as exc:
            detail = _read_http_error_detail(exc)
            raise RetrievalError(f"Embedding service HTTP error: {detail}") from exc
        except error.URLError as exc:
            raise RetrievalError(f"Embedding service unavailable: {exc.reason}") from exc

        if not isinstance(body, dict):
            raise RetrievalError("Embedding service returned a non-object response.")
        embedding = body.get("embedding")
        if not isinstance(embedding, list):
            raise RetrievalError("Embedding service returned invalid embedding data.")

        return QueryEmbedding(
            embedding=[float(value) for value in embedding],
            embedding_model_name=_required_str(body, "embedding_model_name"),
            dimension=_required_int(body, "dimension"),
        )


@dataclass
class SearchRetriever:
    """Orchestrate dense retrieval and loading active chunk metadata for API search."""

    embedding_client: QueryEmbeddingClient
    vector_index: VectorIndex

    def search(
        self,
        query: str,
        limit: int,
        repository: MetadataRepository,
    ) -> list[SearchResult]:
        """Return citation-ready results ranked by dense vector search score."""
        embedding = self.embedding_client.embed_query(query)
        try:
            self.vector_index.ensure_collection(embedding.dimension)
            dense_results = self.vector_index.search(embedding.embedding, limit)
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("Vector index search failed.") from exc
        chunks_by_id = repository.get_active_chunks_by_ids(
            [result.chunk_id for result in dense_results]
        )

        results: list[SearchResult] = []
        for dense_result in dense_results:
            chunk = chunks_by_id.get(dense_result.chunk_id)
            if chunk is None:
                continue
            results.append(
                SearchResult(
                    score=dense_result.score,
                    text=chunk["text"],
                    document_id=chunk["document_id"],
                    document_version_id=chunk["document_version_id"],
                    chunk_id=chunk["id"],
                    source_path=chunk["source_path"],
                    original_filename=chunk["original_filename"],
                    page_number=chunk["page_number"],
                    heading_path=chunk["heading_path"],
                    section_title=chunk["section_title"],
                    start_offset=chunk["start_offset"],
                    end_offset=chunk["end_offset"],
                )
            )
        return results


def _read_json_response(response: ReadableResponse) -> dict[str, object]:
    try:
        raw_body = response.read()
        if not isinstance(raw_body, bytes):
            raise RetrievalError("Embedding service returned a non-bytes response.")
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RetrievalError("Embedding service returned an invalid JSON response.") from exc

    if not isinstance(body, dict):
        raise RetrievalError("Embedding service returned a non-object response.")
    return body


def _read_http_error_detail(exc: error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8")
    except UnicodeDecodeError:
        return "<non-UTF-8 response body>"


def _required_str(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise RetrievalError(f"Embedding service response missing '{key}'.")
    return value


def _required_int(body: dict[str, object], key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int):
        raise RetrievalError(f"Embedding service response missing '{key}'.")
    return value
