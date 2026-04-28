from types import SimpleNamespace
from typing import cast

from qdrant_client import models

from shared.vector_index import ChunkVector, QdrantVectorIndex, VectorIndexConfigurationError


def first_filter_condition(selector: models.Filter) -> models.FieldCondition:
    must = cast(list[object], selector.must)
    return cast(models.FieldCondition, must[0])


class FakeQdrantClient:
    def __init__(self, collection_exists: bool = False, dimension: int = 8) -> None:
        self._collection_exists = collection_exists
        self.dimension = dimension
        self.created_collection: dict[str, object] | None = None
        self.upserted: dict[str, object] | None = None
        self.deleted: dict[str, object] | None = None
        self.query: dict[str, object] | None = None

    def collection_exists(self, collection_name: str) -> bool:
        return self._collection_exists

    def create_collection(
        self,
        collection_name: str,
        vectors_config: models.VectorParams,
    ) -> bool:
        self.created_collection = {
            "collection_name": collection_name,
            "vectors_config": vectors_config,
        }
        return True

    def get_collection(self, collection_name: str) -> SimpleNamespace:
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=models.VectorParams(
                        size=self.dimension,
                        distance=models.Distance.COSINE,
                    )
                )
            )
        )

    def upsert(
        self,
        collection_name: str,
        points: list[models.PointStruct],
        wait: bool,
    ) -> None:
        self.upserted = {
            "collection_name": collection_name,
            "points": points,
            "wait": wait,
        }

    def delete(
        self,
        collection_name: str,
        points_selector: models.Filter,
        wait: bool,
    ) -> None:
        self.deleted = {
            "collection_name": collection_name,
            "points_selector": points_selector,
            "wait": wait,
        }

    def query_points(
        self,
        collection_name: str,
        query: list[float],
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> SimpleNamespace:
        self.query = {
            "collection_name": collection_name,
            "query": query,
            "limit": limit,
            "with_payload": with_payload,
            "with_vectors": with_vectors,
        }
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    score=0.87,
                    payload={
                        "document_id": "doc-1",
                        "document_version_id": "version-1",
                        "chunk_id": "chunk-1",
                    },
                )
            ]
        )


def test_ensure_collection_creates_missing_collection() -> None:
    client = FakeQdrantClient(collection_exists=False)
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    index.ensure_collection(8)

    assert client.created_collection is not None
    assert client.created_collection["collection_name"] == "test_chunks"
    vectors_config = client.created_collection["vectors_config"]
    assert isinstance(vectors_config, models.VectorParams)
    assert vectors_config.size == 8
    assert vectors_config.distance == models.Distance.COSINE


def test_ensure_collection_accepts_matching_dimension() -> None:
    client = FakeQdrantClient(collection_exists=True, dimension=8)
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    index.ensure_collection(8)

    assert client.created_collection is None


def test_ensure_collection_rejects_dimension_mismatch() -> None:
    client = FakeQdrantClient(collection_exists=True, dimension=16)
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    try:
        index.ensure_collection(8)
    except VectorIndexConfigurationError as error:
        assert "expected 8" in str(error)
    else:
        raise AssertionError("Expected dimension mismatch to fail fast")


def test_ensure_collection_rejects_named_vector_collection() -> None:
    class FakeNamedVectorQdrantClient(FakeQdrantClient):
        def get_collection(self, collection_name: str) -> SimpleNamespace:
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={
                            "named_vector": models.VectorParams(
                                size=8,
                                distance=models.Distance.COSINE,
                            )
                        }
                    )
                )
            )

    client = FakeNamedVectorQdrantClient(collection_exists=True, dimension=8)
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    try:
        index.ensure_collection(8)
    except VectorIndexConfigurationError as error:
        assert "must use one unnamed dense vector" in str(error)
    else:
        raise AssertionError("Expected named vector collection to fail fast")


def test_upsert_chunks_uses_chunk_id_as_point_id_and_required_payload() -> None:
    client = FakeQdrantClient()
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    index.upsert_chunks(
        [
            ChunkVector(
                chunk_id="chunk-1",
                document_id="doc-1",
                document_version_id="version-1",
                vector=[0.1, 0.2],
            )
        ]
    )

    assert client.upserted is not None
    assert client.upserted["collection_name"] == "test_chunks"
    assert client.upserted["wait"] is True
    points = client.upserted["points"]
    assert isinstance(points, list)
    assert points[0].id == "chunk-1"
    assert points[0].vector == [0.1, 0.2]
    assert points[0].payload == {
        "document_id": "doc-1",
        "document_version_id": "version-1",
        "chunk_id": "chunk-1",
    }


def test_delete_by_document_id_uses_payload_filter() -> None:
    client = FakeQdrantClient()
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    index.delete_by_document_id("doc-1")

    assert client.deleted is not None
    assert client.deleted["collection_name"] == "test_chunks"
    assert client.deleted["wait"] is True
    selector = client.deleted["points_selector"]
    assert isinstance(selector, models.Filter)
    condition = first_filter_condition(selector)
    assert condition.key == "document_id"
    match = cast(models.MatchValue, condition.match)
    assert match.value == "doc-1"


def test_delete_by_document_version_id_uses_payload_filter() -> None:
    client = FakeQdrantClient()
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    index.delete_by_document_version_id("version-1")

    assert client.deleted is not None
    selector = client.deleted["points_selector"]
    assert isinstance(selector, models.Filter)
    condition = first_filter_condition(selector)
    assert condition.key == "document_version_id"
    match = cast(models.MatchValue, condition.match)
    assert match.value == "version-1"


def test_search_maps_qdrant_points_to_vector_results() -> None:
    client = FakeQdrantClient()
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    results = index.search([0.1, 0.2], limit=3)

    assert client.query == {
        "collection_name": "test_chunks",
        "query": [0.1, 0.2],
        "limit": 3,
        "with_payload": True,
        "with_vectors": False,
    }
    assert results[0].chunk_id == "chunk-1"
    assert results[0].document_id == "doc-1"
    assert results[0].document_version_id == "version-1"
    assert results[0].score == 0.87
