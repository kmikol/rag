from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from api_service.main import app, get_metadata_engine, open_metadata_repository
from shared.config import get_settings
from shared.db import metadata
from shared.repository import MetadataRepository


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
        get_metadata_engine.cache_clear()


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer unit-token"}


def test_protected_endpoints_require_api_key(client: TestClient) -> None:
    response = client.post("/ingest")

    assert response.status_code == 401


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
