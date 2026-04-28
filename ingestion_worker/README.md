# Ingestion Worker

The `ingestion-worker` owns background document processing.

## Purpose

The worker claims ingestion jobs, scans configured watch roots, reconciles the index against the filesystem source of truth, parses supported files, chunks text, calls `embedding-service`, and writes metadata/vectors/document copies.

The current implementation exposes the health endpoint plus a one-shot worker
pipeline for processing pending PostgreSQL ingestion jobs.

## Responsibilities

- Dispatch supported source files through a parser registry.
- Discover supported files under configured watch roots.
- Skip hidden files and directories during scans by default.
- Follow symlinks during scans with cycle protection.
- Compute SHA-256 hashes from raw source bytes.
- Copy originals into a hash-addressed managed document store.
- Parse Markdown files (`.md`, `.markdown`) into normalized sections with heading paths.
- Parse PDF files (`.pdf`) into normalized page/paragraph sections.
- Detect PDFs with no extractable text layer by raising `EmptyScannedPdfError`.
- Skip unsupported file formats gracefully by returning `None` from the registry.
- Chunk parsed sections without crossing parser-provided structure boundaries.
- Preserve citation metadata on chunks: source path, filename, Markdown heading path, PDF page number, section title, and character offsets where available.
- Claim pending ingestion jobs with PostgreSQL row locking.
- Process full-scan and single-path ingestion jobs once per worker invocation.
- Call `embedding-service` for batch document embeddings.
- Persist documents, versions, chunks, job state, and embedding metadata in PostgreSQL.
- Upsert chunk vectors into Qdrant after chunk metadata is persisted.
- Skip duplicate raw-byte content hashes without creating another document version.

## API Contract

Implemented:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |

The worker is primarily job-driven through PostgreSQL-backed job records, not an external public API.

## Worker Pipeline Contract

`ingestion_worker.pipeline` provides:

- `process_next_job()`: claims and processes the oldest pending ingestion job,
  returning `True` when a job was claimed and `False` when no pending job exists.
- `process_pending_jobs_once()`: one-shot wrapper for manual runs and tests.
- `run_next_job()` and `run_pending_job_once()`: structured-result variants
  used by automation and the CLI.
- `HttpEmbeddingClient`: minimal client for `GET /model-info` and
  `POST /embed/batch` on `embedding-service`.

The CLI entrypoint is:

```bash
python -m ingestion_worker.worker
```

Each invocation processes at most one job and exits. It does not start a polling
loop or scheduler. Pass `--fail-on-error` when automation should receive a
non-zero exit code for a claimed job that ends in `failed`; an idle run with no
pending job still exits successfully.

Job status progresses through the persisted ADR-005 lifecycle states. A document
version is marked active only after Qdrant upsert succeeds. Hard failures mark
the job failed with an error message and mark any in-progress document/version
failed for inspection.

## Filesystem Contract

`ingestion_worker.filesystem` provides:

- `parse_watch_roots()`: parses `WATCH_ROOTS` as an `os.pathsep`-separated
  path list.
- `scan_watch_roots()`: recursively discovers parser-supported files and
  reports missing or unhealthy roots separately.
- `compute_sha256()`: hashes raw source bytes.
- `copy_to_managed_store()`: copies originals into
  `<DOCUMENT_STORE_PATH>/<first-two-hash-chars>/<sha256><lowercase-suffix>`.

Scans skip dot-prefixed files and directories by default. Symlinks are followed,
and resolved directories/files are tracked so cycles and duplicate discoveries do
not repeat work. Unhealthy roots are reported in the scan result; deletion
reconciliation is intentionally out of scope for this module slice.

Managed-copy hashes must be 64-character SHA-256 hex digests. Hash values are
normalized to lowercase before path construction, existing managed copies are
verified before reuse, and new copies are written through a temporary file before
being atomically moved into place.

## Parser Contract

`ingestion_worker.parsing` provides:

- `BaseDocumentParser`: parser interface for file-to-section normalization.
- `MarkdownDocumentParser`: Markdown parser that preserves heading hierarchy.
- `PdfDocumentParser`: PDF parser that preserves page numbers and detects empty/scanned PDFs.
- `ParserRegistry`: extension-based parser dispatch.
- `default_parser_registry()`: registers `.md`, `.markdown`, and `.pdf`.

Parsers return `ParsedDocument` values containing `DocumentSection` entries. Each section includes source metadata and any format-specific citation context available to the parser.

## Chunking Contract

`ingestion_worker.chunking` provides `StructureAwareChunker`.

The chunker accepts a `ParsedDocument`, keeps chunks inside parser section boundaries, approximates token counts deterministically with a word/punctuation tokenizer, and applies configurable target and overlap token counts. Defaults are 500 target tokens and 75 overlap tokens, matching ADR-006's 300-600 token target and 50-100 token overlap range.

## Configuration

- `POSTGRES_URL`
- `QDRANT_URL`
- `EMBEDDING_SERVICE_URL`
- `WATCH_ROOTS` (`os.pathsep`-separated when multiple roots are configured)
- `DOCUMENT_STORE_PATH`

## Related ADRs

- [ADR 001: Data Sources and Ingestion](../adr/001-data-sources-and-ingestion.md)
- [ADR 005: Document Identity and Ingestion State](../adr/005-document-identity-and-ingestion-state.md)
- [ADR 006: Chunking Strategy](../adr/006-chunking-strategy.md)
- [ADR 008: Job Coordination and Service Contracts](../adr/008-job-coordination-and-service-contracts.md)

## Testing Helpers

No parser-specific testing helpers are currently exposed. Unit tests live under `ingestion_worker/tests/unit/`.
