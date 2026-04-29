# ADR-009: Provider-Configurable Model Services

- **Status:** Accepted
- **Date:** 2026-04-29
- **Supersedes:** The Ollama-only generation assumption in ADR-000, ADR-003, and ADR-008, and the deferred-cloud-embedding assumption in ADR-004.

## Context

The initial architecture assumed that Ollama hosts generation and that
`embedding-service` uses a local model-serving backend. That remains the best
default for private self-hosted deployments, but it makes production-like
end-to-end testing cumbersome when a real model endpoint is needed in CI.

Several providers expose OpenAI-compatible chat completion APIs, and Google AI
Studio exposes both an OpenAI-compatible chat endpoint and REST embedding
endpoints. The system needs a single runtime shape where model providers are
selected by environment variables rather than separate code paths.

## Decision

Model access will be provider-configurable through service-owned facades:

- `api-service` uses an internal LLM client interface for grounded generation.
- The first generation backend is an OpenAI-compatible chat completions client.
- `embedding-service` owns embedding provider selection behind its existing
  HTTP API.
- Ollama remains the default local/self-hosted deployment target.
- External APIs are allowed only when explicitly configured by environment
  variables.

Privacy is therefore a deployment property. A deployment using Ollama and local
embedding backends is private and self-hosted. A deployment using Google,
OpenAI, Anthropic, or another external provider sends configured prompts and
document text to that provider and must be treated accordingly.

## Rationale

Provider-neutral boundaries avoid duplicating tests, prompts, and retrieval
logic for local and cloud-backed runs. They also keep the public API stable:
retrieval, answerability, citation handling, and refusal behavior do not need to
know which model provider generated embeddings or answers.

Keeping provider selection in environment variables preserves the existing
Dockerized operational model. It also keeps self-hosted Ollama as the default
while allowing CI or operator-selected deployments to use external APIs.

## Consequences

- Secrets must be injected through deployment or CI configuration and must not
  be committed.
- Documentation must clearly identify when a test or deployment uses an
  external API.
- Changing embedding model, dimension, or provider still requires a new vector
  collection or full re-embedding.
- Anthropic is not OpenAI-compatible by default; supporting it directly requires
  a provider-specific adapter or an OpenAI-compatible gateway.

## Alternatives

### Keep Google AI Studio as a special E2E-only path

Rejected. That would make local Ollama and external-provider testing drift into
separate paths and would not exercise the same runtime configuration model.

### Keep Ollama-only runtime support

Rejected. This preserves the strictest self-hosted interpretation but prevents a
real model-backed E2E test from running in CI without local model hardware.

### Add a full provider plugin framework

Deferred. The current need is satisfied by one OpenAI-compatible generation
client and embedding backends selected by environment variables.

## Review Triggers

- A non-OpenAI-compatible generation provider is added directly.
- Multiple embedding providers must coexist in the same deployment.
- Provider-specific safety, logging, or data-retention controls become
  necessary.
