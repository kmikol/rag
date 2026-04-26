# ADR-002: Storage and Metadata Topology

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-002                                    |
| Title        | Storage and Metadata Topology              |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-000, ADR-001                           |

---

## Context

The system is intended to run as a collection of small services packaged as Docker containers. Components may be moved between machines on the owner's Tailscale network. The data layer therefore needs to be central enough that services can be relocated without moving the corpus, while still remaining simple enough for a single-user self-hosted deployment.

The system needs persistent storage for:

- Document metadata, source paths, content hashes, and lifecycle state.
- Chunk metadata and document-to-chunk mappings.
- Ingestion job status and error records.
- Managed copies of source documents.
- Vector embeddings and vector search indexes.

ADR-001 establishes that configured watch directories are the authoritative source of corpus membership. The managed document store preserves indexed originals for reprocessing and auditability, but does not define whether a document belongs in the corpus.

---

## Decision

The system will use **PostgreSQL as the central metadata store**, served from the Synology NAS as a Docker-managed service.

PostgreSQL will store document metadata, source path records, SHA-256 content hashes, document lifecycle state, chunk metadata, ingestion job records, and any other relational state required by the ingestion and retrieval pipelines.

The managed document store will live on NAS-backed storage and contain copied source files addressed by stable internal IDs.

The vector store will be packaged as an independent Docker service, currently expected to be **Qdrant**. The reference deployment will run Qdrant on the Synology NAS alongside PostgreSQL and the managed document store. Qdrant's location must be configured by service URL rather than assumed by the application, so it can be moved to a compute machine later if NAS RAM, disk latency, or query performance become limiting.

Services must connect to PostgreSQL over the private Tailscale/network boundary using configured connection strings and credentials. Services must not share a SQLite database file over a network filesystem.

---

## Rationale

The architecture is expected to support independently deployable containers. A shared SQLite file on NAS storage would be operationally simple, but it is a poor fit for multi-service access across network filesystems because SQLite relies on filesystem locking semantics that can be fragile over SMB/NFS-style mounts.

PostgreSQL provides proper concurrent access, transactional guarantees, mature backup tooling, and a clean central coordination point for services that may run on different machines. It is heavier than SQLite, but the operational cost is acceptable because the NAS is already intended to host central infrastructure.

This also improves the portfolio value of the project: the architecture demonstrates a realistic service-oriented storage boundary rather than relying on a shared database file.

---

## Implications

- A PostgreSQL container/service must be part of the deployment stack.
- A Qdrant container/service must be part of the deployment stack.
- Database schema migrations are required.
- Service configuration must include PostgreSQL host, port, database, username, password, and TLS/connection settings as needed.
- Service configuration must include the Qdrant endpoint. The application must not assume Qdrant is co-located with PostgreSQL or the API service.
- Ingestion job state should be persisted in PostgreSQL rather than in memory.
- Metadata writes that coordinate document state, chunk records, and ingestion status should use database transactions.
- Backups must include PostgreSQL dumps or volume snapshots, the managed document store, and the vector store.
- The application should use connection pooling appropriate for a small self-hosted deployment.
- The metadata schema should avoid embedding deployment-specific local paths as the only identity for a document; source path, content hash, and internal document ID must be stored separately.

---

## Alternatives Considered

### SQLite file on NAS

Rejected. It is simple to deploy and easy to inspect, but sharing a SQLite database file across network-mounted storage is brittle. Locking behavior and interrupted mounts could corrupt or stall the metadata layer, especially once multiple containers or machines interact with it.

### SQLite local to a dedicated metadata service

Considered viable but not selected. This would keep SQLite on local disk and expose metadata through a service API, avoiding network-filesystem locking problems. It is lighter than PostgreSQL, but it creates a custom metadata service boundary that PostgreSQL already solves more generally.

### PostgreSQL on the main compute machine

Deferred. Running PostgreSQL on the main machine would reduce NAS dependency and may improve latency, but it conflicts with the goal of keeping the datastore central and independent of where compute services are deployed. This can be revisited if NAS performance or reliability is inadequate.

### Qdrant on the main compute machine by default

Deferred. Running Qdrant close to the retrieval and embedding services may improve latency and indexing performance, especially if the compute machine has faster SSD storage or more RAM than the NAS. The initial deployment will still default to the NAS because the project favours central datastore services and movable compute containers. Qdrant remains an independent Docker service addressed by configuration, so moving it later does not require application architecture changes.

---

## Review Triggers

This ADR should be revisited if any of the following occur:

- The NAS proves too slow or unreliable for PostgreSQL.
- The NAS proves too slow or memory-constrained for Qdrant.
- The system is simplified back into a single-process deployment.
- Multiple users or public access are introduced.
- Backup and recovery requirements become stricter.
