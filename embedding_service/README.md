# Embedding Service

The `embedding-service` is a dedicated model-serving boundary for query and document embeddings.

## Purpose

The service centralizes embedding model selection, model version, output dimensionality, batching behavior, and runtime placement. Both `api-service` and `ingestion-worker` call this service instead of loading embedding models in-process.

The service supports three embedding backends:

- `fake`: deterministic fake embeddings for tests and contract validation.
- `ollama`: runtime embeddings via Ollama's `/api/embed` endpoint.
- `google`: runtime embeddings via Google AI Studio's REST `embedContent` endpoint.

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
  "embedding_model_name": "embeddinggemma",
  "dimension": 2
}
```

## Configuration

- `EMBEDDING_BACKEND` (`fake`, `ollama`, or `google`)
- `EMBEDDING_MODEL_NAME`
- `EMBEDDING_DIMENSION`
- `EMBEDDING_ENDPOINT_URL`
- `EMBEDDING_API_KEY` (required for external providers)
- `EMBEDDING_TIMEOUT_SECONDS`
- `EMBEDDING_KEEP_ALIVE` (used by the Ollama backend)

The service does not auto-pull local models. Ollama must already have the
configured model available. External providers are not private/self-hosted:
document chunks and query text sent for embedding leave the deployment.

## Related ADR

- [ADR 004: Embedding Service](../adr/004-embedding-service.md)
- [ADR 009: Provider-Configurable Model Services](../adr/009-provider-configurable-model-services.md)
