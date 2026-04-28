from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, Row, Select, create_engine, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Connection

from shared.db import DOCUMENT_STATES, chunks, document_versions, documents, ingestion_jobs


def create_metadata_engine(postgres_url: str) -> Engine:
    """Create the SQLAlchemy engine used by services for metadata access."""
    return create_engine(postgres_url, pool_pre_ping=True)


def utc_now() -> datetime:
    """Return a timezone-aware timestamp for persisted metadata records."""
    return datetime.now(UTC)


def new_id() -> str:
    """Return a stable string UUID for records shared across services."""
    return str(uuid4())


def validate_state(state: str) -> None:
    """Reject lifecycle states that are not defined by ADR-005."""
    if state not in DOCUMENT_STATES:
        allowed = ", ".join(DOCUMENT_STATES)
        raise ValueError(f"Unsupported state '{state}'. Expected one of: {allowed}")


@dataclass(frozen=True)
class ChunkRecord:
    """Citation-ready chunk data produced by ingestion before vector indexing."""

    text: str
    source_path: str
    original_filename: str
    page_number: int | None = None
    heading_path: list[str] | None = None
    section_title: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    token_count: int | None = None


class MetadataRepository:
    """Persist document metadata and ingestion jobs in PostgreSQL.

    The repository is intentionally small and explicit because both
    `api-service` and `ingestion-worker` need a stable contract before the full
    ingestion pipeline exists.
    """

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create_ingestion_job(self, requested_path: str | None = None) -> dict[str, Any]:
        """Create a pending ingestion job for a full scan or single path."""
        job_id = new_id()
        row = {
            "id": job_id,
            "requested_path": requested_path,
            "status": "pending",
            "processed_items": 0,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        self.connection.execute(ingestion_jobs.insert().values(row))
        return self.get_ingestion_job(job_id)

    def get_ingestion_job(self, job_id: str) -> dict[str, Any]:
        """Return one ingestion job by id."""
        row = (
            self.connection.execute(select(ingestion_jobs).where(ingestion_jobs.c.id == job_id))
            .mappings()
            .one()
        )
        return dict(row)

    def claim_next_ingestion_job(
        self,
        worker_id: str,
        lease_seconds: int = 300,
    ) -> dict[str, Any] | None:
        """Claim the oldest pending job using PostgreSQL row locking."""
        locked_job: Select[Any] = (
            select(ingestion_jobs.c.id)
            .where(ingestion_jobs.c.status == "pending")
            .order_by(ingestion_jobs.c.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job_id = self.connection.execute(locked_job).scalar_one_or_none()
        if job_id is None:
            return None

        now = utc_now()
        self.connection.execute(
            update(ingestion_jobs)
            .where(ingestion_jobs.c.id == job_id)
            .values(
                status="running",
                worker_id=worker_id,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                started_at=now,
                updated_at=now,
            )
        )
        return self.get_ingestion_job(job_id)

    def update_ingestion_job(
        self,
        job_id: str,
        status: str,
        processed_items: int | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """Update persisted job progress and terminal error details."""
        validate_state(status)
        now = utc_now()
        values: dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if error_message is not None:
            values["error_message"] = error_message
        if processed_items is not None:
            values["processed_items"] = processed_items
        if status in {"active", "failed", "deleted"}:
            values["completed_at"] = now

        self.connection.execute(
            update(ingestion_jobs).where(ingestion_jobs.c.id == job_id).values(values)
        )
        return self.get_ingestion_job(job_id)

    def update_document_state(self, document_id: str, state: str) -> dict[str, Any]:
        """Update the lifecycle state for one logical document."""
        validate_state(state)
        self.connection.execute(
            update(documents)
            .where(documents.c.id == document_id)
            .values(state=state, updated_at=utc_now())
        )
        return dict(
            self.connection.execute(select(documents).where(documents.c.id == document_id))
            .mappings()
            .one()
        )

    def update_document_version_state(
        self,
        document_version_id: str,
        state: str,
        error_message: str | None = None,
        embedding_model_name: str | None = None,
        embedding_dimension: int | None = None,
    ) -> dict[str, Any]:
        """Update lifecycle and embedding metadata for one document version."""
        validate_state(state)
        values: dict[str, Any] = {"state": state}
        if error_message is not None:
            values["error_message"] = error_message
        if embedding_model_name is not None:
            values["embedding_model_name"] = embedding_model_name
        if embedding_dimension is not None:
            values["embedding_dimension"] = embedding_dimension

        self.connection.execute(
            update(document_versions)
            .where(document_versions.c.id == document_version_id)
            .values(values)
        )
        return dict(
            self.connection.execute(
                select(document_versions).where(document_versions.c.id == document_version_id)
            )
            .mappings()
            .one()
        )

    def find_document_version_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        """Return an existing document version with matching raw-byte SHA-256."""
        row = (
            self.connection.execute(
                select(document_versions).where(document_versions.c.content_hash == content_hash)
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    def get_or_create_document(self, source_path: str) -> dict[str, Any]:
        """Return a logical document for a source path, creating it if needed."""
        if self.connection.dialect.name == "postgresql":
            return self._get_or_create_document_postgresql(source_path)

        existing = (
            self.connection.execute(select(documents).where(documents.c.source_path == source_path))
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            return dict(existing)

        document_id = new_id()
        now = utc_now()
        row = {
            "id": document_id,
            "source_path": source_path,
            "original_filename": Path(source_path).name,
            "state": "pending",
            "created_at": now,
            "updated_at": now,
        }
        self.connection.execute(documents.insert().values(row))
        return dict(
            self.connection.execute(select(documents).where(documents.c.id == document_id))
            .mappings()
            .one()
        )

    def _get_or_create_document_postgresql(self, source_path: str) -> dict[str, Any]:
        """Create a document atomically on PostgreSQL to avoid worker races."""
        now = utc_now()
        row = {
            "id": new_id(),
            "source_path": source_path,
            "original_filename": Path(source_path).name,
            "state": "pending",
            "created_at": now,
            "updated_at": now,
        }
        inserted = (
            self.connection.execute(
                postgresql_insert(documents)
                .values(row)
                .on_conflict_do_nothing(index_elements=[documents.c.source_path])
                .returning(documents)
            )
            .mappings()
            .one_or_none()
        )
        if inserted is not None:
            return dict(inserted)

        existing = (
            self.connection.execute(select(documents).where(documents.c.source_path == source_path))
            .mappings()
            .one()
        )
        return dict(existing)

    def create_document_version(
        self,
        document_id: str,
        content_hash: str,
        managed_store_path: str | None = None,
    ) -> dict[str, Any]:
        """Create an immutable indexed-content version for a logical document."""
        version_id = new_id()
        row = {
            "id": version_id,
            "document_id": document_id,
            "content_hash": content_hash,
            "managed_store_path": managed_store_path,
            "state": "pending",
            "created_at": utc_now(),
        }
        self.connection.execute(document_versions.insert().values(row))
        return dict(
            self.connection.execute(
                select(document_versions).where(document_versions.c.id == version_id)
            )
            .mappings()
            .one()
        )

    def mark_document_version_active(self, document_version_id: str) -> dict[str, Any]:
        """Activate one document version and make it the queryable version."""
        version = (
            self.connection.execute(
                select(document_versions).where(document_versions.c.id == document_version_id)
            )
            .mappings()
            .one()
        )
        now = utc_now()
        self.connection.execute(
            update(document_versions)
            .where(document_versions.c.id == document_version_id)
            .values(state="active", activated_at=now)
        )
        self.connection.execute(
            update(documents)
            .where(documents.c.id == version["document_id"])
            .values(
                active_document_version_id=document_version_id,
                state="active",
                updated_at=now,
            )
        )
        return self.get_document_with_active_version(version["document_id"])

    def create_chunks(
        self,
        document_id: str,
        document_version_id: str,
        chunk_records: list[ChunkRecord],
    ) -> list[dict[str, Any]]:
        """Persist citation metadata for chunks that will also be indexed in Qdrant."""
        rows = [
            {
                "id": new_id(),
                "document_id": document_id,
                "document_version_id": document_version_id,
                "ordinal": ordinal,
                "text": chunk.text,
                "source_path": chunk.source_path,
                "original_filename": chunk.original_filename,
                "page_number": chunk.page_number,
                "heading_path": chunk.heading_path,
                "section_title": chunk.section_title,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
                "token_count": chunk.token_count,
                "created_at": utc_now(),
            }
            for ordinal, chunk in enumerate(chunk_records)
        ]
        if rows:
            self.connection.execute(chunks.insert().values(rows))

        result = self.connection.execute(
            select(chunks)
            .where(chunks.c.document_version_id == document_version_id)
            .order_by(chunks.c.ordinal)
        ).mappings()
        return [dict(row) for row in result]

    def get_document_with_active_version(self, document_id: str) -> dict[str, Any]:
        """Return a document and its active version metadata."""
        document = (
            self.connection.execute(select(documents).where(documents.c.id == document_id))
            .mappings()
            .one()
        )
        version = None
        if document["active_document_version_id"] is not None:
            version = (
                self.connection.execute(
                    select(document_versions).where(
                        document_versions.c.id == document["active_document_version_id"]
                    )
                )
                .mappings()
                .one()
            )
        return {"document": dict(document), "active_version": dict(version) if version else None}

    def list_documents(self) -> list[dict[str, Any]]:
        """List logical documents with active-version metadata for API responses."""
        active_version = document_versions.alias("active_version")
        rows = self.connection.execute(
            select(documents, active_version)
            .outerjoin(
                active_version,
                active_version.c.id == documents.c.active_document_version_id,
            )
            .order_by(documents.c.created_at)
        )
        return [self._build_document_with_active_version(row, active_version) for row in rows]

    def _build_document_with_active_version(
        self,
        row: Row[Any],
        active_version: Any,
    ) -> dict[str, Any]:
        """Build API-shaped document data from a joined document/version row."""
        row_mapping = row._mapping
        document = {column.name: row_mapping[column] for column in documents.c}

        version = None
        if row_mapping[active_version.c.id] is not None:
            version = {column.name: row_mapping[column] for column in active_version.c}

        return {"document": document, "active_version": version}
