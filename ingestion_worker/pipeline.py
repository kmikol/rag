from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib import error, request
from uuid import uuid4

from sqlalchemy.engine import Engine

from ingestion_worker.chunking import DocumentChunk, StructureAwareChunker
from ingestion_worker.filesystem import (
    UnhealthyWatchRoot,
    compute_sha256,
    copy_to_managed_store,
    parse_watch_roots,
    scan_watch_roots,
)
from ingestion_worker.parsing import ParserRegistry, default_parser_registry
from shared.config import AppSettings, get_settings
from shared.file_cleanup import (
    delete_unique_files,
    is_path_under_roots,
    resolve_path,
    validate_file_cleanup_targets,
    validate_path_under_root,
)
from shared.repository import ChunkRecord, MetadataRepository, create_metadata_engine
from shared.vector_index import ChunkVector, QdrantVectorIndex

logger = logging.getLogger(__name__)


class IngestionPipelineError(RuntimeError):
    """Raised when a claimed ingestion job cannot be completed."""


@dataclass(frozen=True)
class EmbeddingModelInfo:
    """Embedding model identity returned by `embedding-service`."""

    embedding_model_name: str
    dimension: int


@dataclass(frozen=True)
class BatchEmbeddingResult:
    """Batch embedding response used by the ingestion pipeline."""

    embeddings: list[list[float]]
    embedding_model_name: str
    dimension: int


@dataclass(frozen=True)
class IngestionRunResult:
    """Structured outcome for one worker invocation."""

    claimed: bool
    status: str
    job_id: str | None = None
    processed_items: int = 0
    error_message: str | None = None


@dataclass
class IngestionJobContext:
    """Per-job cache for stable service metadata and index setup."""

    embedding_client: EmbeddingClient
    vector_index: VectorIndex
    model_info: EmbeddingModelInfo | None = None
    ensured_dimensions: set[int] | None = None

    def get_model_info(self) -> EmbeddingModelInfo:
        """Fetch embedding model info at most once for a claimed job."""
        if self.model_info is None:
            self.model_info = self.embedding_client.model_info()
        return self.model_info

    def ensure_collection(self, dimension: int) -> None:
        """Ensure the vector collection once for each dimension in this job."""
        if self.ensured_dimensions is None:
            self.ensured_dimensions = set()
        if dimension in self.ensured_dimensions:
            return
        self.vector_index.ensure_collection(dimension)
        self.ensured_dimensions.add(dimension)


class EmbeddingClient(Protocol):
    def model_info(self) -> EmbeddingModelInfo:
        """Return the currently configured embedding model identity."""

    def embed_batch(self, texts: list[str]) -> BatchEmbeddingResult:
        """Embed one or more chunk texts."""


class VectorIndex(Protocol):
    def ensure_collection(self, dimension: int) -> None:
        """Create or verify the vector collection for the embedding dimension."""

    def upsert_chunks(self, chunks: list[ChunkVector]) -> None:
        """Persist chunk vectors to the vector index."""

    def delete_by_document_id(self, document_id: str) -> None:
        """Remove all vectors belonging to one logical document."""


