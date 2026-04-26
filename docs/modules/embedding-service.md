# Embedding Service

The `embedding-service` is a dedicated Docker service for embeddings.

Responsibilities:

- Own embedding model selection and runtime configuration.
- Expose single-query embedding for chat/search.
- Expose batch embedding for ingestion.
- Expose health and model-info endpoints.
- Keep query and document embeddings consistent for each Qdrant collection.

The exact embedding model is intentionally deferred until the system has a working corpus and benchmark baseline.

Related decision:

- [ADR 004: Embedding Service](../adr/004-embedding-service.md)
