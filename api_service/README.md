# API Service

The `api-service` is the public application boundary for the personal RAG system.

## Purpose

The service owns API key authentication, interactive chat/search endpoints, document management endpoints, ingestion-control endpoints, retrieval orchestration, answerability checks, and generation.

Retrieval and generation remain internal modules inside this service for the first implementation. They should still be written behind clear interfaces so they can become separate services later if load or deployment placement requires it.

## Initial API Contract

Implemented in this skeleton:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |
| `POST` | `/ingest` | Create an ingestion job |
| `GET` | `/ingest/{job_id}` | Inspect ingestion job status |
| `GET` | `/documents` | List ingested documents |
| `DELETE` | `/documents/{id}` | Delete a document from the corpus |
| `POST` | `/chat` | Generate or refuse an answer from retrieved chunks |
| `POST` | `/search` | Return hybrid retrieval results with citation metadata |

The chat, search, ingestion, and document endpoints require
`Authorization: Bearer <RAG_API_KEY>`.
`POST /ingest` accepts an optional `requested_path` JSON field for single-file
ingestion; omitting it creates a full-scan job.

`DELETE /documents/{id}` removes the document's Qdrant vectors, source file
under `WATCH_ROOTS`, managed copy under `DOCUMENT_STORE_PATH`, and PostgreSQL
metadata. The first successful delete returns a deletion summary. Unknown
documents and repeated deletes return `404`.

`POST /search` accepts a non-empty `query` string and optional `limit` integer
from 1 through 100.
It embeds the query through `embedding-service`, searches the configured Qdrant
collection with dense vectors, lexical sparse vectors, and sparse-ranked
text-filtered matching, loads active chunk metadata from PostgreSQL, and returns
ranked results with citation fields and retrieval provenance. PostgreSQL
hydrates active metadata only; sparse and full-text matching live in Qdrant.

`POST /chat` accepts the same non-empty `query` string and optional `limit`
integer as search. It runs retrieval first, applies configurable answerability
gates, and refuses without calling generation when evidence is too weak. When
retrieval passes the gates, it sends a non-streaming OpenAI-compatible chat
completion request to the configured `LLM_CHAT_COMPLETIONS_URL` using
`LLM_MODEL`. Local Ollama remains the default private deployment, while external
OpenAI-compatible providers can be configured explicitly. The prompt uses only
the top configured number of retrieved chunks and truncates chunk text in the
prompt without changing stored citations. The response always uses the same
shape:

```json
{
  "answer": "Grounded answer text, or null when refused",
  "citations": [],
  "refused": false,
  "refusal_reason": null
}
```

## Configuration

The service reads configuration from environment variables:

- `RAG_API_KEY`
- `POSTGRES_URL`
- `QDRANT_URL`
- `EMBEDDING_SERVICE_URL`
- `LLM_PROVIDER`
- `LLM_CHAT_COMPLETIONS_URL`
- `LLM_ENDPOINT_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_TIMEOUT_SECONDS`
- `LLM_TEMPERATURE` (optional)
- `LLM_MAX_TOKENS` (optional)
- `CHAT_MIN_TOP_SCORE`
- `CHAT_MIN_USABLE_CHUNKS`
- `CHAT_MAX_CONTEXT_CHUNKS`
- `CHAT_MAX_CHUNK_CHARS`
- `WATCH_ROOTS`
- `DOCUMENT_STORE_PATH`

## Related ADRs

- [ADR 003: Service Boundaries](../adr/003-service-boundaries.md)
- [ADR 007: Retrieval and Answerability](../adr/007-retrieval-and-answerability.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)
- [ADR 009: Provider-Configurable Model Services](../adr/009-provider-configurable-model-services.md)
- [ADR 010: Qdrant-Owned Hybrid Retrieval](../adr/010-qdrant-owned-hybrid-retrieval.md)
