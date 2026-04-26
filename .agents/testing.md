# Testing Rules

Each module owns its tests under `<module>/tests/`.

Current layout:

- `api_service/tests/`
- `embedding_service/tests/`
- `ingestion_worker/tests/`
- `shared/tests/`
- `tests/smoke/` for repository-level smoke checks.

Each module may expose test helpers under `<module>/testing/`. Other modules should import those helpers instead of importing another module's test files.

Use:

- Unit tests for pure logic and route contracts.
- Integration tests for service boundaries, storage, and Compose wiring.
- Smoke tests for docs/build/startup checks.

Verification commands:

- `make lint`
- `make typecheck`
- `make test.unit`
- `make test.integration` when service boundaries or Compose behavior changes.
- `make test.smoke` when docs, config, or build behavior changes.
- `make test` for the full suite.

The expected development environment is the devcontainer.
