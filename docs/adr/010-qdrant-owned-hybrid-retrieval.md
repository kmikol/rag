# ADR-010: Qdrant-Owned Hybrid Retrieval

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-010                                    |
| Title        | Qdrant-Owned Hybrid Retrieval              |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2026-04-30                                 |
| Supersedes   | -                                          |
| Depends on   | ADR-002, ADR-007                           |

---

## Context

ADR-007 requires hybrid retrieval so exact terms, filenames, acronyms, names,
dates, and quoted phrases are not missed by dense vector retrieval alone. It
allowed PostgreSQL full-text search or another self-hosted sparse index if that
proved preferable.

The owner prefers search and matching behavior to live in one retrieval backend
instead of being split between PostgreSQL and Qdrant. Qdrant supports dense
vectors, sparse vectors, payload text indexes, and deterministic candidate
fusion at the application boundary.

---

## Decision

Hybrid retrieval will be implemented with Qdrant as the only search backend:

- Dense vector retrieval uses the embedding-service vector stored as Qdrant
  named vector `dense`.
- Lexical sparse retrieval uses a deterministic local tokenizer and hashed term
  sparse vector stored as Qdrant named vector `sparse` with Qdrant IDF scoring.
- Full-text matching uses a Qdrant text payload index over chunk text as a
  filter on sparse-ranked candidates.
- PostgreSQL remains the source of truth for metadata, document lifecycle state,
  and citation hydration, but it will not provide sparse retrieval.

Existing Qdrant collections using the old unnamed dense-vector shape are
incompatible and must be recreated and reingested. The application must fail
fast with a clear error rather than deleting or rewriting existing collections.

---

## Rationale

Keeping retrieval matching inside Qdrant makes the retrieval path easier to
reason about: one backend owns dense, sparse, and text candidate generation.
PostgreSQL remains focused on transactional metadata and active-version state.

The local lexical sparse vectorizer avoids model downloads, extra services, and
provider-specific sparse embedding behavior while satisfying the exact-term
retrieval goal.

---

## Implications

- Qdrant collection setup now requires named dense and sparse vectors plus a
  text payload index.
- Reingestion is required after recreating an incompatible old collection.
- Retrieval results should expose component provenance so answerability and
  debugging can see which retrieval sources contributed.
- PostgreSQL FTS migrations should not be added for the baseline hybrid
  retrieval implementation.

---

## Alternatives Considered

### PostgreSQL full-text search

Rejected for this implementation. PostgreSQL FTS is mature and simpler for
metadata-adjacent lexical search, but it splits retrieval matching across two
systems.

### Sparse embedding model

Deferred. SPLADE, miniCOIL, or similar sparse models may improve retrieval
quality, but they add model dependency, storage, download, and configuration
complexity before the baseline hybrid path has real corpus evaluation.

---

## Review Triggers

Revisit this decision if Qdrant sparse or text matching is inadequate on the
owner's corpus, if collection recreation becomes operationally painful, or if
evaluation shows a model-backed sparse encoder is needed.
