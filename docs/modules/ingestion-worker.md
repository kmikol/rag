# Ingestion Worker

The `ingestion-worker` owns background document processing.

Responsibilities:

- Claim PostgreSQL-backed ingestion jobs.
- Scan configured watch roots.
- Confirm watch-root health before deletion reconciliation.
- Detect new, changed, duplicate, and removed files.
- Parse PDF and Markdown documents.
- Chunk documents using the v1 chunking strategy.
- Request batch embeddings from `embedding-service`.
- Write metadata to PostgreSQL.
- Write vectors to Qdrant.
- Copy originals to the managed document store.

Related decisions:

- [ADR 001: Data Sources and Ingestion](../adr/001-data-sources-and-ingestion.md)
- [ADR 005: Document Identity and Ingestion State](../adr/005-document-identity-and-ingestion-state.md)
- [ADR 006: Chunking Strategy](../adr/006-chunking-strategy.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)
