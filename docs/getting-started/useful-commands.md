# Useful Commands

## Documentation

```bash
make docs.serve.local
```

Serve the documentation at <http://localhost:8001>.

```bash
make docs.build
```

Build the static site into `site/`.

## Development Checks

```bash
make lint
```

Run Ruff linting and formatting checks.

```bash
make lint.fix
```

Apply Ruff autofixes and formatting.

```bash
make typecheck
```

Run mypy over service and test packages.

```bash
make test.unit
```

Run local unit tests.

```bash
make test.integration
```

Run Docker Compose integration tests. These verify service boundaries and real
storage dependencies, such as PostgreSQL, Qdrant, health endpoints, ingestion,
and retrieval. They do not call an external LLM provider.

```bash
make test.e2e
```

Run the provider-backed end-to-end RAG test. This exercises the full path from a
watched document, through ingestion, embedding, vector indexing, search, and
chat generation. The current E2E Compose stack uses Google AI Studio and
requires `GEMINI_API_KEY_E2E_TEST`. It configures
`EMBEDDING_MODEL_NAME=gemini-embedding-2` for the embedding service.

In GitHub Actions, this runs automatically as the final CI job after non-secret
checks pass. It requires `GEMINI_API_KEY_E2E_TEST` as a repository secret. Fork
PRs are not supported for provider-backed E2E because GitHub withholds repository
secrets from untrusted forks, so the E2E job will fail if a fork PR is opened.

```bash
make test.smoke
```

Run smoke tests. These are lightweight repository-level checks for broad
breakage, currently including the strict docs build.

## Pre-Commit

```bash
make pre-commit.install
```

Install pre-commit hooks.

```bash
make pre-commit.run
```

Run hooks against all files. Hooks fail if Ruff or mypy finds issues; they do not apply fixes.

## Database Migrations

```bash
make db.revision MESSAGE="create documents"
```

Create a new Alembic migration.

```bash
make db.upgrade
```

Apply migrations.

```bash
make db.downgrade
```

Roll back one migration.

These commands use `POSTGRES_URL` from the environment. Docker Compose development uses
the safe local defaults in `config/env/`.

## Planned Environment Variables

The implementation uses these configuration keys through service-specific files in `config/env/`:

```text
POSTGRES_URL
QDRANT_URL
EMBEDDING_SERVICE_URL
EMBEDDING_BACKEND
EMBEDDING_ENDPOINT_URL
EMBEDDING_MODEL_NAME
EMBEDDING_DIMENSION
LLM_PROVIDER
LLM_CHAT_COMPLETIONS_URL
LLM_MODEL
WATCH_ROOTS
DOCUMENT_STORE_PATH
RAG_API_KEY
```

These are defined in [ADR 008](../adr/008-job-coordination-and-service-contracts.md)
and [ADR 009](../adr/009-provider-configurable-model-services.md).
