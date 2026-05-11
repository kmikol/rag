# Personal RAG System

Architecture-first personal Retrieval-Augmented Generation system for a single-user, self-hosted knowledge base.

The project is currently in the design/scaffolding phase. The documentation site captures the architecture decisions, service boundaries, and implementation plan.

## Documentation

This project is intended to be developed from inside the devcontainer. Open the repository in VS Code and choose **Reopen in Container**. The container installs the development, test, and documentation dependencies from `requirements.txt`.

Serve the project page locally from inside the devcontainer:

```bash
make docs.serve.local
```

The local site is served at <http://localhost:8001>.

## Development Checks

Run the standard checks from inside the devcontainer:

```bash
make lint
make typecheck
make test.unit
make test.integration
make test.smoke
```

`make test` runs all of the above.

Install pre-commit hooks from inside the devcontainer:

```bash
make pre-commit.install
```

## Environment

Configuration is environment-variable driven. Safe service-specific defaults are committed under `config/env/*.env`, and matching `*.env.example` files document the same keys for new environments.

Do not put personal secrets in the committed env defaults; override values in your shell, Compose environment, ignored `.env.local`, or deployment-specific env files.

## Current Architecture Direction

- Dockerized services.
- Watch directories are the authoritative corpus source.
- PostgreSQL metadata store on NAS.
- Qdrant vector store as an independent Docker service, defaulting to NAS placement.
- `api-service` and `ingestion-worker` split from the start.
- Dedicated `embedding-service`, co-located with Ollama/Gemma on the Mac M2 model host by default.
- Hybrid dense + sparse retrieval.
- Immutable document versions and explicit ingestion state.

## Container Images

Deployable services are published to GitHub Container Registry (GHCR):

- `ghcr.io/<owner>/rag-api-service`
- `ghcr.io/<owner>/rag-ingestion-worker`
- `ghcr.io/<owner>/rag-embedding-service`

Image tags are intended for deployments, but tags can be moved if republished; pin by digest when you need an immutable reference:

- `sha-<full_commit_sha>` for every published build, for traceability to a specific source commit.
- Manually selected release version tags (for example: `0.0.1`) via Git tag (`v0.0.1`) or manual workflow dispatch input.

Avoid using `latest` for cluster deployments.
