from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from qdrant_client import QdrantClient, models

from shared.config import get_settings

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
TEXT_PAYLOAD_FIELD = "text"
RRF_K = 60
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/#-]*")


class VectorIndexConfigurationError(RuntimeError):
    """Raised when the configured vector index is incompatible with embeddings."""


RetrievalSource = Literal["dense", "sparse", "text"]
SOURCE_ORDER: tuple[RetrievalSource, ...] = ("dense", "sparse", "text")


@dataclass(frozen=True)
class ChunkVector:
    """Chunk embedding and required payload metadata for Qdrant indexing."""

    chunk_id: str
    document_id: str
    document_version_id: str
    vector: list[float]
    text: str


@dataclass(frozen=True)
class RetrievalSourceScore:
    """Per-source retrieval provenance for a fused candidate."""

    source: RetrievalSource
    rank: int
    score: float | None


@dataclass(frozen=True)
class VectorSearchResult:
    """Fused retrieval result with payload IDs needed to load chunk metadata."""

    chunk_id: str
    document_id: str
    document_version_id: str
    score: float
    retrieval_sources: tuple[RetrievalSourceScore, ...] = ()


def tokenize_sparse_text(text: str) -> list[str]:
    """Return deterministic lexical tokens shared by sparse indexing and queries."""
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def sparse_vector_from_text(text: str) -> models.SparseVector:
    """Build a deterministic sparse vector using stable hashed term ids."""
    counts = Counter(tokenize_sparse_text(text))
    if not counts:
        return models.SparseVector(indices=[], values=[])

    weighted_by_index: dict[int, float] = {}
    for token, count in counts.items():
        index = _stable_sparse_index(token)
        weighted_by_index[index] = weighted_by_index.get(index, 0.0) + (1.0 + math.log(count))

    ordered = sorted(weighted_by_index.items())
    return models.SparseVector(
        indices=[index for index, _ in ordered],
        values=[round(value, 6) for _, value in ordered],
    )


