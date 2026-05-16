# Homelab Helm Configuration Contract

The `cluster` repository configures RAG through Helm values only. It should not
copy application manifests or inspect Python service internals.

## Required Secrets

| Secret | Required keys | Purpose |
| --- | --- | --- |
| `rag-db-credentials` | `DB_USER`, `DB_PASSWORD` | PostgreSQL credentials for API and worker. |
| `rag-api-credentials` | `RAG_API_KEY` | Bearer token for protected API endpoints. |
| `rag-llm-credentials` | `LLM_API_KEY` | LLM provider key when the provider requires one. |
| `rag-embedding-credentials` | `EMBEDDING_API_KEY` | Embedding provider key when the provider requires one. |

Local Ollama deployments may set empty provider keys or omit the optional
provider-key secret references, but the secret names are reserved for sealed
cluster manifests.

## Required Values

The cluster values must provide:

- `database.existingSecret` pointing at `rag-db-credentials`.
- `database.port` and `database.name`.
- `database.host` when `postgresql.enabled=false`; otherwise the chart uses the
  chart-owned PostgreSQL Service.
- `postgresql` configuration when the deployment should own its own database.
- `apiService.apiKey.existingSecret` pointing at `rag-api-credentials`.
- `apiService.env.WATCH_ROOTS` and `apiService.env.DOCUMENT_STORE_PATH`.
- `ingestionWorker.env.WATCH_ROOTS` and `ingestionWorker.env.DOCUMENT_STORE_PATH`.
- `embedding.backend`.
- `embedding.modelName`.
- `embedding.dimension`.
- `embedding.endpointUrl`.
- `llm.provider`.
- `llm.model`.
- `apiService.useEmbeddingConfig`.
- `apiService.useLlmConfig`.
- `ingestionWorker.useEmbeddingConfig`.
- `embeddingService.useEmbeddingConfig`.
- Durable `qdrant.persistence` configuration.

## Storage

PostgreSQL and Qdrant are backup-sensitive state. The managed document store is
backup-sensitive unless the source corpus is the only recovery source you
intend to keep. If `postgresql.enabled=true`, this chart creates PostgreSQL and
its optional PVC, but backup remains an operator responsibility.

The chart supports both storage ownership models:

- Chart-created PVCs: set `*.persistence.enabled=true` and leave
  `existingClaim` empty.
- Existing PVCs: set `*.persistence.enabled=true` and
  `existingClaim=<claim-name>`.
- Shared corpus/document storage: set `sharedStorage.enabled=true` to mount one
  claim into both API and worker pods, normally at `/data`.
- Shared chart-created storage: set `sharedStorage.create=true`.
- Shared external storage: set `sharedStorage.existingClaim=<claim-name>`.

For shared storage, use matching paths in API and worker values:

```yaml
apiService:
  env:
    WATCH_ROOTS: /data/watch
    DOCUMENT_STORE_PATH: /data/documents
ingestionWorker:
  env:
    WATCH_ROOTS: /data/watch
    DOCUMENT_STORE_PATH: /data/documents
```

## External Dependencies

The chart can deploy PostgreSQL, but it does not deploy Ollama or LLM
providers. The cluster configuration must define whether PostgreSQL is
chart-owned or external, and where model/provider services live.

Changing the embedding backend, model name, or vector dimension requires a new
Qdrant collection or full reingestion.

## Safe Examples

Use these committed examples as the rendering contract:

- `charts/rag/examples/values.cluster-home-arpa.example.yaml`
- `charts/rag/examples/values.existing-storage.example.yaml`
