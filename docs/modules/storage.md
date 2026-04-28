# Storage

Storage is split across central durable services.

| Component | Default placement | Purpose |
|-----------|-------------------|---------|
| PostgreSQL | NAS | Metadata, source paths, document versions, chunks, jobs |
| Qdrant | NAS, movable by URL | Dense vector index |
| Managed document store | NAS | Copied originals for reprocessing and auditability |
| Watch roots | Configured filesystem paths | Authoritative corpus source |

## PostgreSQL Metadata

The first metadata schema is implemented with Alembic migrations and SQLAlchemy table
definitions in `shared.db`.

PostgreSQL stores:

- logical documents keyed by stable `document_id`;
- immutable document versions keyed by `document_version_id`;
- citation-ready chunk records;
- persisted ingestion jobs with worker lease fields.

Services use `shared.repository.MetadataRepository` inside explicit transactions. The
repository is shared by `api-service` and `ingestion-worker`; it is not a standalone
metadata service.

## Qdrant Vector Index

Qdrant stores chunk embeddings in the configured `QDRANT_COLLECTION`. Services use
`shared.vector_index.QdrantVectorIndex` to create or verify the collection, upsert
chunk vectors, delete vectors by document or document version, and run dense vector
searches that return payload IDs used to load chunk metadata from PostgreSQL.

Related decisions:

- [ADR 001: Data Sources and Ingestion](../adr/001-data-sources-and-ingestion.md)
- [ADR 002: Storage and Metadata Topology](../adr/002-storage-and-metadata-topology.md)
- [ADR 005: Document Identity and Ingestion State](../adr/005-document-identity-and-ingestion-state.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)