class QdrantVectorIndex:
    """Manage the chunk-vector collection used by ingestion and retrieval."""

    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        if collection_name is not None and client is not None:
            self.collection_name = collection_name
            self.client = client
            return

        if collection_name is not None and url is not None:
            self.collection_name = collection_name
            self.client = QdrantClient(url=url)
            return

        if collection_name is None or client is None:
            settings = get_settings()
            self.collection_name = collection_name or settings.qdrant_collection
            self.client = client or QdrantClient(url=url or settings.qdrant_url)
            return

    def ensure_collection(self, dimension: int) -> None:
        """Create the configured collection or verify its vector dimension."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: models.VectorParams(
                        size=dimension,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: models.SparseVectorParams(
                        modifier=models.Modifier.IDF,
                    )
                },
            )
            self._ensure_text_payload_index()
            return

        collection = self.client.get_collection(self.collection_name)
        vector_params = collection.config.params.vectors
        actual_dimension = self._extract_dense_vector_size(vector_params)
        if actual_dimension != dimension:
            raise VectorIndexConfigurationError(
                f"Qdrant collection '{self.collection_name}' has dense vector dimension "
                f"{actual_dimension}, expected {dimension}. Recreate the collection and reingest."
            )
        self._validate_sparse_vectors(collection)
        self._validate_text_payload_index(collection)

    def _ensure_text_payload_index(self) -> None:
        self.client.create_payload_index(
            collection_name=self.collection_name,
            field_name=TEXT_PAYLOAD_FIELD,
            field_schema=models.TextIndexParams(
                type=models.TextIndexType.TEXT,
                tokenizer=models.TokenizerType.WORD,
                lowercase=True,
            ),
            wait=True,
        )

    def upsert_chunks(self, chunks: list[ChunkVector]) -> None:
        """Upsert chunk vectors with the required document/version/chunk payload IDs."""
        if not chunks:
            return

        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector={
                    DENSE_VECTOR_NAME: chunk.vector,
                    SPARSE_VECTOR_NAME: sparse_vector_from_text(chunk.text),
                },
                payload={
                    "document_id": chunk.document_id,
                    "document_version_id": chunk.document_version_id,
                    "chunk_id": chunk.chunk_id,
                    TEXT_PAYLOAD_FIELD: chunk.text,
                },
            )
            for chunk in chunks
        ]
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def delete_by_document_id(self, document_id: str) -> None:
        """Delete all vectors whose payload belongs to one logical document."""
        self._delete_by_payload("document_id", document_id)

    def delete_by_document_version_id(self, document_version_id: str) -> None:
        """Delete all vectors whose payload belongs to one immutable document version."""
        self._delete_by_payload("document_version_id", document_version_id)

    def search(
        self,
        query_vector: list[float],
        query_text: str,
        limit: int,
    ) -> list[VectorSearchResult]:
        """Search dense, sparse, and text indexes, then return fused candidates."""
        dense_points = self._query_dense(query_vector, limit)
        sparse_points = self._query_sparse(query_text, limit)
        text_points = self._query_text(query_text, limit)
        return self._fuse_results(
            {
                "dense": dense_points,
                "sparse": sparse_points,
                "text": text_points,
            },
            limit,
        )

    def _query_dense(self, query_vector: list[float], limit: int) -> list[Any]:
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=DENSE_VECTOR_NAME,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return list(response.points)

    def _query_sparse(self, query_text: str, limit: int) -> list[Any]:
        sparse_vector = sparse_vector_from_text(query_text)
        if not sparse_vector.indices:
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=sparse_vector,
            using=SPARSE_VECTOR_NAME,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return list(response.points)

    def _query_text(self, query_text: str, limit: int) -> list[Any]:
        sparse_vector = sparse_vector_from_text(query_text)
        if not sparse_vector.indices:
            return []
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=sparse_vector,
            using=SPARSE_VECTOR_NAME,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key=TEXT_PAYLOAD_FIELD,
                        match=models.MatchText(text=query_text),
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return list(response.points)

    def _fuse_results(
        self,
        results_by_source: dict[RetrievalSource, list[Any]],
        limit: int,
    ) -> list[VectorSearchResult]:
        fused_scores: dict[str, float] = {}
        payloads_by_chunk_id: dict[str, dict[str, Any]] = {}
        sources_by_chunk_id: dict[str, list[RetrievalSourceScore]] = {}

        for source in SOURCE_ORDER:
            for rank, point in enumerate(results_by_source[source], start=1):
                payload = point.payload or {}
                chunk_id = self._required_payload_value(payload, "chunk_id")
                payloads_by_chunk_id.setdefault(chunk_id, payload)
                fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (1.0 / (RRF_K + rank))
                sources_by_chunk_id.setdefault(chunk_id, []).append(
                    RetrievalSourceScore(
                        source=source,
                        rank=rank,
                        score=float(point.score) if hasattr(point, "score") else None,
                    )
                )

        if not fused_scores:
            return []

        max_possible_score = len(SOURCE_ORDER) / (RRF_K + 1)
        ordered_chunk_ids = sorted(
            fused_scores,
            key=lambda chunk_id: (-fused_scores[chunk_id], chunk_id),
        )
        return [
            self._build_search_result(
                payloads_by_chunk_id[chunk_id],
                min(fused_scores[chunk_id] / max_possible_score, 1.0),
                tuple(sources_by_chunk_id[chunk_id]),
            )
            for chunk_id in ordered_chunk_ids[:limit]
        ]

    def _delete_by_payload(self, field_name: str, value: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key=field_name,
                        match=models.MatchValue(value=value),
                    )
                ]
            ),
            wait=True,
        )

    def _build_search_result(
        self,
        payload: dict[str, Any],
        score: float,
        retrieval_sources: tuple[RetrievalSourceScore, ...],
    ) -> VectorSearchResult:
        return VectorSearchResult(
            chunk_id=self._required_payload_value(payload, "chunk_id"),
            document_id=self._required_payload_value(payload, "document_id"),
            document_version_id=self._required_payload_value(payload, "document_version_id"),
            score=round(score, 6),
            retrieval_sources=retrieval_sources,
        )

    def _required_payload_value(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise VectorIndexConfigurationError(
                f"Qdrant search result is missing required payload field '{key}'."
            )
        return value

    def _extract_dense_vector_size(self, vector_params: Any) -> int:
        if isinstance(vector_params, models.VectorParams):
            raise VectorIndexConfigurationError(
                f"Qdrant collection '{self.collection_name}' uses the legacy unnamed "
                "dense vector shape. Recreate the collection and reingest."
            )
        if isinstance(vector_params, dict):
            dense_params = vector_params.get(DENSE_VECTOR_NAME)
            if isinstance(dense_params, models.VectorParams):
                return dense_params.size

        raise VectorIndexConfigurationError(
            f"Qdrant collection '{self.collection_name}' must define a named "
            f"'{DENSE_VECTOR_NAME}' dense vector. Recreate the collection and reingest."
        )

    def _validate_sparse_vectors(self, collection: Any) -> None:
        sparse_vectors = getattr(collection.config.params, "sparse_vectors", None)
        if not isinstance(sparse_vectors, dict) or SPARSE_VECTOR_NAME not in sparse_vectors:
            raise VectorIndexConfigurationError(
                f"Qdrant collection '{self.collection_name}' must define a named "
                f"'{SPARSE_VECTOR_NAME}' sparse vector. Recreate the collection and reingest."
            )

    def _validate_text_payload_index(self, collection: Any) -> None:
        payload_schema = getattr(collection, "payload_schema", None)
        if not isinstance(payload_schema, dict):
            raise VectorIndexConfigurationError(
                f"Qdrant collection '{self.collection_name}' must expose payload schema "
                f"with a '{TEXT_PAYLOAD_FIELD}' text index. Recreate the collection and reingest."
            )
        text_schema = payload_schema.get(TEXT_PAYLOAD_FIELD)
        schema_type = getattr(text_schema, "data_type", None) or getattr(text_schema, "type", None)
        if schema_type not in {models.PayloadSchemaType.TEXT, models.TextIndexType.TEXT, "text"}:
            raise VectorIndexConfigurationError(
                f"Qdrant collection '{self.collection_name}' must have a text payload "
                f"index on '{TEXT_PAYLOAD_FIELD}'. Recreate the collection and reingest."
            )


def _stable_sparse_index(token: str) -> int:
    # FNV-1a provides deterministic 32-bit ids without Python hash randomization.
    value = 2166136261
    for byte in token.encode("utf-8"):
        value ^= byte
        value = (value * 16777619) % (2**32)
    return value
