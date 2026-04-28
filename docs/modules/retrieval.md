# Retrieval

Retrieval is implemented inside `api-service`.

Responsibilities:

- Embed user queries through `embedding-service`.
- Retrieve dense candidates through the shared Qdrant vector-index client.
- Load active chunk metadata from PostgreSQL.
- Return citations with document, version, chunk, and source metadata.

The current `POST /search` implementation is dense-only. Sparse/exact-match
retrieval remains a follow-up because the current PostgreSQL schema does not yet
include full-text search support. When sparse retrieval is added, results should
be merged with dense candidates through a simple deterministic rank-fusion
strategy.

Answerability gates are planned for `POST /chat`, which will build on this
retrieval path before generation.

Related decisions:

- [ADR 006: Chunking Strategy](../adr/006-chunking-strategy.md)
- [ADR 007: Retrieval and Answerability](../adr/007-retrieval-and-answerability.md)
