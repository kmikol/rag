# Embedding Service

The `embedding-service` is a dedicated model-serving boundary for query and document embeddings.

## Purpose

The service centralizes embedding model selection, model version, output dimensionality, batching behavior, and runtime placement. Both `api-service` and `ingestion-worker` call this service instead of loading embedding models in-process.

The skeleton uses deterministic fake embeddings so service contracts and tests can be built before choosing a real model.

## API Contract

Implemented:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |
| `GET` | `/model-info` | Current embedding model name and dimensionality |
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
  "model_name": "fake-embedding-model",
  "dimension": 8
}
```

## Configuration

- `EMBEDDING_MODEL_NAME`
- `EMBEDDING_DIMENSION`

## Related ADR

- [ADR 004: Embedding Service](../adr/004-embedding-service.md)
