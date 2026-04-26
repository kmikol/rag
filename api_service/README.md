# API Service

The `api-service` is the public application boundary for the personal RAG system.

## Purpose

The service owns API key authentication, interactive chat/search endpoints, document management endpoints, ingestion-control endpoints, retrieval orchestration, answerability checks, and streaming generation.

Retrieval and generation remain internal modules inside this service for the first implementation. They should still be written behind clear interfaces so they can become separate services later if load or deployment placement requires it.

## Initial API Contract

Implemented in this skeleton:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |

Planned:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/chat` | Generate an answer grounded in retrieved chunks |
| `POST` | `/search` | Return ranked chunks without generation |
| `POST` | `/ingest` | Create an ingestion job |
| `GET` | `/ingest/{job_id}` | Inspect ingestion job status |
| `GET` | `/documents` | List ingested documents |
| `DELETE` | `/documents/{id}` | Delete a document from the corpus |

## Configuration

The service reads configuration from environment variables:

- `RAG_API_KEY`
- `POSTGRES_URL`
- `QDRANT_URL`
- `EMBEDDING_SERVICE_URL`
- `OLLAMA_URL`
- `WATCH_ROOTS`
- `DOCUMENT_STORE_PATH`

## Related ADRs

- [ADR 003: Service Boundaries](../adr/003-service-boundaries.md)
- [ADR 007: Retrieval and Answerability](../adr/007-retrieval-and-answerability.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)
