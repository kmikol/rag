# Getting Started: Deploy and Use the RAG

This guide describes how to deploy the personal RAG system on a NAS, server, or
private LAN/Tailscale host, then ingest documents and query them through the API.

The system is single-user and private. Keep it on a trusted private network
unless a future deployment adds a reverse proxy, TLS, and stronger exposure
controls.

## What Gets Deployed

The runtime stack contains these services:

| Service | Role | Persistent state |
|---|---|---|
| `api-service` | Authenticated API for ingestion jobs, documents, search, and chat | None |
| `ingestion-worker` | Health endpoint plus one-shot ingestion CLI | None |
| `embedding-service` | Embedding API used by ingestion and search | None |
| `postgres` | Metadata, document lifecycle, chunks, and ingestion jobs | PostgreSQL data volume |
| `qdrant` | Dense, sparse, and text retrieval index | Qdrant data volume |
| Ollama or provider endpoint | Chat and embedding model backend | Model host storage |

The source document directories are authoritative. A supported file is in the
corpus when it exists under `WATCH_ROOTS`. The managed document store is an
internal copy used for auditability and future reprocessing.

Currently supported source formats:

- Markdown: `.md`, `.markdown`
- PDF files with an extractable text layer: `.pdf`

Scanned image-only PDFs are detected as having no extractable text and fail
ingestion until OCR support is added.

## Deployment Topology

The default self-hosted topology is:

- NAS/server: PostgreSQL, Qdrant, `api-service`, `embedding-service`,
  `ingestion-worker`, watch-root mounts, managed document store.
- Model host: Ollama, when model serving is better placed on a Mac, GPU host, or
  another machine on the private network.

You can run everything on one server if it has enough CPU, memory, and storage.
If Ollama runs on a different machine, use its LAN or Tailscale address in the
environment files. Do not rely on `host.docker.internal` for a NAS/server
deployment unless you have explicitly configured it for that Docker host.

External model providers are supported by configuration, but they are not a
private self-hosted deployment. Any document chunks, queries, and prompts sent to
an external embedding or chat provider leave your environment.

## Prerequisites

On the NAS/server:

- Docker Engine with Compose v2.
- Git checkout of this repository, or images built from this repository.
- Persistent storage for PostgreSQL, Qdrant, watch roots, and managed document
  copies.
- Network access from containers to the model host.
- A private API token for `RAG_API_KEY`.

For local Ollama:

```bash
ollama pull gemma3:4b
ollama pull embeddinggemma
```

If Ollama runs on another host, make sure it listens on an address reachable
from the NAS/server containers.

## Storage Layout

Use explicit persistent directories on the NAS/server. For example:

```text
/volume1/rag/
  postgres/
  qdrant/
  watch/
    papers/
    notes/
  documents/
```

`watch/` contains the files you intentionally want indexed. `documents/` is
owned by the RAG system and should not be edited manually.

Back up all of these:

- PostgreSQL data, preferably with `pg_dump` or a database-aware backup.
- Qdrant storage.
- Managed document store.
- Source watch roots, if they are not backed up elsewhere.
- Deployment env files and Compose files, excluding committed defaults.

## Environment Files

The repository includes safe examples under `config/env/*.env.example`. For a
server deployment, keep deployment-specific env files outside version control or
inject them with your NAS/container manager.

Minimum `api-service` settings:

```dotenv
RAG_API_KEY=replace-with-a-long-private-token
POSTGRES_URL=postgresql+psycopg://rag:replace-me@postgres:5432/rag
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=rag_chunks
EMBEDDING_SERVICE_URL=http://embedding-service:8000
EMBEDDING_MODEL_NAME=embeddinggemma
LLM_PROVIDER=openai_compatible
LLM_CHAT_COMPLETIONS_URL=http://ollama-host:11434/v1/chat/completions
LLM_MODEL=gemma3:4b
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=120
CHAT_MIN_TOP_SCORE=0.5
CHAT_MIN_USABLE_CHUNKS=1
CHAT_MAX_CONTEXT_CHUNKS=5
CHAT_MAX_CHUNK_CHARS=2000
WATCH_ROOTS=/watch/papers:/watch/notes
DOCUMENT_STORE_PATH=/documents
```

Minimum `ingestion-worker` settings:

