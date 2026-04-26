# ADR-000: Problem Definition and Scope

| Field        | Value                          |
|--------------|--------------------------------|
| ID           | ADR-000                        |
| Title        | Problem Definition and Scope   |
| Status       | Accepted                       |
| Deciders     | System owner                   |
| Date         | 2025-04-24                     |
| Supersedes   | —                              |

---

## Context

This is the foundational ADR for a personal Retrieval-Augmented Generation (RAG) system. Before any technical or architectural decisions are made, the scope, constraints, and operating context must be defined explicitly. These decisions constrain every downstream ADR in the series.

The system is being built for two simultaneous but distinct purposes:

1. **Personal utility** — a production-grade knowledge retrieval and question-answering system for the owner's own daily use.
2. **Portfolio demonstration** — a reference implementation published on GitHub intended to demonstrate sound architectural and engineering practices. Others may fork and adapt it.

These two purposes are separable. The runtime deployment is private and single-user. The codebase must nonetheless be clean, well-structured, and follow best practices, because it serves as a public artefact of engineering quality.

---

## Decisions

### 1. Target Use Cases

**Decision:** The system will support personal knowledge retrieval and question-answering over a user-defined corpus. It will not be scoped to a narrow domain — the corpus may contain anything the owner chooses to ingest.

**Rationale:** A general-purpose system is appropriate for a personal tool where the owner's informational needs span diverse topics. Domain-narrowing would add engineering complexity (specialised embeddings, fine-tuned models) without commensurate benefit for a single-user general corpus.

**Implications:**
- Embedding and retrieval strategies must generalise across topic areas.
- No domain-specific pre/post-processing pipelines are required at this stage.
- Future specialisation is possible without architectural rework if corpus scope narrows later.

---

### 2. Users and Interaction Modes

**Decision:** The system is single-user — the owner. Three interaction modes are in scope for this iteration:

- **Chat** — conversational, multi-turn interface.
- **Search** — direct retrieval queries returning ranked results without generation.
- **API** — programmatic access for scripting, automation, and integration with other personal tools.

Embedded functionality (widgets embedded in third-party interfaces or web pages) is explicitly **out of scope** for this iteration.

**Rationale:** Embedded functionality introduces cross-origin complexity, UI isolation concerns, and potentially different security postures. The marginal utility for a single-user personal system does not justify the additional engineering surface at this stage. The API mode provides the integration primitive that an embedding layer would eventually build on, so the capability is not permanently foreclosed.

**Implications:**
- No embedded widget or iframe integration is required.
- The API surface must be clean and well-documented, as it serves both personal scripting and as a portfolio demonstration of interface design.
- The chat and search modes may share a retrieval backend but may have different frontend interaction patterns.

---

### 3. Latency, Throughput, and Quality Constraints

**Decision:** The system will be constrained by a locally-deployed language model. The current candidate is **Gemma 4 E4B** (or equivalent small open model), with earlier testing around **Gemma 3 4B** achieving approximately **15 tokens per second** on the owner's hardware.

- End-to-end latency will be dominated by generation speed, not retrieval.
- **Streaming responses are mandatory**, not optional — they are the primary mechanism for making ~15 tok/sec feel acceptable to a human user.
- Response length should be bounded to prevent excessively long waits.
- Heavy multi-stage retrieval patterns (multiple sequential LLM calls, iterative re-ranking via a second LLM) are to be **avoided or minimised** because each additional call compounds latency.
- The model may be upgraded in the future. The architecture must not assume a specific model capability level and must make the model selection a configuration concern, not a structural one.

**Rationale:** At 15 tok/sec, a 300-token response takes 20 seconds. Without streaming, this is an unusable experience. With streaming, it is tolerable for a personal tool. Keeping the pipeline lean — tight prompts, fewer retrieved chunks, no redundant LLM calls — is a first-class design principle, not a premature optimisation.

**Implications:**
- Streaming must be implemented end-to-end: from the LLM through the API layer to the client.
- Prompt construction must be token-efficient. Retrieved context will be constrained by what can fit without generating unacceptably long waits.
- Retrieval re-ranking via a second LLM call is not currently viable. Cross-encoder re-ranking with a lightweight local model is acceptable if latency permits.
- LLM selection must be an environment variable / configuration value, not hardcoded.

---

### 4. Failure Mode Preference

**Decision:** **No answer is strongly preferred over a wrong answer.** When the system cannot retrieve sufficient grounding context, or when confidence in the generated answer is low, it must decline to answer rather than speculate or hallucinate.

**Rationale:** For a personal knowledge tool, an incorrect answer that is presented confidently erodes trust in the system rapidly and may propagate errors into the owner's work. A system that says "I don't have enough information to answer this reliably" is more useful than one that confabulates. This is a deliberate trade-off of recall for precision in the failure case.

**Implications:**
- Retrieval must include a minimum relevance threshold below which results are treated as insufficient.
- The generation prompt must include explicit instructions for the model to express uncertainty and to decline rather than speculate when context is inadequate.
- Response filtering or post-generation confidence checks may be warranted.
- System evaluation must treat false positives (wrong answers confidently given) as more costly than false negatives (correct refusals).

---

### 5. Deployment Environment

