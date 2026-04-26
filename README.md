# Personal RAG System

Architecture-first personal Retrieval-Augmented Generation system for a single-user, self-hosted knowledge base.

The project is currently in the design/scaffolding phase. The documentation site captures the architecture decisions, service boundaries, and implementation plan.

## Documentation

Install documentation dependencies:

```bash
python -m pip install -r docs/docs-requirements.txt
```

Serve the project page locally:

```bash
make docs.serve.local
```

The local site is served at <http://localhost:8001>.

## Current Architecture Direction

- Dockerized services.
- Watch directories are the authoritative corpus source.
- PostgreSQL metadata store on NAS.
- Qdrant vector store as an independent Docker service, defaulting to NAS placement.
- `api-service` and `ingestion-worker` split from the start.
- Dedicated `embedding-service`, co-located with Ollama/Gemma on the Mac M2 model host by default.
- Hybrid dense + sparse retrieval.
- Immutable document versions and explicit ingestion state.
