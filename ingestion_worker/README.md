# Ingestion Worker

The `ingestion-worker` owns background document processing.

## Purpose

The worker claims ingestion jobs, scans configured watch roots, reconciles the index against the filesystem source of truth, parses supported files, chunks text, calls `embedding-service`, and writes metadata/vectors/document copies.

This skeleton exposes a health endpoint only. Job claiming, parsing, chunking, and indexing will be added in the first ingestion milestone.

## API Contract

Implemented:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |

The worker is primarily job-driven through PostgreSQL-backed job records, not an external public API.

## Configuration

- `POSTGRES_URL`
- `QDRANT_URL`
- `EMBEDDING_SERVICE_URL`
- `WATCH_ROOTS`
- `DOCUMENT_STORE_PATH`

## Related ADRs

- [ADR 001: Data Sources and Ingestion](../adr/001-data-sources-and-ingestion.md)
- [ADR 005: Document Identity and Ingestion State](../adr/005-document-identity-and-ingestion-state.md)
- [ADR 006: Chunking Strategy](../adr/006-chunking-strategy.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)
