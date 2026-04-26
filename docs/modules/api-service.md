# API Service

The `api-service` is the public application boundary.

Responsibilities:

- API key authentication.
- Chat and search endpoints.
- Document listing and deletion endpoints.
- Ingestion job creation and status endpoints.
- Retrieval orchestration.
- Answerability checks.
- Streaming generation through Ollama.

Retrieval and generation remain internal modules inside the API service for the first implementation. They should still be written behind clean interfaces so they can be extracted later if needed.

Related decisions:

- [ADR 003: Service Boundaries](../adr/003-service-boundaries.md)
- [ADR 007: Retrieval and Answerability](../adr/007-retrieval-and-answerability.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)
