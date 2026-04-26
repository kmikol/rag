# Storage

Storage is split across central durable services.

| Component | Default placement | Purpose |
|-----------|-------------------|---------|
| PostgreSQL | NAS | Metadata, source paths, document versions, chunks, jobs |
| Qdrant | NAS, movable by URL | Dense vector index |
| Managed document store | NAS | Copied originals for reprocessing and auditability |
| Watch roots | Configured filesystem paths | Authoritative corpus source |

Related decisions:

- [ADR 001: Data Sources and Ingestion](../adr/001-data-sources-and-ingestion.md)
- [ADR 002: Storage and Metadata Topology](../adr/002-storage-and-metadata-topology.md)