class HttpEmbeddingClient:
    """Small HTTP client for the embedding-service API."""

    def __init__(self, base_url: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def model_info(self) -> EmbeddingModelInfo:
        """Fetch model identity from `GET /model-info`."""
        body = self._request("GET", "/model-info")
        return EmbeddingModelInfo(
            embedding_model_name=_required_str(body, "embedding_model_name"),
            dimension=_required_int(body, "dimension"),
        )

    def embed_batch(self, texts: list[str]) -> BatchEmbeddingResult:
        """Embed chunk text through `POST /embed/batch`."""
        body = self._request("POST", "/embed/batch", {"texts": texts})
        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list) or not all(
            isinstance(vector, list) for vector in embeddings
        ):
            raise IngestionPipelineError("Embedding service returned invalid embeddings.")
        if len(embeddings) != len(texts):
            raise IngestionPipelineError("Embedding service returned the wrong embedding count.")

        return BatchEmbeddingResult(
            embeddings=[[float(value) for value in vector] for vector in embeddings],
            embedding_model_name=_required_str(body, "embedding_model_name"),
            dimension=_required_int(body, "dimension"),
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise IngestionPipelineError(f"Embedding service HTTP error: {detail}") from exc
        except error.URLError as exc:
            raise IngestionPipelineError(f"Embedding service unavailable: {exc.reason}") from exc

        if not isinstance(body, dict):
            raise IngestionPipelineError("Embedding service returned a non-object response.")
        return body


def process_pending_jobs_once(worker_id: str | None = None) -> bool:
    """Process at most one pending ingestion job."""
    return process_next_job(worker_id=worker_id)


def run_pending_job_once(worker_id: str | None = None) -> IngestionRunResult:
    """Process at most one pending ingestion job and return its outcome."""
    return run_next_job(worker_id=worker_id)


def process_next_job(
    worker_id: str | None = None,
    settings: AppSettings | None = None,
    engine: Engine | None = None,
    embedding_client: EmbeddingClient | None = None,
    vector_index: VectorIndex | None = None,
    parser_registry: ParserRegistry | None = None,
    chunker: StructureAwareChunker | None = None,
) -> bool:
    """Claim and process the oldest pending ingestion job, if one exists."""
    return run_next_job(
        worker_id=worker_id,
        settings=settings,
        engine=engine,
        embedding_client=embedding_client,
        vector_index=vector_index,
        parser_registry=parser_registry,
        chunker=chunker,
    ).claimed


def run_next_job(
    worker_id: str | None = None,
    settings: AppSettings | None = None,
    engine: Engine | None = None,
    embedding_client: EmbeddingClient | None = None,
    vector_index: VectorIndex | None = None,
    parser_registry: ParserRegistry | None = None,
    chunker: StructureAwareChunker | None = None,
) -> IngestionRunResult:
    """Claim and process the oldest pending ingestion job, returning its outcome."""
    resolved_settings = settings or get_settings()
    resolved_engine = engine or create_metadata_engine(resolved_settings.postgres_url)
    resolved_embedding_client = embedding_client or HttpEmbeddingClient(
        resolved_settings.embedding_service_url
    )
    resolved_vector_index = vector_index or QdrantVectorIndex(
        url=resolved_settings.qdrant_url,
        collection_name=resolved_settings.qdrant_collection,
    )
    resolved_parser_registry = parser_registry or default_parser_registry()
    resolved_chunker = chunker or StructureAwareChunker()
    resolved_worker_id = worker_id or _default_worker_id()

    with resolved_engine.begin() as connection:
        repository = MetadataRepository(connection)
        job = repository.claim_next_ingestion_job(resolved_worker_id)
        if job is None:
            return IngestionRunResult(claimed=False, status="idle")

        try:
            processed_items = _process_claimed_job(
                repository=repository,
                job=job,
                settings=resolved_settings,
                context=IngestionJobContext(
                    embedding_client=resolved_embedding_client,
                    vector_index=resolved_vector_index,
                ),
                parser_registry=resolved_parser_registry,
                chunker=resolved_chunker,
            )
        except Exception as exc:
            failed_job = _mark_job_failed(repository, str(job["id"]), str(exc))
            return IngestionRunResult(
                claimed=True,
                status="failed",
                job_id=str(job["id"]),
                processed_items=_required_int(failed_job, "processed_items"),
                error_message=str(failed_job["error_message"]),
            )
        else:
            completed_job = repository.update_ingestion_job(job["id"], "active", processed_items)
            return IngestionRunResult(
                claimed=True,
                status="active",
                job_id=str(completed_job["id"]),
                processed_items=int(completed_job["processed_items"]),
            )

    raise RuntimeError("unreachable")


def _process_claimed_job(
    repository: MetadataRepository,
    job: dict[str, object],
    settings: AppSettings,
    context: IngestionJobContext,
    parser_registry: ParserRegistry,
    chunker: StructureAwareChunker,
) -> int:
    requested_path = job.get("requested_path")
    if requested_path:
        source_paths = [
            _validate_requested_path(Path(str(requested_path)).expanduser(), parser_registry)
        ]
        return _process_source_paths(
            repository=repository,
            job=job,
            source_paths=source_paths,
            settings=settings,
            context=context,
            parser_registry=parser_registry,
            chunker=chunker,
        )

    watch_roots = parse_watch_roots(settings.watch_roots)
    scan_result = scan_watch_roots(watch_roots, parser_registry)
    for unhealthy_root in scan_result.unhealthy_roots:
        logger.warning(
            "Skipping deletion reconciliation for unhealthy watch root %s: %s",
            unhealthy_root.root_path,
            unhealthy_root.reason,
        )
    processed_items = _reconcile_missing_source_files(
        repository=repository,
        settings=settings,
        vector_index=context.vector_index,
        healthy_roots=_healthy_roots(watch_roots, scan_result.unhealthy_roots),
    )
    if processed_items:
        repository.update_ingestion_job(str(job["id"]), "running", processed_items)

    return processed_items + _process_source_paths(
        repository=repository,
        job=job,
        source_paths=[discovered.source_path for discovered in scan_result.files],
        settings=settings,
        context=context,
        parser_registry=parser_registry,
        chunker=chunker,
        initial_processed_items=processed_items,
    )


def _process_source_paths(
    repository: MetadataRepository,
    job: dict[str, object],
    source_paths: list[Path],
    settings: AppSettings,
    context: IngestionJobContext,
    parser_registry: ParserRegistry,
    chunker: StructureAwareChunker,
    initial_processed_items: int = 0,
) -> int:
    processed_items = 0
    for source_path in source_paths:
        _process_source_path(
            repository=repository,
            job_id=str(job["id"]),
            source_path=source_path,
            settings=settings,
            context=context,
            parser_registry=parser_registry,
            chunker=chunker,
        )
        processed_items += 1
        repository.update_ingestion_job(
            str(job["id"]),
            "running",
            initial_processed_items + processed_items,
        )
    return processed_items


def _reconcile_missing_source_files(
    repository: MetadataRepository,
    settings: AppSettings,
    vector_index: VectorIndex,
    healthy_roots: tuple[Path, ...],
) -> int:
    if not healthy_roots:
        return 0

    reconciled = 0
    document_store_root = Path(settings.document_store_path).expanduser()
    for row in repository.list_documents():
        document = row["document"]
        active_version = row["active_version"]
        if active_version is None or document["state"] != "active":
            continue

        source_path = Path(str(document["source_path"])).expanduser()
        if not is_path_under_roots(source_path, healthy_roots):
            continue
        if source_path.exists():
            continue

        deletion_target = repository.get_document_deletion_target(str(document["id"]))
        if deletion_target is None:
            continue

        managed_files = [
            validate_path_under_root(path, document_store_root)
            for path in deletion_target["managed_store_paths"]
        ]
        validate_file_cleanup_targets(managed_files)

        vector_index.delete_by_document_id(str(document["id"]))
        delete_unique_files(managed_files)
        repository.delete_document(str(document["id"]))
        reconciled += 1

    return reconciled


def _healthy_roots(
    roots: tuple[Path, ...],
    unhealthy_roots: tuple[UnhealthyWatchRoot, ...],
) -> tuple[Path, ...]:
    unhealthy = {resolve_path(root.root_path) for root in unhealthy_roots}
    return tuple(root for root in roots if resolve_path(root) not in unhealthy)


def _validate_requested_path(source_path: Path, parser_registry: ParserRegistry) -> Path:
    if not source_path.exists():
        raise IngestionPipelineError(f"Requested path does not exist: {source_path}")
    if not source_path.is_file():
        raise IngestionPipelineError(f"Requested path is not a file: {source_path}")
    if parser_registry.get_parser(source_path) is None:
        raise IngestionPipelineError(f"Unsupported document format: {source_path}")
    return source_path


def _process_source_path(
    repository: MetadataRepository,
    job_id: str,
    source_path: Path,
    settings: AppSettings,
    context: IngestionJobContext,
    parser_registry: ParserRegistry,
    chunker: StructureAwareChunker,
) -> None:
    content_hash = compute_sha256(source_path)
    if repository.find_document_version_by_hash(content_hash) is not None:
        return

    document_version_id: str | None = None
    document_id: str | None = None
    try:
        document = repository.get_or_create_document(str(source_path))
        document_id = str(document["id"])
        repository.update_document_state(document_id, "running")

        managed_copy = copy_to_managed_store(
            source_path,
            content_hash,
            Path(settings.document_store_path),
        )
        version = repository.create_document_version(
            document_id,
            content_hash,
            str(managed_copy.managed_path),
        )
        document_version_id = str(version["id"])
        repository.update_document_version_state(document_version_id, "copied")
        repository.update_ingestion_job(job_id, "copied")

        parsed_document = parser_registry.parse(source_path)
        if parsed_document is None:
            raise IngestionPipelineError(f"Unsupported document format: {source_path}")
        repository.update_document_version_state(document_version_id, "parsed")
        repository.update_ingestion_job(job_id, "parsed")

        chunks = chunker.chunk(parsed_document)
        if not chunks:
            raise IngestionPipelineError(f"No chunkable text found: {source_path}")
        repository.update_document_version_state(document_version_id, "chunked")
        repository.update_ingestion_job(job_id, "chunked")

        model_info = context.get_model_info()
        embedding_result = context.embedding_client.embed_batch([chunk.text for chunk in chunks])
        if embedding_result.dimension != model_info.dimension:
            raise IngestionPipelineError(
                "Embedding service model-info dimension does not match batch response."
            )
        repository.update_document_version_state(
            document_version_id,
            "embedded",
            embedding_model_name=embedding_result.embedding_model_name,
            embedding_dimension=embedding_result.dimension,
        )
        repository.update_ingestion_job(job_id, "embedded")

        persisted_chunks = repository.create_chunks(
            document_id,
            document_version_id,
            [_chunk_record(chunk) for chunk in chunks],
        )
        context.ensure_collection(embedding_result.dimension)
        context.vector_index.upsert_chunks(
            [
                ChunkVector(
                    chunk_id=str(chunk_record["id"]),
                    document_id=document_id,
                    document_version_id=document_version_id,
                    vector=embedding,
                    text=str(chunk_record["text"]),
                )
                for chunk_record, embedding in zip(
                    persisted_chunks,
                    embedding_result.embeddings,
                    strict=True,
                )
            ]
        )
        repository.update_document_version_state(document_version_id, "indexed")
        repository.update_ingestion_job(job_id, "indexed")

        repository.mark_document_version_active(document_version_id)
    except Exception as exc:
        if document_version_id is not None:
            repository.update_document_version_state(
                document_version_id,
                "failed",
                error_message=str(exc),
            )
        if document_id is not None:
            repository.update_document_state(document_id, "failed")
        raise IngestionPipelineError(f"Failed to ingest {source_path}: {exc}") from exc


def _chunk_record(chunk: DocumentChunk) -> ChunkRecord:
    return ChunkRecord(
        text=chunk.text,
        source_path=chunk.source_path,
        original_filename=chunk.filename,
        page_number=chunk.page_number,
        heading_path=list(chunk.heading_path) if chunk.heading_path else None,
        section_title=chunk.section_title,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        token_count=chunk.token_count,
    )


def _mark_job_failed(
    repository: MetadataRepository,
    job_id: str,
    message: str,
) -> dict[str, object]:
    return repository.update_ingestion_job(job_id, "failed", error_message=message)


def _required_str(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise IngestionPipelineError(f"Embedding service response missing '{key}'.")
    return value


def _required_int(body: dict[str, object], key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int):
        raise IngestionPipelineError(f"Embedding service response missing '{key}'.")
    return value


def _default_worker_id() -> str:
    return f"{socket.gethostname()}-{uuid4()}"
