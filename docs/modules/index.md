# Modules

The project will be implemented as Dockerized services with clear internal modules.

## Planned Services

| Module | Responsibility |
|--------|----------------|
| [API Service](api-service.md) | Auth, chat/search/document APIs, retrieval orchestration, generation streaming |
| [Ingestion Worker](ingestion-worker.md) | Watch-root scanning, reconciliation, parsing, chunking, indexing |
| [Embedding Service](embedding-service.md) | Single-query and batch embeddings |
| [Retrieval](retrieval.md) | Hybrid dense + sparse retrieval and answerability gates |
| [Storage](storage.md) | PostgreSQL metadata, Qdrant vectors, managed document copies |

Each implementation module owns its own tests under `<module>/tests/` and exposes test helpers under `<module>/testing/` for other modules to import.