**Decision:** The system will be self-hosted on hardware owned and controlled by the owner. Components may be distributed across multiple physical devices on a **Tailscale private network**.

- No cloud-managed services are required or assumed.
- All components (vector store, LLM inference, API layer, any frontend) must be deployable on commodity or consumer-grade hardware.
- The Tailscale network provides the network perimeter. All devices on the Tailscale network are considered trusted by the system.
- The system is not exposed to the public internet.

**Rationale:** A self-hosted deployment is consistent with personal data sovereignty, eliminates recurring cloud costs, and allows the architecture to demonstrate that a capable RAG system can be built without managed services — which is itself a useful portfolio demonstration.

**Implications:**
- All component choices must have a viable self-hosted deployment path (Docker image, binary, or Python package).
- The architecture must support components running on different hosts, communicating over Tailscale-assigned addresses.
- High-availability and redundancy requirements are minimal — single-user, best-effort uptime is acceptable.
- GPU availability is constrained to what the owner's hardware provides. GPU resource allocation is a deployment configuration concern.
- Documentation must cover multi-device deployment via Tailscale as a first-class scenario.

---

### 6. Access Control

**Decision:** Two layers of access control will be used:

**Layer 1 — Network perimeter (Tailscale):** Only devices on the owner's Tailscale network can reach the system. This is the primary security boundary and requires no application-level implementation.

**Layer 2 — API key authentication:** The application's API layer will require a static bearer token, configured via environment variable. All clients (chat UI, search UI, scripts) must present this token. Requests without a valid token are rejected with HTTP 401.

Role-based access control, per-document permissions, multi-tenant isolation, and session-based authentication are **out of scope**.

**Rationale:** Tailscale provides strong network-level isolation for free. The API key layer adds defence-in-depth with minimal implementation cost (~1 hour) and demonstrates the correct pattern in the codebase — one that a fork could extend to JWT or OAuth without structural changes. More sophisticated access control would be over-engineering for a single-user system, but the code must not be structured in a way that would make adding it later difficult.

**Implications:**
- The API key must be configurable via environment variable (`RAG_API_KEY` or equivalent), never hardcoded.
- Middleware or a request interceptor must validate the token on every request before routing.
- The pattern should be clearly documented so that forks can substitute a more sophisticated auth mechanism.
- No user identity is propagated through the system — all requests are treated as the single authorised user.

---

### 7. Regulatory and Compliance Constraints

**Decision:** No regulatory constraints apply. The system processes data owned or licensed by the owner for personal use only. No GDPR, HIPAA, SOC 2, or other compliance frameworks are in scope.

**Rationale:** Single-user, self-hosted, non-commercial, personal use.

**Implications:**
- Data retention policies, audit logging requirements, and right-to-erasure mechanisms are not required by regulation.
- Basic operational logging (for debugging) is still desirable but is not shaped by compliance needs.
- If the system were ever extended to serve other users or to handle third-party personal data, this decision would need to be revisited before that extension is deployed.

---

## Consequences

The decisions in this ADR establish the following design constraints that apply to all subsequent ADRs:

| Constraint | Effect on downstream decisions |
|---|---|
| Single user, self-hosted | Simplifies auth, access control, multi-tenancy, and scaling decisions significantly |
| ~15 tok/sec generation | Mandates streaming; biases toward lean prompts and single-stage retrieval |
| No answer > wrong answer | Drives conservative retrieval thresholds and prompt design for uncertainty expression |
| Tailscale + API key | Establishes security model without cloud IAM or complex session management |
| Portfolio / GitHub codebase | All decisions must also be justifiable and legible to external readers of the code |
| No regulatory constraints | Removes compliance overhead from logging, retention, and data handling decisions |
| No embedded mode (this iteration) | Removes cross-origin and widget complexity from scope |
| General-purpose domain | Prevents premature optimisation toward any specific corpus type |

---

## Alternatives Considered

### Cloud-hosted deployment
A managed deployment on a cloud provider would offer better baseline availability and access to larger models via API. Rejected because it introduces recurring cost, reduces data sovereignty, and is inconsistent with the self-hosted portfolio demonstration goal.

### Public access with authentication
Opening the system to the public internet with strong authentication would allow access from anywhere. Rejected because the complexity of securing a public endpoint (TLS termination, rate limiting, DDoS mitigation) is not warranted for personal use. Tailscale provides equivalent ubiquitous access from the owner's own devices without the exposure.

### Semi-public portfolio access
Allowing visitors to a portfolio site to query the system was considered. Rejected for this iteration due to the significant added complexity of rate limiting, content safety guardrails, cost control, and multi-user behaviour — all of which would dominate the architecture and obscure the core RAG design being demonstrated.

### Fine-tuned or larger model
Using a larger or fine-tuned model for higher generation quality. Deferred rather than rejected. The architecture must make model selection a configuration concern so this can be revisited without structural changes when hardware changes.

---

## Review Triggers

This ADR should be revisited if any of the following occur:

- The system is extended to serve users other than the owner.
- The owner's hardware changes significantly, altering the latency constraint.
- The corpus begins to contain regulated personal data belonging to third parties.
- Embedded functionality is added in a future iteration.
- The system is exposed outside the Tailscale network.
