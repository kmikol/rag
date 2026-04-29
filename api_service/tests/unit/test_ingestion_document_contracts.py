from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from api_service.chat import GenerationError
from api_service.main import (
    app,
    get_chat_completion_client,
    get_metadata_engine,
    get_query_embedding_client,
    get_vector_index,
    open_metadata_repository,
)
from api_service.retrieval import QueryEmbedding, RetrievalError
from shared.config import get_settings
from shared.db import metadata
from shared.repository import ChunkRecord, MetadataRepository
from shared.vector_index import VectorSearchResult


@pytest.fixture
def engine() -> Iterator[Engine]:
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RAG_API_KEY", "unit-token")
    get_settings.cache_clear()
    get_metadata_engine.cache_clear()

    def open_test_repository() -> Iterator[MetadataRepository]:
        with engine.begin() as connection:
            yield MetadataRepository(connection)

    app.dependency_overrides[open_metadata_repository] = open_test_repository
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        get_chat_completion_client.cache_clear()
        get_metadata_engine.cache_clear()


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer unit-token"}


class FakeQueryEmbeddingClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.error: RetrievalError | None = None

    def embed_query(self, query: str) -> QueryEmbedding:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return QueryEmbedding(
            embedding=[1.0, 0.0, 0.0],
            model_name="fake-model",
            dimension=3,
        )


class FakeVectorIndex:
    def __init__(self) -> None:
        self.results: list[VectorSearchResult] = []
        self.ensured_dimensions: list[int] = []
        self.query_vector: list[float] | None = None
        self.limit: int | None = None
        self.error: RuntimeError | None = None

    def ensure_collection(self, dimension: int) -> None:
        self.ensured_dimensions.append(dimension)

    def search(self, query_vector: list[float], limit: int) -> list[VectorSearchResult]:
        if self.error is not None:
            raise self.error
        self.query_vector = query_vector
        self.limit = limit
        return self.results


class FakeChatCompletionClient:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []
        self.error: GenerationError | None = None

    def complete(self, messages: list[dict[str, str]]) -> str:
        self.messages.append(messages)
        if self.error is not None:
            raise self.error
        return "Alpha is answered from the retrieved context [1]."


def test_protected_endpoints_require_api_key(client: TestClient) -> None:
    response = client.post("/ingest")

    assert response.status_code == 401


def test_search_requires_api_key(client: TestClient) -> None:
    response = client.post("/search", json={"query": "example"})

    assert response.status_code == 401


def test_chat_requires_api_key(client: TestClient) -> None:
    response = client.post("/chat", json={"query": "example"})

    assert response.status_code == 401


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_search_rejects_invalid_limit(client: TestClient, limit: int) -> None:
    response = client.post(
        "/search",
        json={"query": "example", "limit": limit},
        headers=auth_headers(),
    )

    assert response.status_code == 422


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_chat_rejects_invalid_limit(client: TestClient, limit: int) -> None:
    response = client.post(
        "/chat",
        json={"query": "example", "limit": limit},
        headers=auth_headers(),
    )

    assert response.status_code == 422


