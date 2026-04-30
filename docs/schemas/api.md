# API Schemas

Shared conventions already exist for:

| Schema | Purpose |
|--------|---------|
| `HealthResponse` | Standard service health response: `service`, `status` |
| `ErrorResponse` | Standard error envelope: `error`, `message`, optional `request_id` |

Search schemas:

| Schema | Purpose |
|--------|---------|
| `QueryLimitRequest` | Shared base request fields for query endpoints: non-empty `query`, optional `limit` from 1 through 100 defaulting to 10 |
| `SearchRequest` | Request body for `POST /search`: non-empty `query`, optional `limit` from 1 through 100 defaulting to 10 |
| `SearchResponse` | Search response containing ranked `results` |
| `RetrievalSourceScore` | Per-source retrieval provenance: `source`, `rank`, and optional raw `score` |
| `SearchResult` | Citation-ready chunk result with normalized fused score, retrieval provenance, text, document/version/chunk ids, source path, filename, page/heading metadata, and text offsets |

Document schemas:

| Schema | Purpose |
|--------|---------|
| `DocumentDeleteResponse` | Deletion summary for `DELETE /documents/{id}` with the document id, source path, deletion flag, source-file deletion status, and managed-copy paths removed |

Chat schemas:

| Schema | Purpose |
|--------|---------|
| `ChatRequest` | Request body for `POST /chat`, using the shared query and limit fields |
| `ChatResponse` | Stable chat response containing `answer`, `citations`, `refused`, and optional `refusal_reason`; validation enforces answered/refused state consistency |

Minimum planned API surface:

| Service | Endpoint | Purpose |
|---------|----------|---------|
| `api-service` | `POST /chat` | Chat with retrieved grounding context and answerability refusal |
| `api-service` | `POST /search` | Retrieve hybrid ranked results without generation |
| `api-service` | `POST /ingest` | Create an ingestion job |
| `api-service` | `GET /ingest/{job_id}` | Inspect ingestion job status |
| `api-service` | `GET /documents` | List ingested documents |
| `api-service` | `DELETE /documents/{id}` | Explicitly remove a document |
| `embedding-service` | `POST /embed` | Embed a single query |
| `embedding-service` | `POST /embed/batch` | Embed document chunks in batches |
| `embedding-service` | `GET /health` | Health check |
| `embedding-service` | `GET /model-info` | Current embedding model identity |

`DELETE /documents/{id}` requires bearer authentication. On first success it
returns `200` with `DocumentDeleteResponse` after removing Qdrant vectors, the
source file under `WATCH_ROOTS`, managed copies under `DOCUMENT_STORE_PATH`, and
PostgreSQL metadata. Unknown documents and repeated deletes return `404` with
`"Document not found"`.
