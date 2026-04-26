# Schemas

Schema documentation will be generated as the API and database models are implemented.

The architecture already requires schema coverage for:

- Documents and document versions.
- Source paths and content hashes.
- Chunks and citation metadata.
- Ingestion jobs and lifecycle state.
- Chat/search request and response payloads.
- Embedding service request and response payloads.

See [ADR 005](../adr/005-document-identity-and-ingestion-state.md) and [ADR 008](../adr/008-job-coordination-and-service-contracts.md).