def test_post_ingest_creates_pending_job(client: TestClient) -> None:
    response = client.post(
        "/ingest",
        json={"requested_path": "/watch/example.md"},
        headers=auth_headers(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["requested_path"] == "/watch/example.md"
    assert body["status"] == "pending"
    assert body["processed_items"] == 0
    assert body["id"]


def test_get_ingest_returns_persisted_status(client: TestClient) -> None:
    created = client.post("/ingest", headers=auth_headers()).json()

    response = client.get(f"/ingest/{created['id']}", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "pending"


def test_get_ingest_returns_404_for_unknown_job(client: TestClient) -> None:
    response = client.get("/ingest/missing", headers=auth_headers())

    assert response.status_code == 404


def test_get_documents_lists_metadata_backed_documents(
    client: TestClient,
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/example.md")
        version = repository.create_document_version(document["id"], "a" * 64)
        repository.mark_document_version_active(version["id"])

    response = client.get("/documents", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert len(body["documents"]) == 1
    listed = body["documents"][0]
    assert listed["id"] == document["id"]
    assert listed["source_path"] == "/watch/example.md"
    assert listed["active_version"]["id"] == version["id"]


def test_search_returns_citation_ready_chunks(
    client: TestClient,
    engine: Engine,
) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/example.md")
        version = repository.create_document_version(document["id"], "a" * 64)
        chunks = repository.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="Alpha content",
                    source_path="/watch/example.md",
                    original_filename="example.md",
                    page_number=3,
                    heading_path=["Root", "Alpha"],
                    section_title="Alpha",
                    start_offset=10,
                    end_offset=23,
                )
            ],
        )
        repository.mark_document_version_active(version["id"])

    vector_index.results = [
        VectorSearchResult(
            chunk_id=chunks[0]["id"],
            document_id=document["id"],
            document_version_id=version["id"],
            score=0.92,
        )
    ]
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index

    response = client.post(
        "/search",
        json={"query": "alpha", "limit": 5},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert embedding_client.queries == ["alpha"]
    assert vector_index.ensured_dimensions == [3]
    assert vector_index.query_vector == [1.0, 0.0, 0.0]
    assert vector_index.limit == 5
    body = response.json()
    assert body["results"] == [
        {
            "score": 0.92,
            "text": "Alpha content",
            "document_id": document["id"],
            "document_version_id": version["id"],
            "chunk_id": chunks[0]["id"],
            "source_path": "/watch/example.md",
            "original_filename": "example.md",
            "page_number": 3,
            "heading_path": ["Root", "Alpha"],
            "section_title": "Alpha",
            "start_offset": 10,
            "end_offset": 23,
        }
    ]


def test_chat_returns_grounded_answer_with_citations(
    client: TestClient,
    engine: Engine,
) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()
    chat_client = FakeChatCompletionClient()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/example.md")
        version = repository.create_document_version(document["id"], "a" * 64)
        chunks = repository.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="Alpha content",
                    source_path="/watch/example.md",
                    original_filename="example.md",
                    page_number=3,
                    heading_path=["Root", "Alpha"],
                    section_title="Alpha",
                    start_offset=10,
                    end_offset=23,
                )
            ],
        )
        repository.mark_document_version_active(version["id"])

    vector_index.results = [
        VectorSearchResult(
            chunk_id=chunks[0]["id"],
            document_id=document["id"],
            document_version_id=version["id"],
            score=0.92,
        )
    ]
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index
    app.dependency_overrides[get_chat_completion_client] = lambda: chat_client

    response = client.post(
        "/chat",
        json={"query": "alpha", "limit": 5},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert embedding_client.queries == ["alpha"]
    assert vector_index.limit == 5
    assert len(chat_client.messages) == 1
    messages = chat_client.messages[0]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Alpha content" in messages[1]["content"]
    body = response.json()
    assert body["answer"] == "Alpha is answered from the retrieved context [1]."
    assert body["refused"] is False
    assert body["refusal_reason"] is None
    assert body["citations"][0]["chunk_id"] == chunks[0]["id"]


def test_chat_refuses_when_retrieval_is_empty(client: TestClient) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()
    chat_client = FakeChatCompletionClient()
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index
    app.dependency_overrides[get_chat_completion_client] = lambda: chat_client

    response = client.post(
        "/chat",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert chat_client.messages == []
    assert response.json() == {
        "answer": None,
        "citations": [],
        "refused": True,
        "refusal_reason": "Retrieved evidence is insufficient to answer reliably.",
    }


def test_chat_refuses_when_top_score_is_too_low(
    client: TestClient,
    engine: Engine,
) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()
    chat_client = FakeChatCompletionClient()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/example.md")
        version = repository.create_document_version(document["id"], "a" * 64)
        chunks = repository.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="Low confidence content",
                    source_path="/watch/example.md",
                    original_filename="example.md",
                )
            ],
        )
        repository.mark_document_version_active(version["id"])

    vector_index.results = [
        VectorSearchResult(
            chunk_id=chunks[0]["id"],
            document_id=document["id"],
            document_version_id=version["id"],
            score=0.1,
        )
    ]
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index
    app.dependency_overrides[get_chat_completion_client] = lambda: chat_client

    response = client.post(
        "/chat",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert chat_client.messages == []
    body = response.json()
    assert body["answer"] is None
    assert body["refused"] is True
    assert body["refusal_reason"] == "Top retrieved evidence is below the answerability threshold."
    assert body["citations"][0]["chunk_id"] == chunks[0]["id"]


def test_chat_returns_bad_gateway_for_retrieval_failure(client: TestClient) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    embedding_client.error = RetrievalError("Embedding service unavailable: refused")
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: FakeVectorIndex()
    app.dependency_overrides[get_chat_completion_client] = lambda: FakeChatCompletionClient()

    response = client.post(
        "/chat",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Embedding service unavailable: refused"


def test_chat_returns_bad_gateway_for_generation_failure(
    client: TestClient,
    engine: Engine,
) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()
    chat_client = FakeChatCompletionClient()
    chat_client.error = GenerationError("Ollama chat response missing choices.")

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/example.md")
        version = repository.create_document_version(document["id"], "a" * 64)
        chunks = repository.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="Alpha content",
                    source_path="/watch/example.md",
                    original_filename="example.md",
                )
            ],
        )
        repository.mark_document_version_active(version["id"])

    vector_index.results = [
        VectorSearchResult(
            chunk_id=chunks[0]["id"],
            document_id=document["id"],
            document_version_id=version["id"],
            score=0.92,
        )
    ]
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index
    app.dependency_overrides[get_chat_completion_client] = lambda: chat_client

    response = client.post(
        "/chat",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Ollama chat response missing choices."


def test_search_returns_empty_results_when_vector_search_is_empty(client: TestClient) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index

    response = client.post(
        "/search",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_search_excludes_stale_document_versions(
    client: TestClient,
    engine: Engine,
) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/example.md")
        old_version = repository.create_document_version(document["id"], "a" * 64)
        active_version = repository.create_document_version(document["id"], "b" * 64)
        stale_chunks = repository.create_chunks(
            document["id"],
            old_version["id"],
            [
                ChunkRecord(
                    text="Old content",
                    source_path="/watch/example.md",
                    original_filename="example.md",
                )
            ],
        )
        active_chunks = repository.create_chunks(
            document["id"],
            active_version["id"],
            [
                ChunkRecord(
                    text="Current content",
                    source_path="/watch/example.md",
                    original_filename="example.md",
                )
            ],
        )
        repository.mark_document_version_active(active_version["id"])

    vector_index.results = [
        VectorSearchResult(
            chunk_id=stale_chunks[0]["id"],
            document_id=document["id"],
            document_version_id=old_version["id"],
            score=0.99,
        ),
        VectorSearchResult(
            chunk_id=active_chunks[0]["id"],
            document_id=document["id"],
            document_version_id=active_version["id"],
            score=0.9,
        ),
    ]
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index

    response = client.post(
        "/search",
        json={"query": "current"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["chunk_id"] == active_chunks[0]["id"]
    assert results[0]["text"] == "Current content"


def test_search_returns_bad_gateway_for_embedding_failure(client: TestClient) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    embedding_client.error = RetrievalError("Embedding service unavailable: refused")
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: FakeVectorIndex()

    response = client.post(
        "/search",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Embedding service unavailable: refused"


def test_search_returns_bad_gateway_for_vector_index_failure(client: TestClient) -> None:
    embedding_client = FakeQueryEmbeddingClient()
    vector_index = FakeVectorIndex()
    vector_index.error = RuntimeError("qdrant unavailable")
    app.dependency_overrides[get_query_embedding_client] = lambda: embedding_client
    app.dependency_overrides[get_vector_index] = lambda: vector_index

    response = client.post(
        "/search",
        json={"query": "alpha"},
        headers=auth_headers(),
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Vector index search failed."
