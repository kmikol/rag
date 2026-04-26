# ADR-005: Document Identity and Ingestion State

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-005                                    |
| Title        | Document Identity and Ingestion State      |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-001, ADR-002, ADR-003                  |

---

## Context

Ingestion writes to multiple durable systems: PostgreSQL metadata, the managed document store, and Qdrant. A document update must not leave the corpus in a half-updated state where old chunks are partially removed, new chunks are partially written, or citations point at ambiguous content.

ADR-001 establishes that watch directories are authoritative. This ADR defines how source files map to logical documents, immutable indexed versions, chunks, and ingestion lifecycle state.

---

## Decision

The system will separate logical document identity from indexed content versions:

- `document_id` identifies a stable logical document.
- `document_version_id` identifies one immutable ingested content version.
- `source_path` records where the document came from under a configured watch root.
- `content_hash` records the SHA-256 hash of the raw source bytes.

When a source file is updated, the system creates a new `document_version_id`, processes it fully, writes its chunks and embeddings, then marks that version active. Old versions are retained at least until the new version is active, so failed re-ingestion does not remove the last usable version.

Only active document versions are queryable.

Ingestion will use an explicit state machine. Initial states are:

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

Some states may be internal only, but they must be persisted or derivable from persisted records so failed jobs can be inspected and retried.

---

## Rationale

Immutable versions make document updates safer. They avoid the delete-then-reingest gap where a failed update removes a document from retrieval entirely. They also make citations precise: an answer can cite the exact version of a document that supplied the chunk.

An explicit state machine makes multi-system writes easier to reason about. PostgreSQL can coordinate which version is active, while Qdrant and the managed document store can be reconciled against metadata state.

---

## Implications

- PostgreSQL schema must include logical documents, document versions, source paths, chunks, and ingestion jobs.
- Qdrant payloads must include `document_id`, `document_version_id`, and `chunk_id`.
- Citations must refer to document versions, not just source paths.
- Re-ingestion creates a new version and atomically switches the active version in PostgreSQL after indexing succeeds.
- Failed versions remain inspectable and retryable.
- Deletion removes or tombstones the logical document, all versions, all chunks, Qdrant vectors, and managed document copies.

---

## Alternatives Considered

### Overwrite document records in place

Rejected. This is simpler but makes failed re-ingestion risky and weakens citation auditability.

### Content hash as the only document identity

Rejected. Hashes identify byte-identical content, not logical documents. A file update should be related to the previous document even though its hash changes.

---

## Review Triggers

This ADR should be revisited if version retention becomes too costly or if a future UI needs richer document history controls.
