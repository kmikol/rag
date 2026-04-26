from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

DOCUMENT_STATES = (
    "pending",
    "running",
    "copied",
    "parsed",
    "chunked",
    "embedded",
    "indexed",
    "active",
    "failed",
    "deleting",
    "deleted",
)

metadata = MetaData()


def state_check_constraint(column_name: str, constraint_name: str) -> CheckConstraint:
    """Build a database check constraint for ADR-005 lifecycle states."""
    quoted_states = ", ".join(f"'{state}'" for state in DOCUMENT_STATES)
    return CheckConstraint(f"{column_name} IN ({quoted_states})", name=constraint_name)


documents = Table(
    "documents",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("source_path", Text, nullable=False, unique=True),
    Column("original_filename", Text, nullable=False),
    Column("active_document_version_id", String(36), nullable=True),
    Column("state", String(32), nullable=False, server_default="pending"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
    state_check_constraint("state", "ck_documents_state"),
)

document_versions = Table(
    "document_versions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "document_id", String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    ),
    Column("content_hash", String(64), nullable=False),
    Column("managed_store_path", Text, nullable=True),
    Column("state", String(32), nullable=False, server_default="pending"),
    Column("embedding_model_name", Text, nullable=True),
    Column("embedding_dimension", Integer, nullable=True),
    Column("chunking_strategy", Text, nullable=False, server_default="structure-aware-v1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("activated_at", DateTime(timezone=True), nullable=True),
    Column("error_message", Text, nullable=True),
    state_check_constraint("state", "ck_document_versions_state"),
    UniqueConstraint("content_hash", name="uq_document_versions_content_hash"),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "document_id", String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    ),
    Column(
        "document_version_id",
        String(36),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("source_path", Text, nullable=False),
    Column("original_filename", Text, nullable=False),
    Column("page_number", Integer, nullable=True),
    Column("heading_path", JSON, nullable=True),
    Column("section_title", Text, nullable=True),
    Column("start_offset", Integer, nullable=True),
    Column("end_offset", Integer, nullable=True),
    Column("token_count", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("document_version_id", "ordinal", name="uq_chunks_version_ordinal"),
)

ingestion_jobs = Table(
    "ingestion_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("requested_path", Text, nullable=True),
    Column("status", String(32), nullable=False, server_default="pending"),
    Column("worker_id", Text, nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("processed_items", Integer, nullable=False, server_default="0"),
    Column("error_message", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    state_check_constraint("status", "ck_ingestion_jobs_status"),
)

Index("ix_document_versions_document_id", document_versions.c.document_id)
Index("ix_document_versions_content_hash", document_versions.c.content_hash)
Index("ix_chunks_document_version_id", chunks.c.document_version_id)
Index("ix_ingestion_jobs_status_created_at", ingestion_jobs.c.status, ingestion_jobs.c.created_at)
