# rag Helm Chart

Deploys the RAG API service, ingestion worker, embedding service, and Qdrant.

The chart owns reusable Kubernetes behavior. Deployment repositories own
environment-specific values, secrets, hostnames, storage classes, resource
sizing, and chart version pins.

## Required Values

Set these values for a production-like deployment:

| Value | Purpose |
| --- | --- |
| `existingSecret` | Kubernetes Secret containing PostgreSQL credentials. |
| `database.host` | PostgreSQL host reachable from the cluster. |
| `database.port` | PostgreSQL port. |
| `database.name` | PostgreSQL database name. |
| `apiService.apiKey.existingSecret` | Kubernetes Secret containing the API bearer token. |
| `apiService.env.WATCH_ROOTS` | Source corpus path list as seen by the API container. |
| `apiService.env.DOCUMENT_STORE_PATH` | Managed document-copy path as seen by the API container. |
| `ingestionWorker.env.WATCH_ROOTS` | Source corpus path list as seen by the worker container. |
| `ingestionWorker.env.DOCUMENT_STORE_PATH` | Managed document-copy path as seen by the worker container. |
| `embeddingService.env.EMBEDDING_BACKEND` | Embedding backend, for example `ollama` or `google`. |
| `embeddingService.env.EMBEDDING_MODEL_NAME` | Embedding model name. |
| `embeddingService.env.EMBEDDING_DIMENSION` | Embedding vector dimension. |
| `embeddingService.env.EMBEDDING_ENDPOINT_URL` | External embedding/model endpoint used by the embedding service. |
| `qdrant.persistence` | Durable vector-store storage configuration. |

The chart builds `POSTGRES_URL` for `api-service` and `ingestion-worker` from
`existingSecret` and `database.*`. It sets in-cluster `QDRANT_URL` and
`EMBEDDING_SERVICE_URL` values for the API and worker.

## Secrets

Required secret names and keys for the homelab deployment contract:

| Secret | Keys | Used by |
| --- | --- | --- |
| `rag-db-credentials` | `DB_USER`, `DB_PASSWORD` | API service and ingestion worker. |
| `rag-api-credentials` | `RAG_API_KEY` | API service bearer-token auth. |
| `rag-llm-credentials` | `LLM_API_KEY` | API service when the selected LLM provider requires a key. |
| `rag-embedding-credentials` | `EMBEDDING_API_KEY` | Embedding service when the selected embedding provider requires a key. |

Provider API keys are optional for local Ollama-style deployments, but the
secret names are reserved so the cluster repository can add sealed manifests
without inspecting application internals.

## Storage Contract

Qdrant storage is backup-sensitive state and should use durable storage. The
managed document store is also backup-sensitive unless source watch roots are
the only recovery source you intend to keep. PostgreSQL is external to this
chart and must be backed up outside the chart.

The chart supports both chart-created PVCs and existing claims:

- Set `*.persistence.enabled=true` and leave `existingClaim` empty to let the
  chart create the component PVC.
- Set `*.persistence.enabled=true` and `existingClaim=<claim>` to mount a PVC
  created by the cluster repository or storage platform.
- Set `sharedStorage.enabled=true` to mount one shared PVC into both
  `api-service` and `ingestion-worker`, usually at `/data`.
- Set `sharedStorage.create=true` for a chart-created shared PVC, or set
  `sharedStorage.existingClaim` to use an existing NAS, RWX Longhorn, or other
  shared claim.

When `sharedStorage` is enabled, set:

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

`WATCH_ROOTS` must point at the same source paths for both the API and worker.
`DOCUMENT_STORE_PATH` must point at the same managed-copy path for both
components so document deletion and ingestion operate on the same files.

## External Dependencies

This chart does not deploy PostgreSQL, Ollama, or external LLM providers.
Deployment repositories must provide:

- PostgreSQL reachable from the cluster.
- Any required database schema migration process before serving real traffic.
- Embedding endpoint placement, for example an in-cluster Ollama service or a
  private LAN/Tailnet endpoint.
- Chat-completion endpoint placement through `apiService.env.LLM_*` values.
- Backup policy for PostgreSQL, Qdrant, source corpus, and managed documents.

Changing `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSION`, or the embedding backend
requires a new Qdrant collection or full reingestion.

## Examples

- `examples/values.example.yaml` for portable settings.
- `examples/values.cluster-home-arpa.example.yaml` for a homelab-shaped
  deployment using chart-created shared storage.
- `examples/values.existing-storage.example.yaml` for externally managed shared
  storage and existing component claims.

## OCI Chart Publishing

The chart is published to GitHub Container Registry by the `Publish Helm Chart`
workflow when a GitHub release is published. It can also be published manually
from the workflow dispatch form with an explicit semantic version.

Chart reference:

```text
oci://ghcr.io/kmikol/charts/rag
```

The workflow strips a leading `v` from release tags, so release tag `v0.1.0`
publishes chart version `0.1.0`. It packages the chart with both `version` and
`appVersion` set to the same semantic version. Chart versions must not use
SemVer build metadata (`+...`) because GHCR stores OCI chart versions as
registry tags. The publish job serializes by normalized chart version, then
refuses to push if that chart version already exists in GHCR.

Pull the packaged chart:

```bash
helm pull oci://ghcr.io/kmikol/charts/rag --version 0.1.0
```

Install directly from GHCR:

```bash
helm install rag oci://ghcr.io/kmikol/charts/rag \
  --version 0.1.0 \
  -f values.yaml
```

For Argo CD, use the repository and chart name separately:

```yaml
repoURL: oci://ghcr.io/kmikol/charts
chart: rag
targetRevision: 0.1.0
```

If the cluster must pull the chart without GHCR credentials, make the
`ghcr.io/kmikol/charts/rag` package public after the first publish. Private
cluster pulls should use a GHCR token with package read access.
