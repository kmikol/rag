import os
from uuid import uuid4

from alembic import command
from alembic.config import Config

from shared.repository import ChunkRecord, MetadataRepository, create_metadata_engine


def upgrade_database() -> None:
    """Apply Alembic migrations against the integration PostgreSQL database."""
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def test_alembic_upgrade_and_repository_round_trip() -> None:
    upgrade_database()
    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    unique = uuid4().hex
    source_path = f"/watch/{unique}.md"
    content_hash = f"{unique}{unique}"

    with engine.begin() as connection:
        repo = MetadataRepository(connection)
        job = repo.create_ingestion_job(source_path)
        claimed = repo.claim_next_ingestion_job("integration-worker")
        assert claimed is not None
        assert claimed["id"] == job["id"]
        assert claimed["status"] == "running"

        document = repo.get_or_create_document(source_path)
        version = repo.create_document_version(document["id"], content_hash)
        repo.create_chunks(
            document["id"],
            version["id"],
            [
                ChunkRecord(
                    text="PostgreSQL backed chunk",
                    source_path=source_path,
                    original_filename=f"{unique}.md",
                    page_number=1,
                )
            ],
        )
        active_document = repo.mark_document_version_active(version["id"])

        assert active_document["document"]["state"] == "active"
        assert active_document["active_version"]["id"] == version["id"]
        document_ids = {row["document"]["id"] for row in repo.list_documents()}
        assert document["id"] in document_ids


def test_claiming_pending_jobs_does_not_return_running_jobs() -> None:
    upgrade_database()
    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    unique = uuid4().hex

    with engine.begin() as connection:
        repo = MetadataRepository(connection)
        first = repo.create_ingestion_job(f"/watch/{unique}-one.md")
        second = repo.create_ingestion_job(f"/watch/{unique}-two.md")

    with engine.begin() as connection:
        repo = MetadataRepository(connection)
        claimed = repo.claim_next_ingestion_job("worker-1")
        assert claimed is not None
        assert claimed["id"] in {first["id"], second["id"]}

    with engine.begin() as connection:
        repo = MetadataRepository(connection)
        claimed = repo.claim_next_ingestion_job("worker-2")
        assert claimed is not None
        assert claimed["id"] in {first["id"], second["id"]}
        assert claimed["worker_id"] == "worker-2"
