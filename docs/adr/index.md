# Architecture Decision Records

Architecture Decision Records (ADRs) document significant design choices made in this system, including the rationale and consequences of each decision.

## Overview

Each ADR follows a standard format:

- **Status**: Accepted, Proposed, Superseded, or Deprecated
- **Context**: The problem or situation that required a decision
- **Decision**: What was chosen and why
- **Rationale**: The deeper reasoning behind the choice
- **Consequences / Implications**: Positive and negative impacts
- **Alternatives**: Other options that were considered and rejected or deferred

## Current ADRs

| ID | Title | Status | Summary |
|----|-------|--------|---------|
| [000](000-problem-definition-and-scope.md) | Problem Definition and Scope | Accepted | Defines the single-user, self-hosted, local-model RAG system scope and constraints |
| [001](001-data-sources-and-ingestion.md) | Data Sources and Ingestion | Accepted | Watch directories are authoritative; PDF and Markdown are initial formats |
| [002](002-storage-and-metadata-topology.md) | Storage and Metadata Topology | Accepted | PostgreSQL runs centrally on NAS; Qdrant is an independent movable Docker service |
| [003](003-service-boundaries.md) | Service Boundaries | Accepted | Initial split uses `api-service` and `ingestion-worker`, with retrieval/generation internal to API |
| [004](004-embedding-service.md) | Embedding Service | Accepted | Dedicated `embedding-service` handles query and batch embeddings |
| [005](005-document-identity-and-ingestion-state.md) | Document Identity and Ingestion State | Accepted | Logical documents have immutable indexed versions and explicit ingestion states |
| [006](006-chunking-strategy.md) | Chunking Strategy | Accepted | Structure-aware Markdown/PDF chunking with citation metadata |
| [007](007-retrieval-and-answerability.md) | Retrieval and Answerability | Accepted | Hybrid retrieval, citations, and configurable refusal gates |
| [008](008-job-coordination-and-service-contracts.md) | Job Coordination and Service Contracts | Accepted | PostgreSQL-backed job records and minimal service API contracts |
| [009](009-provider-configurable-model-services.md) | Provider-Configurable Model Services | Accepted | Model providers are selected by env; Ollama remains the private default while external APIs are explicit deployments |

## When to Reference These

- **Before changing corpus lifecycle behavior**: See ADR-001 and ADR-005.
- **Before moving services between machines or model providers**: See ADR-002, ADR-003, ADR-004, and ADR-009.
- **Before changing chunking or retrieval**: See ADR-006 and ADR-007.
- **Before adding queue infrastructure**: See ADR-008.
- **When wondering why the system refuses to answer**: See ADR-000 and ADR-007.

## How to Add New ADRs

1. Create a new file: `00N-short-title.md`.
2. Use the full format with context, decision, rationale, implications, alternatives, and review triggers.
3. Link related ADRs where relevant.
4. Update this index and `docs/mkdocs.yml`.

## Design Philosophy

1. **Trust over coverage**: The system should refuse weakly grounded answers.
2. **Local but movable**: Services should run privately and move between machines by configuration.
3. **Simple first, extensible later**: Use clear interfaces and defer heavier infrastructure until it is justified.
4. **Observable decisions**: Architecture choices should be documented and traceable.
