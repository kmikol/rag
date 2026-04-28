from sqlalchemy import create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from shared.db import metadata
from shared.repository import ChunkRecord, MetadataRepository, validate_state


def open_repository() -> tuple[MetadataRepository, Connection]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    connection = engine.connect()
    return MetadataRepository(connection), connection


def test_validate_state_rejects_unknown_state() -> None:
    try:
        validate_state("unknown")
    except ValueError as error:
        assert "Unsupported state" in str(error)
    else:
        raise AssertionError("Expected ValueError for unknown state")


def test_create_and_update_ingestion_job() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            job = repo.create_ingestion_job("/watch/example.md")

            assert job["requested_path"] == "/watch/example.md"
            assert job["status"] == "pending"

            updated = repo.update_ingestion_job(job["id"], "failed", 2, "parse failed")

            assert updated["status"] == "failed"
            assert updated["processed_items"] == 2
            assert updated["error_message"] == "parse failed"
            assert updated["completed_at"] is not None
    finally:
        connection.close()


def test_update_ingestion_job_preserves_error_when_omitted() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            job = repo.create_ingestion_job("/watch/example.md")

            repo.update_ingestion_job(job["id"], "failed", 2, "parse failed")
            updated = repo.update_ingestion_job(job["id"], "failed", 3)

            assert updated["processed_items"] == 3
            assert updated["error_message"] == "parse failed"
    finally:
        connection.close()


def test_claim_next_ingestion_job_marks_job_running() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            repo.create_ingestion_job()

            claimed = repo.claim_next_ingestion_job("worker-1")

            assert claimed is not None
            assert claimed["status"] == "running"
            assert claimed["worker_id"] == "worker-1"
            assert claimed["lease_expires_at"] is not None
            assert repo.claim_next_ingestion_job("worker-2") is None
    finally:
        connection.close()


def test_get_or_create_document_returns_existing_source_path() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            first = repo.get_or_create_document("/watch/example.md")
            second = repo.get_or_create_document("/watch/example.md")

            assert second["id"] == first["id"]
            assert second["source_path"] == "/watch/example.md"
    finally:
        connection.close()


def test_document_version_activation_switches_active_version() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            document = repo.get_or_create_document("/watch/example.md")
            first_version = repo.create_document_version(document["id"], "a" * 64)
            second_version = repo.create_document_version(document["id"], "b" * 64)

            repo.mark_document_version_active(first_version["id"])
            active_document = repo.mark_document_version_active(second_version["id"])

            assert active_document["document"]["active_document_version_id"] == second_version["id"]
            assert active_document["active_version"]["content_hash"] == "b" * 64
    finally:
        connection.close()


def test_update_document_and_version_state_persists_metadata() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            document = repo.get_or_create_document("/watch/example.md")
            version = repo.create_document_version(document["id"], "a" * 64)

            updated_document = repo.update_document_state(document["id"], "running")
            updated_version = repo.update_document_version_state(
                version["id"],
                "embedded",
                embedding_model_name="fake-model",
                embedding_dimension=8,
            )

            assert updated_document["state"] == "running"
            assert updated_version["state"] == "embedded"
            assert updated_version["embedding_model_name"] == "fake-model"
            assert updated_version["embedding_dimension"] == 8
    finally:
        connection.close()


def test_list_documents_returns_active_versions() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            first_document = repo.get_or_create_document("/watch/one.md")
            second_document = repo.get_or_create_document("/watch/two.md")
            first_version = repo.create_document_version(first_document["id"], "a" * 64)
            second_version = repo.create_document_version(second_document["id"], "b" * 64)
            repo.mark_document_version_active(first_version["id"])
            repo.mark_document_version_active(second_version["id"])

            listed = repo.list_documents()

            versions_by_document_id = {
                row["document"]["id"]: row["active_version"]["id"] for row in listed
            }
            assert versions_by_document_id[first_document["id"]] == first_version["id"]
            assert versions_by_document_id[second_document["id"]] == second_version["id"]
    finally:
        connection.close()


def test_duplicate_content_hash_is_rejected() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            first_document = repo.get_or_create_document("/watch/one.md")
            second_document = repo.get_or_create_document("/watch/two.md")
            repo.create_document_version(first_document["id"], "a" * 64)

            try:
                repo.create_document_version(second_document["id"], "a" * 64)
            except IntegrityError:
                pass
            else:
                raise AssertionError("Expected duplicate content hash to be rejected")
    finally:
        connection.close()


def test_create_chunks_preserves_citation_metadata() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            document = repo.get_or_create_document("/watch/example.md")
            version = repo.create_document_version(document["id"], "a" * 64)

            chunks = repo.create_chunks(
                document["id"],
                version["id"],
                [
                    ChunkRecord(
                        text="Chunk text",
                        source_path="/watch/example.md",
                        original_filename="example.md",
                        heading_path=["Title", "Section"],
                        section_title="Section",
                        start_offset=10,
                        end_offset=20,
                        token_count=2,
                    )
                ],
            )

            assert chunks[0]["ordinal"] == 0
            assert chunks[0]["heading_path"] == ["Title", "Section"]
            assert chunks[0]["section_title"] == "Section"
            assert chunks[0]["token_count"] == 2
    finally:
        connection.close()


def test_get_active_chunks_by_ids_returns_only_active_version_chunks() -> None:
    repo, connection = open_repository()
    try:
        with connection.begin():
            document = repo.get_or_create_document("/watch/example.md")
            first_version = repo.create_document_version(document["id"], "a" * 64)
            second_version = repo.create_document_version(document["id"], "b" * 64)
            first_chunks = repo.create_chunks(
                document["id"],
                first_version["id"],
                [
                    ChunkRecord(
                        text="Old chunk",
                        source_path="/watch/example.md",
                        original_filename="example.md",
                    )
                ],
            )
            second_chunks = repo.create_chunks(
                document["id"],
                second_version["id"],
                [
                    ChunkRecord(
                        text="Current chunk",
                        source_path="/watch/example.md",
                        original_filename="example.md",
                    )
                ],
            )
            repo.mark_document_version_active(second_version["id"])

            chunks = repo.get_active_chunks_by_ids(
                [first_chunks[0]["id"], second_chunks[0]["id"], "missing"]
            )

            assert list(chunks) == [second_chunks[0]["id"]]
            assert chunks[second_chunks[0]["id"]]["text"] == "Current chunk"
    finally:
        connection.close()


def test_get_active_chunks_by_ids_handles_empty_input() -> None:
    repo, connection = open_repository()
    try:
        assert repo.get_active_chunks_by_ids([]) == {}
    finally:
        connection.close()
