# ADR-007: Retrieval and Answerability

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-007                                    |
| Title        | Retrieval and Answerability                |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-000, ADR-002, ADR-004, ADR-005, ADR-006 |

---

## Context

ADR-000 states that no answer is preferred over a wrong answer. Retrieval therefore needs to support both semantic matching and exact-term matching, and generation must not proceed as if weak retrieval is sufficient evidence.

Personal corpora often include names, acronyms, filenames, dates, quoted phrases, and technical terms. Dense vector retrieval alone can miss these exact-match cases.

---

## Decision

The first implementation will use **hybrid retrieval**:

- Dense vector retrieval through Qdrant.
- Sparse/full-text retrieval through PostgreSQL full-text search or another self-hosted sparse index if PostgreSQL FTS proves inadequate.
- Result merging via reciprocal rank fusion or a similarly simple deterministic rank-fusion strategy.

Generation must use retrieved chunks as grounding context and return citations. Citations should include:

- `document_id`
- `document_version_id`
- `chunk_id`
- source path
- page number or heading path where available

The system will implement configurable answerability gates before generation. Initial gates should include:

- Minimum top-result relevance threshold.
- Minimum number of usable retrieved chunks.
- Refusal when retrieval is insufficient.

Threshold values may be tuned after benchmarking, but the refusal mechanism must exist from the first implementation.

---

## Rationale

Hybrid retrieval improves recall for both semantic and exact-match queries. It is particularly useful for personal knowledge bases where the owner may remember a specific phrase, symbol, filename, or acronym.

Answerability gates operationalize the system's preference for refusing weakly grounded answers. Prompt instructions alone are not enough, especially with small local models.

---

## Implications

- PostgreSQL schema should support full-text indexing of chunk text or a separate sparse index must be introduced.
- Retrieval results must carry scores and provenance from both dense and sparse retrieval.
- The retrieval service/module must expose enough scoring information for answerability checks.
- Prompt construction must include citations and retrieved chunk boundaries.
- Evaluation should measure false confident answers, not only retrieval recall.

---

## Alternatives Considered

### Dense-only retrieval

Rejected as the default. It is simpler, but weaker for exact terms, filenames, acronyms, and quoted phrases.

### LLM-based reranking before generation

Deferred. It adds latency and another model call on the interactive path. Lightweight reranking can be revisited after baseline evaluation.

---

## Review Triggers

This ADR should be revisited if PostgreSQL full-text search is inadequate, if hybrid retrieval latency is too high, or if evaluation shows dense-only retrieval would be sufficient.
