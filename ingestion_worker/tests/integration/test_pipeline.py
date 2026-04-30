import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config

from ingestion_worker.pipeline import process_next_job
from shared.config import AppSettings
from shared.repository import MetadataRepository, create_metadata_engine
from shared.vector_index import QdrantVectorIndex


def upgrade_database() -> None:
    """Apply Alembic migrations against the integration PostgreSQL database."""
    config = Config("alembic.ini")
    command.upgrade(config, "head")


def test_one_shot_worker_ingests_markdown_into_postgres_and_qdrant(tmp_path: Path) -> None:
    upgrade_database()
    unique = uuid4().hex
    source = tmp_path / f"{unique}.md"
    source.write_text("# Integration\n\nSearchable integration chunk.", encoding="utf-8")
    document_store = tmp_path / "documents"
    collection_name = f"test_ingestion_{unique}"
    settings = AppSettings(
        POSTGRES_URL=os.environ["POSTGRES_URL"],
        QDRANT_URL=os.environ["QDRANT_URL"],
        QDRANT_COLLECTION=collection_name,
        EMBEDDING_SERVICE_URL=os.environ["EMBEDDING_SERVICE_URL"],
        EMBEDDING_MODEL_NAME="embeddinggemma",
        WATCH_ROOTS=str(tmp_path),
        DOCUMENT_STORE_PATH=str(document_store),
    )
    vector_index = QdrantVectorIndex(
        url=os.environ["QDRANT_URL"],
        collection_name=collection_name,
    )
    engine = create_metadata_engine(os.environ["POSTGRES_URL"])

    try:
        with engine.begin() as connection:
            repository = MetadataRepository(connection)
            job = repository.create_ingestion_job(str(source))

        processed = process_next_job(
            worker_id="integration-worker",
            settings=settings,
            engine=engine,
            vector_index=vector_index,
        )

        assert processed is True
        with engine.begin() as connection:
            repository = MetadataRepository(connection)
            updated_job = repository.get_ingestion_job(job["id"])
            documents = repository.list_documents()

        listed = next(row for row in documents if row["document"]["source_path"] == str(source))
        active_version = listed["active_version"]
        assert updated_job["status"] == "active"
        assert updated_job["processed_items"] == 1
        assert active_version["state"] == "active"
        assert active_version["embedding_model_name"] == "embeddinggemma"
        assert active_version["embedding_dimension"] == 8
        assert Path(active_version["managed_store_path"]).exists()

        results = vector_index.search(
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "Searchable integration chunk",
            limit=10,
        )
        assert any(result.document_id == listed["document"]["id"] for result in results)
    finally:
        if vector_index.client.collection_exists(collection_name):
            vector_index.client.delete_collection(collection_name=collection_name)
