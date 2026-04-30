# Retrieval

Retrieval is implemented inside `api-service`.

Responsibilities:

- Embed user queries through `embedding-service`.
- Retrieve dense, sparse, and text-match candidates through the shared Qdrant
  vector-index client.
- Load active chunk metadata from PostgreSQL.
- Return citations with document, version, chunk, and source metadata.

`POST /search` embeds the query through `embedding-service`, asks Qdrant for
dense vector, lexical sparse-vector, and sparse-ranked text-filtered matches,
and merges the candidates with normalized reciprocal rank fusion. PostgreSQL
hydrates only active chunk metadata after Qdrant matching, so stale document
versions remain excluded from API results.

Qdrant collections must use named vectors `dense` and `sparse` plus a text
payload index on chunk text. Legacy unnamed-vector collections must be recreated
and reingested.

`POST /chat` builds on this retrieval path before generation. It applies
configurable answerability gates and refuses without calling the configured LLM
when the retrieved evidence is too weak. The initial gates check the top retrieved score
and the minimum number of usable chunks. When the gates pass, `api-service`
caps the grounding context to a configured number of chunks, truncates chunk
text in the prompt, calls the configured OpenAI-compatible chat completions
endpoint, and returns the generated answer with the grounding chunk citations.
Local Ollama is the default private provider; external providers are explicit
deployments and receive the prompt context sent for generation.

Related decisions:

- [ADR 006: Chunking Strategy](../adr/006-chunking-strategy.md)
- [ADR 007: Retrieval and Answerability](../adr/007-retrieval-and-answerability.md)
- [ADR 009: Provider-Configurable Model Services](../adr/009-provider-configurable-model-services.md)
- [ADR 010: Qdrant-Owned Hybrid Retrieval](../adr/010-qdrant-owned-hybrid-retrieval.md)
