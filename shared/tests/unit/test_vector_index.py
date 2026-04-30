from types import SimpleNamespace
from typing import cast

from qdrant_client import models

from shared.vector_index import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    TEXT_PAYLOAD_FIELD,
    ChunkVector,
    QdrantVectorIndex,
    VectorIndexConfigurationError,
    sparse_vector_from_text,
    tokenize_sparse_text,
)


def first_filter_condition(selector: models.Filter) -> models.FieldCondition:
    must = cast(list[object], selector.must)
    return cast(models.FieldCondition, must[0])


class FakeQdrantClient:
    def __init__(self, collection_exists: bool = False, dimension: int = 8) -> None:
        self._collection_exists = collection_exists
        self.dimension = dimension
        self.created_collection: dict[str, object] | None = None
        self.created_payload_index: dict[str, object] | None = None
        self.upserted: dict[str, object] | None = None
        self.deleted: dict[str, object] | None = None
        self.queries: list[dict[str, object]] = []
        self.scrolled: dict[str, object] | None = None

    def collection_exists(self, collection_name: str) -> bool:
        return self._collection_exists

    def create_collection(
        self,
        collection_name: str,
        vectors_config: dict[str, models.VectorParams],
        sparse_vectors_config: dict[str, models.SparseVectorParams],
    ) -> bool:
        self.created_collection = {
            "collection_name": collection_name,
            "vectors_config": vectors_config,
            "sparse_vectors_config": sparse_vectors_config,
        }
        return True

    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: models.TextIndexParams,
        wait: bool,
    ) -> None:
        self.created_payload_index = {
            "collection_name": collection_name,
            "field_name": field_name,
            "field_schema": field_schema,
            "wait": wait,
        }

    def get_collection(self, collection_name: str) -> SimpleNamespace:
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={
                        DENSE_VECTOR_NAME: models.VectorParams(
                            size=self.dimension,
                            distance=models.Distance.COSINE,
                        )
                    },
                    sparse_vectors={
                        SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
                    },
                )
            ),
            payload_schema={TEXT_PAYLOAD_FIELD: SimpleNamespace(data_type="text")},
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
        query: list[float] | models.SparseVector,
        using: str,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> SimpleNamespace:
        self.queries.append(
            {
                "collection_name": collection_name,
                "query": query,
                "using": using,
                "limit": limit,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
            }
        )
        chunk_id = "chunk-1" if using == DENSE_VECTOR_NAME else "chunk-2"
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id=chunk_id,
                    score=0.87 if using == DENSE_VECTOR_NAME else 0.5,
                    payload={
                        "document_id": "doc-1",
                        "document_version_id": "version-1",
                        "chunk_id": chunk_id,
                    },
                )
            ]
        )

    def scroll(
        self,
        collection_name: str,
        scroll_filter: models.Filter,
        limit: int,
        with_payload: bool,
        with_vectors: bool,
    ) -> tuple[list[SimpleNamespace], None]:
        self.scrolled = {
            "collection_name": collection_name,
            "scroll_filter": scroll_filter,
            "limit": limit,
            "with_payload": with_payload,
            "with_vectors": with_vectors,
        }
        return (
            [
                SimpleNamespace(
                    id="chunk-3",
                    payload={
                        "document_id": "doc-1",
                        "document_version_id": "version-1",
                        "chunk_id": "chunk-3",
                    },
                )
            ],
            None,
        )


def test_sparse_vectorizer_is_deterministic_and_log_weights_duplicates() -> None:
    first = sparse_vector_from_text("Alpha alpha beta")
    second = sparse_vector_from_text("alpha beta")

    assert first.indices == sparse_vector_from_text("Alpha alpha beta").indices
    assert tokenize_sparse_text("Path/foo.md A_B c#") == ["path/foo.md", "a_b", "c#"]
    assert first.indices == second.indices
    assert max(first.values) > max(second.values)


def test_sparse_vectorizer_handles_empty_text() -> None:
    vector = sparse_vector_from_text("! ! !")

    assert vector.indices == []
    assert vector.values == []


def test_ensure_collection_creates_missing_collection() -> None:
    client = FakeQdrantClient(collection_exists=False)
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    index.ensure_collection(8)

    assert client.created_collection is not None
    assert client.created_collection["collection_name"] == "test_chunks"
    vectors_config = client.created_collection["vectors_config"]
    assert isinstance(vectors_config, dict)
    assert vectors_config[DENSE_VECTOR_NAME].size == 8
    assert vectors_config[DENSE_VECTOR_NAME].distance == models.Distance.COSINE
    sparse_vectors_config = client.created_collection["sparse_vectors_config"]
    assert isinstance(sparse_vectors_config, dict)
    assert sparse_vectors_config[SPARSE_VECTOR_NAME].modifier == models.Modifier.IDF
    assert client.created_payload_index is not None
    assert client.created_payload_index["field_name"] == TEXT_PAYLOAD_FIELD
    assert isinstance(client.created_payload_index["field_schema"], models.TextIndexParams)


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


