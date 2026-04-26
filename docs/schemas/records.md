# Event and Record Schemas

The first persistent record schemas are implemented in PostgreSQL through Alembic.

The shared API convention schemas remain in `shared.schemas`; durable metadata records are
defined in `shared.db` and accessed through `shared.repository.MetadataRepository`.

## Persistent Records

| Record | Purpose |
|--------|---------|
| `documents` | Stable logical document identity, source path, original filename, active version pointer, lifecycle state |
| `document_versions` | Immutable indexed content version, raw-byte content hash, managed copy path, model/chunking metadata, lifecycle state |
| `chunks` | Chunk text and citation metadata tied to one document version |
| `ingestion_jobs` | Persisted async ingestion work, status, worker lease, progress, and error details |

Each chunk record must preserve enough provenance for citations:

- `document_id`
- `document_version_id`
- `chunk_id`
- source path
- original filename
- page number or heading path where available
- offsets where practical

## Lifecycle States

The initial persisted lifecycle states are:

- `pending`
- `running`
- `copied`
- `parsed`
- `chunked`
- `embedded`
- `indexed`
- `active`
- `failed`
- `deleting`
- `deleted`

These states are validated by database constraints and by the shared repository layer.

## Job Coordination

Workers claim pending jobs through PostgreSQL row locking with `FOR UPDATE SKIP LOCKED`.
This keeps the first implementation queue-free while allowing multiple workers to run
without claiming the same job.
