# Ingestion Worker

The `ingestion-worker` owns background document processing.

## Purpose

The worker claims ingestion jobs, scans configured watch roots, reconciles the index against the filesystem source of truth, parses supported files, chunks text, calls `embedding-service`, and writes metadata/vectors/document copies.

The current implementation exposes the health endpoint plus filesystem scanning,
managed-copy, parser, and chunker building blocks. Job claiming, embedding calls,
indexing, and PostgreSQL writes are intentionally outside this module slice.

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

## API Contract

Implemented:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Service health check |

The worker is primarily job-driven through PostgreSQL-backed job records, not an external public API.

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
