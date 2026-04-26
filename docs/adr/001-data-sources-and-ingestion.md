# ADR-001: Data Sources and Ingestion

| Field        | Value                          |
|--------------|--------------------------------|
| ID           | ADR-001                        |
| Title        | Data Sources and Ingestion     |
| Status       | Accepted                       |
| Deciders     | System owner                   |
| Date         | 2025-04-24                     |
| Supersedes   | —                              |
| Depends on   | ADR-000 (Problem Definition and Scope), ADR-002 (Storage and Metadata Topology) |

---

## Context

This ADR defines how documents enter the RAG system — what formats are accepted, where they come from, how ingestion is triggered, how the system maintains consistency between the source file store and the index, and how the document lifecycle (add, update, delete) is managed.

The system is single-user and self-hosted (ADR-000). All data sources are local files on devices controlled by the owner. There are no external APIs, databases, or third-party content streams to integrate with at this stage. The architecture must nonetheless be structured so that new source types and file formats can be added without restructuring the pipeline.

---

## Decisions

### 1. Supported File Formats

**Decision:** The initial supported formats are **PDF** and **Markdown**. The ingestion pipeline must be designed as a format-dispatch architecture so that additional formats can be added by implementing a new parser without modifying existing pipeline logic.

**Rationale:** PDF and Markdown cover the dominant formats in a personal knowledge corpus — research papers, documentation, notes, exported content, and written artefacts. Markdown in particular is the native format of most personal knowledge management tools (Obsidian, Logseq, etc.).

Extensibility is a first-class requirement because the owner may later want to add DOCX, HTML, EPUB, plain text, or code files. The right pattern is a **format registry**: a map from file extension (and optionally MIME type) to a parser implementation. Each parser is responsible for extracting clean text and basic structural metadata from its format. The rest of the pipeline is format-agnostic and operates on the normalised output.

**Implications:**
- A `BaseDocumentParser` interface or abstract class must be defined. PDF and Markdown parsers implement it.
- File format detection should use both file extension and MIME type sniffing (extension alone is unreliable).
- Adding a new format requires: implementing the parser, registering it, and adding any new dependencies. No existing code changes.
- Unsupported formats encountered during a scan must be logged and skipped gracefully, not cause pipeline failure.
- PDF parsing must handle both native text-layer PDFs and scanned image PDFs differently. Scanned PDFs without a text layer will return empty content — this must be detected and flagged. OCR integration is deferred but the parser interface must not preclude it.

---

### 2. Document Inclusion Criteria

**Decision:** **Any document placed in the configured watch directory (or directory tree) is eligible for ingestion.** Inclusion is determined solely by presence — no tagging, flagging, or explicit opt-in is required per document. Documents in subdirectories are included recursively.

The watch root(s) are defined in system configuration and may point to one or more directories across the Tailscale network.

**Rationale:** An explicit opt-in mechanism (e.g., tagging files, maintaining an include list) introduces friction and is easy to forget. For a personal system where the owner controls what goes in the directory, presence is a sufficient and intuitive proxy for intent. If a document should not be indexed, it should not be in the watch directory.

**Implications:**
- Watch paths are a required configuration value. The system must refuse to start without at least one valid configured path.
- Recursive directory traversal must be implemented. Directory depth should not be artificially limited.
- Hidden files and directories (dot-prefixed) should be skipped by default, with a configuration option to include them.
- Symlinks should be followed, with cycle detection to prevent infinite traversal.
- Files with unsupported extensions are silently skipped with a log entry. They do not cause errors.

---

### 3. Ingestion Trigger Mechanism

**Decision:** Two complementary ingestion trigger mechanisms will be implemented:

**Primary — On-demand ingestion via API:**
A `POST /ingest` endpoint triggers an immediate ingestion run. The caller may optionally specify a single file path to ingest only that document, or omit it to run a full scan of all watch directories. The endpoint returns immediately with a job ID; ingestion runs asynchronously and status is queryable via `GET /ingest/{job_id}`.

**Secondary — Scheduled nightly job:**
A background scheduler runs a full ingestion scan once per night at a configurable time (default: 02:00 local time). This serves as a fallback to catch documents that were added without an explicit on-demand trigger, and as a reconciliation mechanism for deletions (see Decision 6).

No file-system watcher (inotify, FSEvents, etc.) will be implemented in this iteration.

**Rationale:** On-demand ingestion gives the owner deliberate, immediate control — a document can be added and queried within seconds of triggering. The nightly job provides a safety net without requiring the owner to remember to trigger ingestion after every addition.

A file-system watcher was considered but rejected. Watchers are platform-specific, add a persistent background process with non-trivial failure modes, and require handling edge cases (rapid successive writes, partial writes, file locks). For a personal system where ingestion lag of up to 24 hours is acceptable as a fallback, the watcher's complexity is not justified.

The asynchronous job pattern for the API endpoint is important: ingesting a large document or a full directory scan may take tens of seconds to minutes. A synchronous HTTP response would time out or require the caller to hold a long connection open. The job/status pattern is clean, easy to implement, and easy to demonstrate.

