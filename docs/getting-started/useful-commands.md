# Useful Commands

## Documentation

```bash
make docs.serve.local
```

Serve the documentation at <http://localhost:8001>.

```bash
make docs.build
```

Build the static site into `site/`.

## Planned Environment Variables

The first implementation should use these configuration keys:

```text
POSTGRES_URL
QDRANT_URL
EMBEDDING_SERVICE_URL
OLLAMA_URL
WATCH_ROOTS
DOCUMENT_STORE_PATH
RAG_API_KEY
```

These are defined in [ADR 008](../adr/008-job-coordination-and-service-contracts.md).
