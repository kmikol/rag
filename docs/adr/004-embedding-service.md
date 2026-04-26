# ADR-004: Embedding Service

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-004                                    |
| Title        | Embedding Service                          |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-000, ADR-002, ADR-003                  |

---

## Context

Both ingestion and retrieval require embeddings:

- During ingestion, document chunks are embedded before being written to the vector store.
- During query handling, user queries are embedded before retrieval.

The system is expected to run as Docker services that can move between machines on the private Tailscale network. Embedding model choice, version, and deployment location should therefore be centralized rather than duplicated across multiple services.

---

## Decision

The system will include a dedicated **`embedding-service`** Docker service.

Both `api-service` and `ingestion-worker` will call `embedding-service` over an internal HTTP API:

- `api-service` uses it for low-latency query embeddings.
- `ingestion-worker` uses it for batch document chunk embeddings.

The embedding model, model version, runtime device, and batching parameters are owned by `embedding-service` configuration. Other services must treat embeddings as a remote capability addressed by service URL, not as an in-process library.

The same embedding model must be used for query embeddings and document chunk embeddings for a given Qdrant collection/index.

The reference deployment will run `embedding-service` on the same Mac M2 16GB machine that hosts Ollama/Gemma generation. This is expected to fit for a small dedicated embedding model plus a small local generation model, while keeping both model-serving workloads close to the main compute path. The placement is not architectural: `embedding-service` must be addressed by configurable URL so it can be moved to another machine if memory pressure, model reloads, or latency become a problem.

---

## Rationale

A dedicated embedding service keeps the embedding model and version canonical. It avoids loading the same model independently in both the API and ingestion worker, reduces the risk of model drift, and allows the embedding workload to move to whichever machine has the best CPU/GPU/RAM characteristics.

This service boundary fits the project's Docker-first architecture. It also makes future changes easier: the model can be replaced, optimized, or accelerated inside one service without changing API or ingestion business logic.

The trade-off is one extra network call in the query path. For a single-user system on a private network, this cost is acceptable, and it is likely to be small compared with local LLM generation latency.

Co-locating embedding and generation on the Mac M2 keeps model-serving operationally simple for the initial deployment. If unified memory pressure causes Ollama to unload/reload models too often, or if ingestion batch embedding interferes with chat generation, the embedding service can be moved without changing API or ingestion architecture.

---

## Implications

- `embedding-service` must be part of the deployment stack.
- `api-service` and `ingestion-worker` must be configured with the embedding service URL.
- The embedding API must support single-query embedding and batch embedding.
- The service should expose health and model-info endpoints so other services can verify availability and expected model identity.
- The embedding model name/version and output dimensionality must be recorded in metadata for each vector collection or document version.
- Changing the embedding model requires creating a new vector collection or fully re-embedding the corpus.
- Ingestion should batch chunk embedding requests for throughput.
- Query embedding requests should have strict timeouts because they are on the interactive path.
- The reference deployment should monitor memory pressure and model reload latency on the shared model-serving machine.
- The embedding service placement must remain configurable and must not be hardcoded to the Ollama host.

---

## Alternatives Considered

### In-process embeddings in each service

Rejected. This would be simpler at first, but it duplicates model memory, makes model/version drift easier, and makes it harder to move embedding work independently.

### Start in-process and extract later

Rejected for the initial architecture. Although this would reduce the number of services at the beginning, embedding is a natural shared capability between ingestion and retrieval. Defining it as a service now is cleaner and better aligned with the deployment goals.

### External cloud embedding API

Deferred. A cloud API could offer strong embedding quality and avoid local model hosting, but it adds recurring cost, network dependency, and data-sovereignty concerns. The current system is intended to be self-hosted.

### Embedding service on NAS

Deferred. Running embeddings on the NAS would keep more services central, but embedding is a compute workload and may compete with PostgreSQL and Qdrant for NAS resources. The NAS remains the default host for durable data services, not model serving.

### Embedding service on a separate compute machine

Deferred. This may become useful if the Mac M2 experiences memory pressure while serving both generation and embedding models. The service URL boundary allows this move without application architecture changes.

---

## Review Triggers

This ADR should be revisited if any of the following occur:

- Query embedding latency becomes a noticeable part of chat/search response time.
- The embedding service becomes a reliability bottleneck.
- Co-locating embedding and generation causes memory pressure or model reload thrashing.
- A future retrieval architecture requires multiple embedding models or collections.
- The system adopts a cloud embedding provider.