def test_ensure_collection_rejects_legacy_unnamed_vector_collection() -> None:
    class FakeLegacyVectorQdrantClient(FakeQdrantClient):
        def get_collection(self, collection_name: str) -> SimpleNamespace:
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors=models.VectorParams(
                            size=8,
                            distance=models.Distance.COSINE,
                        ),
                        sparse_vectors={},
                    )
                ),
                payload_schema={},
            )

    client = FakeLegacyVectorQdrantClient(collection_exists=True, dimension=8)
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    try:
        index.ensure_collection(8)
    except VectorIndexConfigurationError as error:
        assert "legacy unnamed" in str(error)
        assert "Recreate the collection and reingest" in str(error)
    else:
        raise AssertionError("Expected legacy vector collection to fail fast")


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
                text="Alpha beta alpha",
            )
        ]
    )

    assert client.upserted is not None
    assert client.upserted["collection_name"] == "test_chunks"
    assert client.upserted["wait"] is True
    points = client.upserted["points"]
    assert isinstance(points, list)
    assert points[0].id == "chunk-1"
    assert points[0].vector == {
        DENSE_VECTOR_NAME: [0.1, 0.2],
        SPARSE_VECTOR_NAME: sparse_vector_from_text("Alpha beta alpha"),
    }
    assert points[0].payload == {
        "document_id": "doc-1",
        "document_version_id": "version-1",
        "chunk_id": "chunk-1",
        "text": "Alpha beta alpha",
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


def test_search_fuses_dense_sparse_and_text_results_with_provenance() -> None:
    client = FakeQdrantClient()
    index = QdrantVectorIndex(collection_name="test_chunks", client=client)

    results = index.search([0.1, 0.2], "alpha", limit=3)

    assert client.queries[0] == {
        "collection_name": "test_chunks",
        "query": [0.1, 0.2],
        "using": DENSE_VECTOR_NAME,
        "limit": 3,
        "with_payload": True,
        "with_vectors": False,
    }
    assert client.queries[1]["using"] == SPARSE_VECTOR_NAME
    assert client.scrolled is not None
    assert [result.chunk_id for result in results] == ["chunk-1", "chunk-2", "chunk-3"]
    assert results[0].document_id == "doc-1"
    assert results[0].document_version_id == "version-1"
    assert results[0].score == 0.333333
    assert results[0].retrieval_sources[0].source == "dense"
    assert results[0].retrieval_sources[0].rank == 1
    assert results[0].retrieval_sources[0].score == 0.87
    assert results[2].retrieval_sources[0].source == "text"
    assert results[2].retrieval_sources[0].score is None


def test_fusion_handles_single_source_results() -> None:
    index = QdrantVectorIndex(collection_name="test_chunks", client=FakeQdrantClient())
    point = SimpleNamespace(
        id="chunk-1",
        score=0.42,
        payload={
            "document_id": "doc-1",
            "document_version_id": "version-1",
            "chunk_id": "chunk-1",
        },
    )

    results = index._fuse_results({"dense": [], "sparse": [point], "text": []}, limit=10)

    assert len(results) == 1
    assert results[0].chunk_id == "chunk-1"
    assert results[0].score == 0.333333
    assert results[0].retrieval_sources[0].source == "sparse"


def test_fusion_merges_mixed_results_and_breaks_ties_by_chunk_id() -> None:
    index = QdrantVectorIndex(collection_name="test_chunks", client=FakeQdrantClient())

    def point(chunk_id: str, score: float = 0.1) -> SimpleNamespace:
        return SimpleNamespace(
            id=chunk_id,
            score=score,
            payload={
                "document_id": "doc-1",
                "document_version_id": "version-1",
                "chunk_id": chunk_id,
            },
        )

    results = index._fuse_results(
        {
            "dense": [point("chunk-b"), point("chunk-a")],
            "sparse": [point("chunk-a")],
            "text": [SimpleNamespace(id="chunk-c", payload=point("chunk-c").payload)],
        },
        limit=10,
    )

    assert [result.chunk_id for result in results] == ["chunk-a", "chunk-b", "chunk-c"]
    assert [source.source for source in results[0].retrieval_sources] == ["dense", "sparse"]