**Implications:**
- An async job queue is required. A simple in-process queue (e.g., Python `asyncio.Queue` or a lightweight task runner) is sufficient. A full external queue (Redis, Celery) is over-engineering for single-user volume.
- The scheduler must be embedded in the application process or run as a companion cron job. A cron entry calling `POST /ingest` is the simplest approach and avoids a persistent scheduler dependency.
- The nightly run time must be configurable via environment variable.
- Ingestion job status (running, completed, failed, items processed, errors) must be persisted in the metadata store so the owner can inspect what happened across service restarts.
- The `POST /ingest` endpoint is subject to API key authentication (ADR-000).

---

### 4. Raw Document Storage

**Decision:** The configured watch directories are the authoritative source of the corpus. The original source document will be **copied into a managed document store** at ingestion time, but this managed copy is an internal preservation and reprocessing artefact, not the definition of corpus membership.

**Rationale:** For a personal file-based knowledge system, the simplest and most intuitive ownership model is: if a supported document is present in a configured watch directory, it belongs in the corpus; if it is removed from all configured watch directories, it no longer belongs in the corpus. This keeps corpus management aligned with the owner's normal filesystem workflow.

Storing a managed copy of the original still enables two important capabilities:
- **Re-processing:** If the chunking strategy or embedding model changes, documents can be re-processed from the stored original without the owner needing to re-import anything.
- **Auditing:** The exact content that was indexed is preserved, which matters when generated answers cite a document.

The managed copy does not override the watch directory's authority. If the source file is removed from the watch directory, the corresponding managed copy, chunks, embeddings, and metadata are removed during deletion reconciliation, subject to the safety checks defined in Decision 7.

**Implications:**
- A managed document store directory must be defined in configuration (e.g., `~/.rag/documents/` or a configurable path).
- Documents are stored with a stable internal ID as their filename (UUID or content-hash-based). Original filename and path are stored as metadata.
- The document store must be included in any backup strategy the owner maintains.
- The managed store, metadata store, and vector index must remain consistent — an active document must have a source file under a healthy watch root, a managed copy, metadata, and corresponding chunks in the index. The nightly reconciliation job enforces this.

---

### 5. Duplicate Detection

**Decision:** Duplicate detection will use **SHA-256 content hashing**. At ingestion time, the hash of the incoming file is computed and compared against hashes of all previously ingested documents. If a match exists, the file is treated as a duplicate and ingestion is skipped.

**Rationale:** Path-based identity is unreliable — the same document can exist at multiple paths, or a file can be moved and re-discovered. Content hashing is path-agnostic and correctly identifies duplicates regardless of filename or location. SHA-256 is collision-resistant at practical scales and fast enough that hashing even large documents is not a meaningful bottleneck.

**Implications:**
- SHA-256 hashes of all ingested documents must be stored in the document metadata store defined in ADR-002.
- At ingestion, the file is hashed before any other processing. Hash lookup is the first gate — if the document is already present with this hash, processing stops immediately.
- The hash is also used to detect updates: if a document at a previously-ingested path has a different hash, it has been modified and must be re-ingested (see Decision 6).
- Hash computation must occur on the raw file bytes before any normalisation or cleaning.

---

### 6. Document Update Handling

**Decision:** When a previously-ingested document is modified (detected by hash change on a path that maps to an existing document), the system will **delete all existing chunks and embeddings for that document and re-ingest it from scratch**.

**Rationale:** Differential re-ingestion (detecting which sections changed and only updating those chunks) is significantly more complex to implement correctly and provides marginal benefit at personal document volumes. The brief period during which a document is being re-processed — where it has been removed from the index but not yet re-added — is acceptable for a personal system. If this gap becomes a concern in future, it can be mitigated by a shadow-index swap pattern, but this is not warranted now.

**Implications:**
- Re-ingestion is triggered by: a hash mismatch on a known path (detected during on-demand or nightly scan), or an explicit `POST /ingest` call for a specific file that is already in the index.
- The delete-then-ingest sequence must be atomic at the document level: all old chunks are removed before new chunks are written. Partial states (some old, some new chunks) must not persist if the re-ingestion fails midway.
- Re-ingestion failures must be logged with enough detail to diagnose. The document should be flagged as in an error state in the metadata store, not silently left half-processed.
- The document's internal ID is preserved across re-ingestion; only the chunks, embeddings, and hash are replaced.

---

### 7. Deletion Propagation

**Decision:** When a source document is removed from the watch directory, it must be removed from the index. Two mechanisms work together:

**Event-triggered deletion (primary):**
A `DELETE /documents/{id}` API endpoint removes a document immediately — deleting its entry from the metadata store, its chunks from the vector index, and its copy from the managed document store.

**Nightly reconciliation scan (secondary):**
As part of the scheduled nightly job, the system will scan all documents in the metadata store and verify that their source file still exists in the watch directory. Any document whose source file is no longer present will be automatically removed from the index. This catches deletions that occurred without an explicit API call.