```dotenv
POSTGRES_URL=postgresql+psycopg://rag:replace-me@postgres:5432/rag
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=rag_chunks
EMBEDDING_SERVICE_URL=http://embedding-service:8000
EMBEDDING_MODEL_NAME=embeddinggemma
WATCH_ROOTS=/watch/papers:/watch/notes
DOCUMENT_STORE_PATH=/documents
```

Minimum `embedding-service` settings for Ollama embeddings:

```dotenv
EMBEDDING_BACKEND=ollama
EMBEDDING_MODEL_NAME=embeddinggemma
EMBEDDING_DIMENSION=768
EMBEDDING_ENDPOINT_URL=http://ollama-host:11434
EMBEDDING_API_KEY=
EMBEDDING_TIMEOUT_SECONDS=30
EMBEDDING_KEEP_ALIVE=5m
```

Use `:` between multiple watch roots on Linux-based servers. Every path listed
in `WATCH_ROOTS` must be mounted into both `api-service` and
`ingestion-worker`.

## Compose Example for a NAS or Server

The checked-in `docker-compose.yml` is a local development baseline. For a
server deployment, add persistent volumes and real env files. This example keeps
all application services on the NAS/server and points them at an Ollama host on
the private network:

```yaml
services:
  postgres:
    image: postgres:16
    env_file:
      - ./deploy/env/postgres.env
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - /volume1/rag/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag"]
      interval: 5s
      timeout: 3s
      retries: 10

  qdrant:
    image: qdrant/qdrant:v1.12.4
    volumes:
      - /volume1/rag/qdrant:/qdrant/storage

  embedding-service:
    build:
      context: .
      dockerfile: embedding_service/Dockerfile
    env_file:
      - ./deploy/env/embedding-service.env
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"]
      interval: 5s
      timeout: 5s
      retries: 10

  api-service:
    build:
      context: .
      dockerfile: api_service/Dockerfile
    env_file:
      - ./deploy/env/api-service.env
    ports:
      - "8000:8000"
    volumes:
      - /volume1/rag/watch/papers:/watch/papers
      - /volume1/rag/watch/notes:/watch/notes
      - /volume1/rag/documents:/documents
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      embedding-service:
        condition: service_healthy

  ingestion-worker:
    build:
      context: .
      dockerfile: ingestion_worker/Dockerfile
    env_file:
      - ./deploy/env/ingestion-worker.env
    volumes:
      - /volume1/rag/watch/papers:/watch/papers
      - /volume1/rag/watch/notes:/watch/notes
      - /volume1/rag/documents:/documents
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      embedding-service:
        condition: service_healthy
```

The PostgreSQL port binding above is localhost-only so migrations and backups
can run from the server checkout. Remove it if your operational tooling reaches
PostgreSQL another way. Do not expose PostgreSQL or Qdrant ports publicly.
Expose `api-service` only on the private network unless a future deployment adds
a reviewed public-access setup.

## First Start

Build the images and start the long-running services:

```bash
docker compose up -d --build postgres qdrant embedding-service api-service ingestion-worker
```

Apply database migrations from a repository checkout that has the Python
dependencies installed:

```bash
POSTGRES_URL=postgresql+psycopg://rag:replace-me@localhost:5432/rag make db.upgrade
```

If PostgreSQL is not exposed on localhost, use its private network host or run
the migration command from a machine that can reach it. The current service
images are runtime images and do not include the Alembic migration files, so
migrations are run from the repository checkout.

Verify health:

```bash
curl -fsS http://server-host:8000/health
docker compose exec embedding-service python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/model-info').read().decode())"
```

The API health endpoint does not require a bearer token. The chat, search,
ingestion, and document endpoints do.

## Ingest Documents

Place supported files under one of the configured watch roots:

```text
/volume1/rag/watch/papers/example-paper.pdf
/volume1/rag/watch/notes/project-notes.md
```

Create a full-scan ingestion job:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  http://server-host:8000/ingest
```

The response contains a job ID. A job is only a persisted request; the worker
must process it. Run the one-shot worker:

```bash
docker compose run --rm ingestion-worker \
  python -m ingestion_worker.worker --fail-on-error
```

Poll job status:

```bash
curl -fsS \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  http://server-host:8000/ingest/<job-id>
```

For a single file, create a targeted job using the path as it appears inside the
containers:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"requested_path":"/watch/notes/project-notes.md"}' \
  http://server-host:8000/ingest
```

