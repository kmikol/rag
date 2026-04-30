import os
from pathlib import Path
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config

from embedding_service.testing.mocks import make_fake_embedding
from shared.repository import ChunkRecord, MetadataRepository, create_metadata_engine
from shared.vector_index import ChunkVector, QdrantVectorIndex


def upgrade_database() -> None:
    """Apply Alembic migrations against the integration PostgreSQL database."""
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


def test_ingestion_endpoints_persist_jobs() -> None:
    upgrade_database()
    base_url = os.environ["API_SERVICE_URL"]
    source_path = f"/watch/{uuid4().hex}.md"

    created = httpx.post(
        f"{base_url}/ingest",
        json={"requested_path": source_path},
        headers=auth_headers(),
        timeout=5,
    )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["requested_path"] == source_path
    assert created_body["status"] == "pending"

    fetched = httpx.get(
        f"{base_url}/ingest/{created_body['id']}",
        headers=auth_headers(),
        timeout=5,
    )

    assert fetched.status_code == 200
    assert fetched.json()["id"] == created_body["id"]
    assert fetched.json()["status"] == "pending"

    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        repository.update_ingestion_job(created_body["id"], "failed")


def test_documents_endpoint_lists_metadata_backed_documents() -> None:
    upgrade_database()
    base_url = os.environ["API_SERVICE_URL"]
    unique = uuid4().hex
    source_path = f"/watch/{unique}.md"

    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document(source_path)
        version = repository.create_document_version(document["id"], f"{unique}{unique}")
        repository.mark_document_version_active(version["id"])

    response = httpx.get(
        f"{base_url}/documents",
        headers=auth_headers(),
        timeout=5,
    )

    assert response.status_code == 200
    documents = response.json()["documents"]
    listed = next(document for document in documents if document["source_path"] == source_path)
    assert listed["id"] == document["id"]
    assert listed["active_version"]["id"] == version["id"]


def test_search_endpoint_returns_qdrant_backed_citations() -> None:
    upgrade_database()
    base_url = os.environ["API_SERVICE_URL"]
    query = f"searchable integration phrase {uuid4().hex}"
    unique = uuid4().hex
    source_path = f"/watch/{unique}.md"

    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    vector_index = QdrantVectorIndex(url=os.environ["QDRANT_URL"])
    vector_index.ensure_collection(8)

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document(source_path)
        version = repository.create_document_version(document["id"], f"{unique}{unique}")
        chunks = repository.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="Integration search result",
                    source_path=source_path,
                    original_filename=f"{unique}.md",
                    page_number=2,
                    heading_path=["Integration"],
                    section_title="Integration",
                    start_offset=0,
                    end_offset=25,
                )
            ],
        )
        repository.mark_document_version_active(version["id"])

    try:
        vector_index.upsert_chunks(
            [
                ChunkVector(
                    chunk_id=chunks[0]["id"],
                    document_id=document["id"],
                    document_version_id=version["id"],
                    vector=make_fake_embedding(query, 8),
                    text="Integration search result",
                )
            ]
        )

        response = httpx.post(
            f"{base_url}/search",
            json={"query": query, "limit": 1},
            headers=auth_headers(),
            timeout=5,
        )

        assert response.status_code == 200
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["chunk_id"] == chunks[0]["id"]
        assert results[0]["document_id"] == document["id"]
        assert results[0]["document_version_id"] == version["id"]
        assert results[0]["source_path"] == source_path
        assert results[0]["page_number"] == 2
        assert results[0]["heading_path"] == ["Integration"]
    finally:
        vector_index.delete_by_document_id(document["id"])


def test_delete_document_endpoint_removes_files_metadata_and_qdrant_vectors() -> None:
    upgrade_database()
    base_url = os.environ["API_SERVICE_URL"]
    query = f"delete integration phrase {uuid4().hex}"
    unique = uuid4().hex
    watch_root = Path(os.environ["WATCH_ROOTS"].split(os.pathsep)[0])
    document_store = Path(os.environ["DOCUMENT_STORE_PATH"])
    source_path = watch_root / f"{unique}.md"
    managed_path = document_store / unique[:2] / f"{unique}.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    managed_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("# Delete\n\nDelete integration content.", encoding="utf-8")
    managed_path.write_text("# Delete\n\nManaged integration copy.", encoding="utf-8")

    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    vector_index = QdrantVectorIndex(url=os.environ["QDRANT_URL"])
    vector_index.ensure_collection(8)

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document(str(source_path))
        version = repository.create_document_version(
            document["id"],
            f"{unique}{unique}",
            str(managed_path),
        )
        chunks = repository.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="Delete integration content",
                    source_path=str(source_path),
                    original_filename=source_path.name,
                )
            ],
        )
        repository.mark_document_version_active(version["id"])

    try:
        vector_index.upsert_chunks(
            [
                ChunkVector(
                    chunk_id=chunks[0]["id"],
                    document_id=document["id"],
                    document_version_id=version["id"],
                    vector=make_fake_embedding(query, 8),
                    text="Delete integration content",
                )
            ]
        )

        deleted = httpx.delete(
            f"{base_url}/documents/{document['id']}",
            headers=auth_headers(),
            timeout=5,
        )

        assert deleted.status_code == 200
        assert deleted.json()["id"] == document["id"]
        assert deleted.json()["source_file_deleted"] is True
        assert not source_path.exists()
        assert not managed_path.exists()

        search = httpx.post(
            f"{base_url}/search",
            json={"query": query, "limit": 1},
            headers=auth_headers(),
            timeout=5,
        )

        assert search.status_code == 200
        assert search.json()["results"] == []
        with engine.begin() as connection:
            repository = MetadataRepository(connection)
            assert repository.get_document_deletion_target(document["id"]) is None
    finally:
        vector_index.delete_by_document_id(document["id"])
        if source_path.exists():
            source_path.unlink()
        if managed_path.exists():
            managed_path.unlink()
