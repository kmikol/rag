# Project Facts

This is a personal, self-hosted Retrieval-Augmented Generation system.

Stable facts:

- The system is single-user and private.
- The project is docs-first and ADR-driven.
- Services are Dockerized and configured through environment variables.
- The expected development workflow is inside the devcontainer.
- Watch directories are the authoritative source of corpus membership.
- PostgreSQL stores metadata, jobs, chunks, and document lifecycle state.
- Qdrant stores vector embeddings.
- The managed document store keeps copied originals for reprocessing and auditability.
- Ollama hosts the generation model.
- `embedding-service` owns embedding model selection and exposes embedding APIs.
- No answer is preferred over a wrong answer.

Do not introduce features, deployment targets, or product scope not requested by the owner.
