# ADR-003: Service Boundaries

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-003                                    |
| Title        | Service Boundaries                         |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Last Reviewed| 2026-05-15                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-000, ADR-001, ADR-002                  |

---

## Context

The system should be deployable as Kubernetes workloads (primary) and as Docker services for local development, while remaining movable between machines on the owner's Tailscale network. At the same time, this is a single-user personal system, so the first implementation should avoid unnecessary distributed-system complexity.

The main application responsibilities are:

- External API surface and authentication.
- Chat and search request handling.
- Retrieval orchestration.
- Generation orchestration and streaming.
- Ingestion job orchestration.
- Parsing, cleaning, chunking, embedding, and indexing documents.

Ingestion is long-running, potentially CPU/RAM-heavy, and operationally different from interactive chat/search requests. It is the most important workload to isolate from the API process.

---

## Decision

The first implementation will use a **hybrid service split**:

- `api-service`
  - Owns API key authentication.
  - Exposes chat, search, document, and ingestion-control endpoints.
  - Performs retrieval orchestration as an internal module.
  - Performs generation orchestration and streams responses from Ollama.
  - Writes and reads metadata from PostgreSQL.
  - Reads vectors from Qdrant.

- `ingestion-worker`
  - Runs on-demand and scheduled ingestion jobs.
  - Scans configured watch roots.
  - Computes hashes and reconciles additions, updates, and deletions.
  - Parses, cleans, chunks, embeds, and indexes documents.
  - Writes managed document copies, PostgreSQL metadata, and Qdrant vectors.

- `postgres`
  - Central metadata store, reachable from the cluster as decided in ADR-002.

- `qdrant`
  - Independent vector store service with durable storage as decided in ADR-002.

- `ollama`
  - Generation model server, running on the GPU-capable machine or another configured host.

Retrieval and generation will remain inside `api-service` for the initial implementation. They must still be implemented as clear internal modules so they can be extracted into separate services later if needed.

---

## Rationale

This split isolates the highest-risk background workload without forcing every internal function behind a network boundary on day one. Ingestion can be scheduled, moved, restarted, and resource-limited independently from the API service. Interactive chat/search latency is protected from long document processing runs.

Keeping retrieval and generation orchestration inside the API service initially simplifies streaming, avoids extra inter-service calls on the critical user-facing path, and reduces the number of service contracts that must be designed before the first working version.

The codebase should still preserve clear module boundaries so a future architecture can split out `retrieval-service` or `generation-service` without rewriting business logic. Embedding is already split into its own service by ADR-004.

---

## Implications

- API and ingestion worker must be separate deployable workloads (separate images/commands).
- Both services need access to PostgreSQL and Qdrant configuration.
- The ingestion worker needs access to configured watch roots and the managed document store.
- The API service should not perform heavy ingestion work directly; `POST /ingest` should create or request a job for the worker to execute.
- A job coordination mechanism is required. PostgreSQL-backed job records are sufficient for this iteration.
- Retrieval and generation code should live behind internal interfaces rather than being embedded directly in route handlers.
- Streaming responses remain simpler because API-to-Ollama streaming is direct.

---

## Alternatives Considered

### Single modular API container

Rejected for the first implementation. It would be simpler to build, but ingestion could interfere with interactive API latency and the deployment would be less aligned with the project's Docker-service architecture goals.

### Fully split API, ingestion, retrieval, and generation services

Deferred. This would provide the cleanest microservice separation, but it adds more network contracts, more configuration, and more streaming complexity before the system has proven its core behavior. Retrieval and generation can be extracted later if load, placement, or maintainability justify it.

---

## Review Triggers

This ADR should be revisited if any of the following occur:

- Retrieval becomes resource-heavy enough to move near Qdrant or an embedding model.
- Generation orchestration needs to support multiple model backends or richer routing.
- Ingestion jobs require a stronger queue than PostgreSQL-backed job records.
- Chat/search latency is affected by retrieval or generation work inside the API process.
