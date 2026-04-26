# Architecture Rules

## Services

- `api_service`: external API boundary, auth, chat/search/document endpoints, retrieval orchestration, answerability checks, generation streaming.
- `ingestion_worker`: job-driven background processing, watch-root scans, parsing, chunking, embedding calls, indexing, reconciliation.
- `embedding_service`: single-query and batch embedding API, model identity, embedding dimensions.
- `shared`: config, logging, shared schemas, common errors, and cross-service utilities.

## Configuration

- All runtime settings must come from environment variables.
- Do not hardcode paths, credentials, hosts, ports, model names, or service URLs in implementation code.
- Service-specific defaults live in `config/env/*.env`.
- Secrets must not be committed. Use local overrides or deployment-specific env injection.

## Storage and Migrations

- Schema changes must use Alembic.
- Do not hand-edit production schema outside migrations.
- Persistent record design must follow the accepted ADRs unless the owner approves a superseding ADR.

## Service Contracts

- Public response and error conventions belong in `shared.schemas`.
- New service endpoints require tests and module README updates.
- New services require Dockerfile, env files, README, docs module page, Compose wiring, tests, and health checks.
