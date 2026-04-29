# Running

## Local Stack

Start the local Docker stack with:

```bash
make up
```

The default committed environment files point application services at
PostgreSQL, Qdrant, `embedding-service`, and a local Ollama-compatible model
host. The model host itself is configured by environment variables rather than
hardcoded service names.

For local Ollama generation, set:

```bash
LLM_PROVIDER=openai_compatible
LLM_CHAT_COMPLETIONS_URL=http://host.docker.internal:11434/v1/chat/completions
LLM_MODEL=gemma3:4b
LLM_API_KEY=
```

For local Ollama embeddings, set:

```bash
EMBEDDING_BACKEND=ollama
EMBEDDING_ENDPOINT_URL=http://host.docker.internal:11434
EMBEDDING_MODEL_NAME=embeddinggemma
EMBEDDING_DIMENSION=768
```

## End-to-End Test

`make test.e2e` runs a production-like RAG flow against real application
endpoints and the model provider configured in `docker-compose.e2e.yml`.
The current CI backend is Google AI Studio. This is not a private/self-hosted
test run: synthetic test documents and prompts are sent to the configured
external provider.

Required environment:

```bash
GEMINI_API_KEY_E2E_TEST=...
```

The E2E Compose stack sets `EMBEDDING_MODEL_NAME=gemini-embedding-2` for
Google embeddings and fixes the chat model to Google's API model id
`gemma-4-31b-it`.

Run:

```bash
GEMINI_API_KEY_E2E_TEST=... make test.e2e
```

The E2E test intentionally uses invented, non-personal document text and
questions. It fails when required provider credentials are missing.

In GitHub Actions, provider-backed E2E is part of the normal CI workflow and
runs only after lint, typecheck, unit, integration, and smoke checks pass. It
requires `GEMINI_API_KEY_E2E_TEST` as a repository secret.

Fork PRs are not a supported workflow for provider-backed E2E in this repository:
GitHub does not expose repository secrets to untrusted forked pull requests, so
the E2E job will fail if a fork PR is opened. If fork contributions become
relevant later, handle that with repository settings and maintainer policy rather
than by weakening the E2E gate.

The backend configuration is documented in [Useful Commands](useful-commands.md),
[ADR 008](../adr/008-job-coordination-and-service-contracts.md), and
[ADR 009](../adr/009-provider-configurable-model-services.md).
