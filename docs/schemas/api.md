# API Schemas

Shared conventions already exist for:

| Schema | Purpose |
|--------|---------|
| `HealthResponse` | Standard service health response: `service`, `status` |
| `ErrorResponse` | Standard error envelope: `error`, `message`, optional `request_id` |

Search schemas:

| Schema | Purpose |
|--------|---------|
| `SearchRequest` | Request body for `POST /search`: non-empty `query`, optional `limit` from 1 through 100 defaulting to 10 |
| `SearchResponse` | Search response containing ranked `results` |
| `SearchResult` | Citation-ready chunk result with score, text, document/version/chunk ids, source path, filename, page/heading metadata, and text offsets |

Minimum planned API surface:

| Service | Endpoint | Purpose |
|---------|----------|---------|
| `api-service` | `POST /chat` | Chat with retrieved grounding context |
| `api-service` | `POST /search` | Retrieve dense ranked results without generation |
| `api-service` | `POST /ingest` | Create an ingestion job |
| `api-service` | `GET /ingest/{job_id}` | Inspect ingestion job status |
| `api-service` | `GET /documents` | List ingested documents |
| `api-service` | `DELETE /documents/{id}` | Explicitly remove a document |
| `embedding-service` | `POST /embed` | Embed a single query |
| `embedding-service` | `POST /embed/batch` | Embed document chunks in batches |
| `embedding-service` | `GET /health` | Health check |
| `embedding-service` | `GET /model-info` | Current embedding model identity |
