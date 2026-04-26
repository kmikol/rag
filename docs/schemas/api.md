# API Schemas

API schemas are not implemented yet.

Shared conventions already exist for:

| Schema | Purpose |
|--------|---------|
| `HealthResponse` | Standard service health response: `service`, `status` |
| `ErrorResponse` | Standard error envelope: `error`, `message`, optional `request_id` |

Minimum planned API surface:

| Service | Endpoint | Purpose |
|---------|----------|---------|
| `api-service` | `POST /chat` | Chat with retrieved grounding context |
| `api-service` | `POST /search` | Retrieve ranked results without generation |
| `api-service` | `POST /ingest` | Create an ingestion job |
| `api-service` | `GET /ingest/{job_id}` | Inspect ingestion job status |
| `api-service` | `GET /documents` | List ingested documents |
| `api-service` | `DELETE /documents/{id}` | Explicitly remove a document |
| `embedding-service` | `POST /embed` | Embed a single query |
| `embedding-service` | `POST /embed/batch` | Embed document chunks in batches |
| `embedding-service` | `GET /health` | Health check |
| `embedding-service` | `GET /model-info` | Current embedding model identity |