Then run the one-shot worker again.

## Scheduled Reconciliation

A full-scan job reconciles additions and deletions under healthy watch roots.
Run it on a schedule with cron, systemd timers, or the NAS task scheduler. A
simple nightly shell command is:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  http://server-host:8000/ingest && \
docker compose run --rm ingestion-worker \
  python -m ingestion_worker.worker --fail-on-error
```

The worker processes at most one pending job per invocation. If you expect many
queued jobs, invoke it once per pending job and check job status through
`GET /ingest/{job_id}`, or schedule it more frequently.

Deletion behavior is intentional:

- Removing a source file from a healthy watch root removes it from Qdrant,
  PostgreSQL, and the managed document store during full-scan reconciliation.
- `DELETE /documents/{id}` removes the source file, managed copy, vectors, and
  metadata immediately.
- If a watch root is missing or unreadable, reconciliation skips deletion for
  documents under that root to avoid treating a failed mount as an empty corpus.

## Search and Chat

List documents:

```bash
curl -fsS \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  http://server-host:8000/documents
```

Search retrieved chunks:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query":"What does the project say about PostgreSQL?", "limit":5}' \
  http://server-host:8000/search
```

Ask a grounded question:

```bash
curl -fsS -X POST \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query":"What does the indexed material say about PostgreSQL?", "limit":5}' \
  http://server-host:8000/chat
```

Responses include citations. If retrieval evidence is too weak, chat refuses
instead of generating an unsupported answer.

For streaming with an OpenAI-compatible backend:

```bash
curl -N -X POST \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"query":"Summarize the indexed notes about backups.", "limit":5, "stream":true}' \
  http://server-host:8000/chat
```

Streaming is implemented for the OpenAI-compatible generation client. The
Google native generation client currently supports non-streaming responses only.

## Delete Documents

Find the document ID:

```bash
curl -fsS \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  http://server-host:8000/documents
```

Delete it:

```bash
curl -fsS -X DELETE \
  -H "Authorization: Bearer ${RAG_API_KEY}" \
  http://server-host:8000/documents/<document-id>
```

This is permanent. It removes vectors, metadata, the managed copy, and the
source file under `WATCH_ROOTS`.

## Upgrade Procedure

Use this order for routine updates:

1. Back up PostgreSQL, Qdrant, managed documents, and deployment env files.
2. Pull or deploy the new application revision.
3. Rebuild images:

   ```bash
   docker compose build
   ```

4. Apply migrations:

   ```bash
   POSTGRES_URL=postgresql+psycopg://rag:replace-me@server-host:5432/rag make db.upgrade
   ```

5. Restart services:

   ```bash
   docker compose up -d
   ```

6. Run a full-scan ingestion job and one-shot worker if the release changes
   parsing, chunking, embedding, or vector-index behavior.

Changing `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSION`, or the embedding
provider requires a new Qdrant collection or full reingestion. Existing
collections with incompatible vector shapes are rejected rather than rewritten.

## Troubleshooting

`401 Invalid API key`

: Check the `Authorization: Bearer <RAG_API_KEY>` header and make sure the API
  container was restarted after changing `RAG_API_KEY`.

`Embedding service unavailable`

: Confirm `EMBEDDING_SERVICE_URL` is reachable from `api-service` and
  `ingestion-worker`. Then confirm `EMBEDDING_ENDPOINT_URL` is reachable from
  `embedding-service`.

`Ollama unavailable`

: Confirm Ollama is running, reachable from the Docker host, and has the
  configured models pulled. Prefer a private LAN or Tailscale URL in server
  deployments.

`Unsupported document format`

: Only Markdown and PDF files are currently parsed. Unsupported extensions are
  skipped during full scans and fail targeted single-file ingestion.

`PDF has no extractable text`

: The PDF likely contains scanned images without a text layer. OCR is not part
  of the current implementation.

`Top retrieved evidence is below the answerability threshold`

: The system found weak evidence and refused to answer. Ingest more relevant
  material, ask a narrower question, or tune the chat threshold variables for
  your corpus.

Worker exits successfully but nothing changes

: The one-shot worker processes at most one pending job. Check that `POST
  /ingest` created a job, that the worker has the same `POSTGRES_URL`, and that
  watch-root paths inside the container match `WATCH_ROOTS`.
