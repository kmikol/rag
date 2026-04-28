# Retrieval

Retrieval is initially implemented inside `api-service`.

Responsibilities:

- Embed user queries through `embedding-service`.
- Retrieve dense candidates through the shared Qdrant vector-index client.
- Retrieve sparse/exact-match candidates through PostgreSQL FTS or another self-hosted sparse index.
- Merge candidates with a deterministic rank-fusion strategy.
- Apply answerability gates before generation.
- Return citations with document, version, chunk, and source metadata.

Related decisions:

- [ADR 006: Chunking Strategy](../adr/006-chunking-strategy.md)
- [ADR 007: Retrieval and Answerability](../adr/007-retrieval-and-answerability.md)
