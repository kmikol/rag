# Shared

The `shared` module contains cross-service code used by the API service, ingestion worker,
and embedding service.

## Purpose

Shared code keeps service contracts consistent without introducing a separate metadata
service. PostgreSQL remains the durable coordination boundary; this package only provides
the Python table definitions and repository helpers used by the services.

## Responsibilities

- Environment configuration.
- Logging setup.
- Shared API response schemas.
- SQLAlchemy metadata table definitions for PostgreSQL.
- A small repository layer for document metadata, chunks, and ingestion jobs.
- A small Qdrant vector-index client for hybrid chunk retrieval.

## Callable Contract

`shared.repository.MetadataRepository` is initialized with a SQLAlchemy connection inside
an explicit transaction. It supports:

- creating and claiming ingestion jobs;
- updating job status and progress;
- creating logical documents and immutable document versions;
- activating a document version;
- persisting citation-ready chunk records;
- listing documents with active-version metadata;
- loading document deletion targets and hard-deleting document metadata.

`shared.repository.create_metadata_engine` creates the SQLAlchemy engine from
`POSTGRES_URL`.

`shared.vector_index.QdrantVectorIndex` is initialized from `QDRANT_URL` and
`QDRANT_COLLECTION`. It creates or verifies the hybrid chunk collection for a
caller-provided embedding dimension, upserts dense vectors, deterministic
lexical sparse vectors, and chunk text payloads, deletes points by `document_id`
or `document_version_id`, and returns fused retrieval results with provenance
and payload IDs needed to load chunk metadata from PostgreSQL.

Collections must use named vectors `dense` and `sparse` plus a text payload
index on `text`. Legacy unnamed-vector collections are rejected with guidance to
recreate the collection and reingest.

## Configuration

- `POSTGRES_URL`
- `QDRANT_URL`
- `QDRANT_COLLECTION`

## Related ADRs

- [ADR 002: Storage and Metadata Topology](../docs/adr/002-storage-and-metadata-topology.md)
- [ADR 005: Document Identity and Ingestion State](../docs/adr/005-document-identity-and-ingestion-state.md)
- [ADR 007: Retrieval and Answerability](../docs/adr/007-retrieval-and-answerability.md)
- [ADR 008: Job Coordination and Service Contracts](../docs/adr/008-job-coordination-and-service-contracts.md)
- [ADR 010: Qdrant-Owned Hybrid Retrieval](../docs/adr/010-qdrant-owned-hybrid-retrieval.md)

## Testing Helpers

No shared testing helper is exported yet. Module-owned tests use in-memory SQLite for pure
repository behavior and PostgreSQL integration tests for migrations and row-locking semantics.
