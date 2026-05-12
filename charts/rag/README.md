# rag Helm Chart

Deploys RAG API service, ingestion worker, embedding service, and Qdrant.

## Notes

- PostgreSQL is external. Override `database.host`, `database.port`, and `database.name` for the target cluster.
- Database credentials are loaded from `existingSecret` with keys defined in `database.userSecretKey` and `database.passwordSecretKey`; the chart builds `POSTGRES_URL` for the services from those values.
- The chart sets in-cluster `QDRANT_URL` and `EMBEDDING_SERVICE_URL` values for `api-service` and `ingestion-worker`.
- Persistence is disabled by default for all components and can be enabled per component.
- Ingress is disabled by default and supports a host/path list under `apiService.ingress.hosts`.
- Runtime settings such as `RAG_API_KEY`, `WATCH_ROOTS`, `DOCUMENT_STORE_PATH`, and model-provider settings should be passed through the relevant `env` maps.

## Examples

- `examples/values.example.yaml` for portable settings.
- `examples/values.cluster-home-arpa.example.yaml` for a homelab route example.
