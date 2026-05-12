# rag Helm Chart

Deploys RAG API service, ingestion worker, embedding service, and Qdrant.

## Notes

- PostgreSQL is external. Override `database.host`, `database.port`, and `database.name` for the target cluster.
- Database credentials are loaded from `existingSecret` with keys defined in `database.userSecretKey` and `database.passwordSecretKey`; the chart builds `POSTGRES_URL` for the services from those values.
- The chart sets in-cluster `QDRANT_URL` and `EMBEDDING_SERVICE_URL` values for `api-service` and `ingestion-worker`.
- Set `apiService.apiKey.existingSecret` to source `RAG_API_KEY` from a Kubernetes Secret, or use `apiService.extraEnv`/`apiService.envFrom` for other secret-backed environment variables.
- Persistence is disabled by default for all components and can be enabled per component.
- Ingress is disabled by default and supports a host/path list under `apiService.ingress.hosts`.
- The `ingestion-worker` Deployment exposes the health server. Enable `ingestionWorker.cronJob` to run the one-shot worker on a schedule.
- Runtime settings such as `WATCH_ROOTS`, `DOCUMENT_STORE_PATH`, and model-provider settings should be passed through the relevant `env`, `extraEnv`, or `envFrom` values.

## Examples

- `examples/values.example.yaml` for portable settings.
- `examples/values.cluster-home-arpa.example.yaml` for a homelab route example.

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
refuses to push if that chart version already exists in GHCR. Cluster
repositories should pin the chart by version instead of tracking an unversioned
reference.

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
