import os
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config

from shared.repository import MetadataRepository, create_metadata_engine


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
