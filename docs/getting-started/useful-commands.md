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

Run Docker Compose integration tests.

```bash
make test.smoke
```

Run smoke tests, including strict docs build.

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

## Planned Environment Variables

The implementation uses these configuration keys through service-specific files in `config/env/`:

```text
POSTGRES_URL
QDRANT_URL
EMBEDDING_SERVICE_URL
OLLAMA_URL
WATCH_ROOTS
DOCUMENT_STORE_PATH
RAG_API_KEY
```

These are defined in [ADR 008](../adr/008-job-coordination-and-service-contracts.md).
