from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient, models

from shared.config import get_settings


class VectorIndexConfigurationError(RuntimeError):
    """Raised when the configured vector index is incompatible with embeddings."""


@dataclass(frozen=True)
class ChunkVector:
    """Chunk embedding and required payload metadata for Qdrant indexing."""

    chunk_id: str
    document_id: str
    document_version_id: str
    vector: list[float]


@dataclass(frozen=True)
class VectorSearchResult:
    """Dense retrieval result with payload IDs needed to load chunk metadata."""

    chunk_id: str
    document_id: str
    document_version_id: str
    score: float


class QdrantVectorIndex:
    """Manage the chunk-vector collection used by ingestion and retrieval."""

    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
        client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.collection_name = collection_name or settings.qdrant_collection
        self.client = client or QdrantClient(url=url or settings.qdrant_url)

    def ensure_collection(self, dimension: int) -> None:
        """Create the configured collection or verify its vector dimension."""
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                ),
            )
            return

        collection = self.client.get_collection(self.collection_name)
        vector_params = collection.config.params.vectors
        actual_dimension = self._extract_single_vector_size(vector_params)
        if actual_dimension != dimension:
            raise VectorIndexConfigurationError(
                f"Qdrant collection '{self.collection_name}' has vector dimension "
                f"{actual_dimension}, expected {dimension}."
            )

    def upsert_chunks(self, chunks: list[ChunkVector]) -> None:
        """Upsert chunk vectors with the required document/version/chunk payload IDs."""
        if not chunks:
            return

        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector=chunk.vector,
                payload={
                    "document_id": chunk.document_id,
                    "document_version_id": chunk.document_version_id,
                    "chunk_id": chunk.chunk_id,
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

    def search(self, query_vector: list[float], limit: int) -> list[VectorSearchResult]:
        """Search the configured collection and return payload IDs plus Qdrant score."""
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [self._build_search_result(point) for point in response.points]

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

    def _build_search_result(self, point: Any) -> VectorSearchResult:
        payload = point.payload or {}
        return VectorSearchResult(
            chunk_id=self._required_payload_value(payload, "chunk_id"),
            document_id=self._required_payload_value(payload, "document_id"),
            document_version_id=self._required_payload_value(payload, "document_version_id"),
            score=float(point.score),
        )

    def _required_payload_value(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise VectorIndexConfigurationError(
                f"Qdrant search result is missing required payload field '{key}'."
            )
        return value

    def _extract_single_vector_size(self, vector_params: Any) -> int:
        if isinstance(vector_params, models.VectorParams):
            return vector_params.size

        raise VectorIndexConfigurationError(
            f"Qdrant collection '{self.collection_name}' must use one unnamed dense vector."
        )