**Rationale:** Given the "no answer > wrong answer" principle established in ADR-000, stale documents in the index are a real correctness risk — they can produce answers that cite sources which no longer exist or have been superseded. Deletion must propagate reliably.

The nightly reconciliation scan elegantly serves double duty: it handles both new document discovery and stale document removal in a single pass. This is simpler than running two separate jobs.

**Implications:**
- The reconciliation scan must compare the set of files currently present in the watch directories against the set of documents in the metadata store, and resolve any discrepancies (missing files → delete from index; new files → ingest).
- Deletion reconciliation must only run for a watch root after the system has confirmed that the root itself is reachable and healthy. If a watch root is missing, inaccessible, or fails abnormally during scanning, deletion reconciliation for that root is skipped and the failure is logged.
- Documents may track `last_seen_at` and `missing_since` timestamps so the system can apply a configurable grace period before automatic deletion if this proves useful in practice.
- The `DELETE /documents/{id}` endpoint requires the internal document ID. A `GET /documents` endpoint listing ingested documents with their IDs is a necessary companion.
- Deletion from the vector index must remove all chunks associated with the document, not just the metadata record. The metadata store must maintain the mapping from document ID to chunk IDs.
- Deletion is permanent and immediate. There is no soft-delete or recycle bin in this iteration.

---

### 8. Language Support

**Decision:** The system will support **English-language documents only** in this iteration.

**Rationale:** The owner's corpus is English-only. Supporting multilingual content requires selecting a multilingual embedding model, which typically has different dimensionality characteristics, may perform less well on English-only workloads, and introduces additional complexity in language detection and potentially in chunking (some languages do not use whitespace as a token boundary). None of this complexity is justified for the current use case.

**Implications:**
- Embedding model selection (addressed in a later ADR) may assume English-optimised models.
- No language detection step is required in the pre-processing pipeline.
- If multilingual support is added in future, the embedding model will likely need to change, requiring a full re-embedding of the corpus. This is an acceptable future cost.

---

### 9. Source Authentication

**Decision:** No source authentication mechanism is required. All source documents are local files on filesystems accessible to the system process or reachable via the Tailscale network. Standard operating system file permissions are the access control mechanism for source files.

**Rationale:** The system has no external data sources requiring API keys, OAuth tokens, or credentials. If remote paths on the Tailscale network are included in watch directories, they must be mounted or accessible via standard network filesystem protocols (NFS, SMB, SSHFS) at the OS level before the application sees them. Credential management for remote mounts is an infrastructure concern, not an application concern.

---

## Consequences

The decisions in this ADR establish the following constraints for downstream ADRs:

| Constraint | Effect on downstream decisions |
|---|---|
| PDF + Markdown formats, extensible | Pre-processing ADR must define parser interface and format-specific cleaning steps |
| Watch directories are authoritative; raw documents stored in managed store | Storage ADR must account for source roots, managed document copies, and vector index consistency |
| On-demand + nightly ingestion | Infrastructure ADR must account for a scheduler (cron or embedded) |
| Async ingestion jobs | API design must include job status endpoints |
| Content hashing | Metadata store must persist hashes; ingestion pipeline must compute hash as first step |
| Delete-and-re-ingest for updates | Vector store must support bulk delete by document ID |
| Nightly reconciliation for deletion | Nightly job has two responsibilities: discover new, prune deleted |
| English only | Embedding model selection unconstrained by multilingual requirements |

---

## Alternatives Considered

### File-system watcher (inotify / FSEvents)
Would provide near-instant ingestion of new files without any manual trigger. Rejected due to platform-specificity, additional persistent process complexity, and edge cases around partial writes and file locks. The on-demand API plus nightly fallback achieves the owner's needs with far simpler implementation.

### Reference-only document storage (no copy of originals)
Simpler, uses less disk space. Rejected because it creates fragility around file moves and makes re-processing impossible without re-import. For text documents, the disk cost of storing originals is negligible.

### Path-based duplicate detection
Simpler than hashing. Rejected because it fails on renamed or moved files, and cannot detect when the same content is imported from multiple locations.

### Differential re-ingestion on update
Would minimise re-processing work and eliminate the brief indexing gap during updates. Rejected because the implementation complexity is not justified at personal document volumes. Full delete-and-re-ingest is correct and straightforward.

### Soft-delete with recovery window
Would allow accidentally deleted documents to be recovered. Rejected for this iteration — the owner can re-ingest from source if needed, and the managed document store retains the original file until deletion is confirmed.

---

## Review Triggers

This ADR should be revisited if any of the following occur:

- New source types are required (web scraping, database export, API integration).
- Non-English documents are added to the corpus.
- Document volume grows to a point where nightly full-scan reconciliation is too slow.
- The owner's workflow reveals that 24-hour ingestion lag for the fallback path is not acceptable.
- Scanned PDFs with no text layer become a significant part of the corpus (triggers OCR decision).
