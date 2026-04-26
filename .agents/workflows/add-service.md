# Workflow: Add Service

A new service requires:

- Package directory.
- Dockerfile.
- `README.md` with purpose and API/callable contract.
- `docs/modules/` page that includes the README.
- Service-specific env file and example under `config/env/`.
- Compose wiring.
- Test Compose wiring if relevant.
- Health endpoint.
- Module-owned tests under `<module>/tests/`.
- Test helpers under `<module>/testing/` when other modules need mocks.
- MkDocs nav update.
