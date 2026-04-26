# Embedding Service

The `embedding-service` is a dedicated model-serving boundary for query and document embeddings.

## Purpose

The service centralizes embedding model selection, model version, output dimensionality, batching behavior, and runtime placement. Both `api-service` and `ingestion-worker` call this service instead of loading embedding models in-process.

The service supports two embedding backends:

- `fake`: deterministic fake embeddings for tests and contract validation.
- `ollama`: runtime embeddings via Ollama's `/api/embed` endpoint.

## API Contract

Implemented:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |
| `GET` | `/model-info` | Current embedding backend, model name, and configured dimensionality |
| `POST` | `/embed` | Embed one text input |
| `POST` | `/embed/batch` | Embed a batch of text inputs |

### `POST /embed`

Request:

```json
{
  "text": "example query"
}
```

Response:

```json
{
  "embedding": [0.1, 0.2],
  "model_name": "embeddinggemma",
  "dimension": 2
}
```

## Configuration

- `EMBEDDING_BACKEND` (`fake` or `ollama`)
- `EMBEDDING_MODEL_NAME`
- `EMBEDDING_DIMENSION`
- `OLLAMA_URL`
- `OLLAMA_EMBED_TIMEOUT_SECONDS`
- `OLLAMA_KEEP_ALIVE`

The service does not auto-pull models. Ollama must already have the configured model available.

## Related ADR

- [ADR 004: Embedding Service](../adr/004-embedding-service.md)
