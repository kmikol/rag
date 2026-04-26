# ADR-006: Chunking Strategy

| Field        | Value                                      |
|--------------|--------------------------------------------|
| ID           | ADR-006                                    |
| Title        | Chunking Strategy                          |
| Status       | Accepted                                   |
| Deciders     | System owner                               |
| Date         | 2025-04-24                                 |
| Supersedes   | —                                          |
| Depends on   | ADR-001, ADR-004, ADR-005                  |

---

## Context

Chunking determines retrieval quality, citation usefulness, prompt size, and reprocessing behavior. The system initially supports Markdown and PDF documents, with future parser extensions expected.

---

## Decision

The first implementation will use structure-aware chunking:

- Markdown documents are chunked using heading hierarchy where possible.
- PDF documents are chunked using page and paragraph boundaries where possible.
- Target chunk size is roughly 300-600 tokens.
- Overlap is roughly 50-100 tokens.
- Semantic chunking is out of scope for the first implementation.

Each chunk must preserve citation metadata where available:

- `document_id`
- `document_version_id`
- `chunk_id`
- source path
- original filename
- page number for PDFs
- heading path for Markdown
- section title where available
- character or token offsets where practical

---

## Rationale

Structure-aware chunking gives better retrieval and citations than naive fixed-size splitting while remaining understandable and debuggable. Semantic chunking may improve some cases, but it adds model dependency and implementation complexity before the baseline system exists.

The chosen size range is small enough to fit several chunks into prompts for a slow local model, but large enough to preserve useful context.

---

## Implications

- Parsers must emit enough structural information for the chunker to use headings, pages, and paragraphs.
- Chunk records in PostgreSQL must include citation metadata.
- Chunking configuration must be persisted with document versions so old results can be interpreted after strategy changes.
- Changing chunking strategy requires reprocessing and re-indexing affected documents.

---

## Alternatives Considered

### Fixed-size chunking only

Rejected as the default. It is simple, but it often creates poor citations and splits sections awkwardly.

### Semantic chunking

Deferred. It can be revisited after the system has real corpus data and baseline retrieval benchmarks.

---

## Review Triggers

This ADR should be revisited after retrieval evaluation on the owner's real corpus, or if documents with unusual structure become common.
