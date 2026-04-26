# ADR-008: Job Coordination and Service Contracts

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-008                                    |
| Title        | Job Coordination and Service Contracts     |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-002, ADR-003, ADR-004, ADR-005         |

---

## Context

ADR-003 splits the first implementation into an `api-service` and an `ingestion-worker`. These services need a coordination mechanism for asynchronous ingestion jobs, but the system does not need a full external queue for single-user volume.

The first implementation also needs minimal service contracts before coding begins.

---

## Decision

Ingestion jobs will be coordinated through PostgreSQL-backed job records.

Workers claim jobs using transactional row locking, such as `SELECT ... FOR UPDATE SKIP LOCKED`, so multiple workers can eventually run without processing the same job twice.

No Redis, Celery, or external message queue will be introduced in the first implementation.

Minimum API contracts:

`api-service`:

- `POST /chat`
- `POST /search`
- `POST /ingest`
- `GET /ingest/{job_id}`
- `GET /documents`
- `DELETE /documents/{id}`

`embedding-service`:

- `POST /embed`
- `POST /embed/batch`
- `GET /health`
- `GET /model-info`

Core configuration will use environment variables:

- `POSTGRES_URL`
- `QDRANT_URL`
- `EMBEDDING_SERVICE_URL`
- `OLLAMA_URL`
- `WATCH_ROOTS`
- `DOCUMENT_STORE_PATH`
- `RAG_API_KEY`

Internal service traffic will use HTTP over the private Tailscale/LAN boundary for the first implementation. The public API surface remains protected by the bearer token described in ADR-000. Public internet exposure and TLS termination are out of scope for the first implementation.

---

## Rationale

PostgreSQL is already required and provides sufficient coordination primitives for the expected workload. Avoiding an external queue reduces operational overhead while still allowing safe job claiming and retries.

Defining minimal contracts now keeps service boundaries clear without over-designing APIs before implementation.

---

## Implications

- Job records must include state, timestamps, ownership/lease information, progress counters, and error details.
- The ingestion worker must be idempotent enough to retry failed or abandoned jobs safely.
- API handlers should create jobs and return quickly rather than running ingestion inline.
- Services must be configured entirely by environment so containers can move between machines.
- HTTP timeouts and health checks are required for calls to embedding and Ollama services.

---

## Alternatives Considered

### Redis/Celery queue

Deferred. Useful if ingestion volume grows or scheduling becomes more complex, but unnecessary for the initial single-user system.

### In-memory job queue

Rejected. It would lose job state across restarts and would not coordinate multiple worker containers.

### HTTPS for all internal service traffic

Deferred. The system is private behind Tailscale and bearer-token protected at the API layer. TLS/reverse proxy details can be added later if deployment requirements change.

---

## Review Triggers

This ADR should be revisited if job volume grows, multiple workers become common, public exposure is introduced, or internal network trust assumptions change.
