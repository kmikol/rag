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
