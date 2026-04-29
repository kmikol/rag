# Testing Rules

Each module owns its tests under `<module>/tests/`.

Current layout:

- `api_service/tests/`
- `embedding_service/tests/`
- `ingestion_worker/tests/`
- `shared/tests/`
- `tests/smoke/` for repository-level smoke checks.
- `tests/e2e/` for full pipeline tests that exercise the application through
  production-like service boundaries.

Each module may expose test helpers under `<module>/testing/`. Other modules should import those helpers instead of importing another module's test files.

Use:

- Unit tests for pure logic and route contracts.
- Integration tests for service boundaries, storage, and Compose wiring without
  requiring an external model provider.
- End-to-end tests for complete user-visible RAG flows across ingestion,
  embedding, indexing, retrieval, answerability, and generation.
- Smoke tests for lightweight docs/build/startup checks.

Verification commands:

- `make lint`
- `make typecheck`
- `make test.unit`
- `make test.integration` when service boundaries or Compose behavior changes.
- `make test.e2e` when validating the full RAG flow against the configured
  provider-backed E2E stack.
- `make test.smoke` when docs, config, or build behavior changes.
- `make test` for the full suite.

Provider-backed E2E runs automatically in CI after non-secret checks pass. It
requires the provider secret in the repository. Fork PRs are not supported for
provider-backed E2E because repository secrets are not exposed to untrusted forks.

The expected development environment is the devcontainer.
