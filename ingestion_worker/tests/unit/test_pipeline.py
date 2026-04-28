from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from ingestion_worker.parsing import BaseDocumentParser, ParsedDocument, ParserRegistry
from ingestion_worker.pipeline import (
    BatchEmbeddingResult,
    EmbeddingModelInfo,
    process_next_job,
    run_next_job,
)
from shared.config import AppSettings
from shared.db import chunks, metadata
from shared.repository import MetadataRepository
from shared.vector_index import ChunkVector


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.embedded_texts: list[str] = []
        self.model_info_calls = 0

    def model_info(self) -> EmbeddingModelInfo:
        self.model_info_calls += 1
        return EmbeddingModelInfo(model_name="fake-model", dimension=3)

    def embed_batch(self, texts: list[str]) -> BatchEmbeddingResult:
        self.embedded_texts.extend(texts)
        return BatchEmbeddingResult(
            embeddings=[[float(index + 1), 0.0, 0.0] for index, _ in enumerate(texts)],
            model_name="fake-model",
            dimension=3,
        )


class FakeVectorIndex:
    def __init__(self) -> None:
        self.dimension: int | None = None
        self.ensure_calls: list[int] = []
        self.vectors: list[ChunkVector] = []

    def ensure_collection(self, dimension: int) -> None:
        self.dimension = dimension
        self.ensure_calls.append(dimension)

    def upsert_chunks(self, chunks: list[ChunkVector]) -> None:
        self.vectors.extend(chunks)


class RaisingParser(BaseDocumentParser):
    content_type = "text/markdown"

    def parse(self, path: Path) -> ParsedDocument:
        raise ValueError(f"parse failed for {path}")


def make_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        POSTGRES_URL="sqlite+pysqlite:///:memory:",
        QDRANT_URL="http://qdrant:6333",
        EMBEDDING_SERVICE_URL="http://embedding-service:8000",
        WATCH_ROOTS=str(tmp_path / "watch"),
        DOCUMENT_STORE_PATH=str(tmp_path / "documents"),
    )


def make_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    return engine


def test_process_next_job_returns_false_when_no_job(tmp_path: Path) -> None:
    engine = make_engine()

    processed = process_next_job(
        worker_id="unit-worker",
        settings=make_settings(tmp_path),
        engine=engine,
        embedding_client=FakeEmbeddingClient(),
        vector_index=FakeVectorIndex(),
    )

    assert processed is False


def test_run_next_job_builds_default_vector_index_from_explicit_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    created_indexes: list[object] = []

    class RecordingVectorIndex(FakeVectorIndex):
        def __init__(self, url: str | None = None, collection_name: str | None = None):
            super().__init__()
            self.url = url
            self.collection_name = collection_name
            created_indexes.append(self)

    settings = make_settings(tmp_path)
    settings.qdrant_url = "http://explicit-qdrant:6333"
    settings.qdrant_collection = "explicit_chunks"
    monkeypatch.setattr("ingestion_worker.pipeline.QdrantVectorIndex", RecordingVectorIndex)

    result = run_next_job(
        worker_id="unit-worker",
        settings=settings,
        engine=make_engine(),
        embedding_client=FakeEmbeddingClient(),
    )

    assert result.claimed is False
    assert len(created_indexes) == 1
    created_index = created_indexes[0]
    assert isinstance(created_index, RecordingVectorIndex)
    assert created_index.url == "http://explicit-qdrant:6333"
    assert created_index.collection_name == "explicit_chunks"


def test_process_next_job_ingests_requested_markdown(tmp_path: Path) -> None:
    engine = make_engine()
    source = tmp_path / "notes.md"
    source.write_text("# Title\n\nAlpha beta gamma.", encoding="utf-8")
    embedding_client = FakeEmbeddingClient()
    vector_index = FakeVectorIndex()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        job = repository.create_ingestion_job(str(source))

    processed = process_next_job(
        worker_id="unit-worker",
        settings=make_settings(tmp_path),
        engine=engine,
        embedding_client=embedding_client,
        vector_index=vector_index,
    )

    assert processed is True
    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        updated_job = repository.get_ingestion_job(job["id"])
        documents = repository.list_documents()
        persisted_chunks = connection.execute(select(chunks)).mappings().all()

    assert updated_job["status"] == "active"
    assert updated_job["processed_items"] == 1
    assert documents[0]["document"]["state"] == "active"
    assert documents[0]["active_version"]["embedding_model_name"] == "fake-model"
    assert documents[0]["active_version"]["embedding_dimension"] == 3
    assert persisted_chunks[0]["text"] == "Alpha beta gamma."
    assert embedding_client.embedded_texts == ["Alpha beta gamma."]
    assert embedding_client.model_info_calls == 1
    assert vector_index.dimension == 3
    assert vector_index.ensure_calls == [3]
    assert len(vector_index.vectors) == 1


def test_process_next_job_full_scan_caches_model_info_and_collection_setup(
    tmp_path: Path,
) -> None:
    engine = make_engine()
    watch_root = tmp_path / "watch"
    watch_root.mkdir()
    first = watch_root / "first.md"
    second = watch_root / "second.md"
    first.write_text("# First\n\nAlpha content.", encoding="utf-8")
    second.write_text("# Second\n\nBeta content.", encoding="utf-8")
    embedding_client = FakeEmbeddingClient()
    vector_index = FakeVectorIndex()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        job = repository.create_ingestion_job()

    processed = process_next_job(
        worker_id="unit-worker",
        settings=make_settings(tmp_path),
        engine=engine,
        embedding_client=embedding_client,
        vector_index=vector_index,
    )

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        updated_job = repository.get_ingestion_job(job["id"])
        documents = repository.list_documents()

    assert processed is True
    assert updated_job["status"] == "active"
    assert updated_job["processed_items"] == 2
    assert len(documents) == 2
    assert embedding_client.model_info_calls == 1
    assert embedding_client.embedded_texts == ["Alpha content.", "Beta content."]
    assert vector_index.ensure_calls == [3]
    assert len(vector_index.vectors) == 2


def test_process_next_job_skips_duplicate_content_hash(tmp_path: Path) -> None:
    engine = make_engine()
    source = tmp_path / "notes.md"
    source.write_text("duplicate content", encoding="utf-8")
    embedding_client = FakeEmbeddingClient()
    vector_index = FakeVectorIndex()

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document = repository.get_or_create_document("/watch/existing.md")
        repository.create_document_version(
            document["id"],
            "b79f8c07798dcc75d6f288e6a620644a88a9c67e74019a57b88a5bfd918e4b0f",
        )
        job = repository.create_ingestion_job(str(source))

    process_next_job(
        worker_id="unit-worker",
        settings=make_settings(tmp_path),
        engine=engine,
        embedding_client=embedding_client,
        vector_index=vector_index,
    )

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        updated_job = repository.get_ingestion_job(job["id"])
        documents = repository.list_documents()

    assert updated_job["status"] == "active"
    assert updated_job["processed_items"] == 1
    assert len(documents) == 1
    assert embedding_client.embedded_texts == []
    assert vector_index.vectors == []


def test_process_next_job_fails_missing_requested_path(tmp_path: Path) -> None:
    engine = make_engine()
    missing = tmp_path / "missing.md"

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        job = repository.create_ingestion_job(str(missing))

    process_next_job(
        worker_id="unit-worker",
        settings=make_settings(tmp_path),
        engine=engine,
        embedding_client=FakeEmbeddingClient(),
        vector_index=FakeVectorIndex(),
    )

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        updated_job = repository.get_ingestion_job(job["id"])

    assert updated_job["status"] == "failed"
    assert f"Requested path does not exist: {missing}" in updated_job["error_message"]


def test_process_next_job_marks_job_and_version_failed_on_parser_error(tmp_path: Path) -> None:
    engine = make_engine()
    source = tmp_path / "notes.md"
    source.write_text("# Title\n\nText", encoding="utf-8")
    parser_registry = ParserRegistry()
    parser_registry.register(".md", RaisingParser())

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        job = repository.create_ingestion_job(str(source))

    process_next_job(
        worker_id="unit-worker",
        settings=make_settings(tmp_path),
        engine=engine,
        embedding_client=FakeEmbeddingClient(),
        vector_index=FakeVectorIndex(),
        parser_registry=parser_registry,
    )

    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        updated_job = repository.get_ingestion_job(job["id"])
        listed = repository.list_documents()

    assert updated_job["status"] == "failed"
    assert "parse failed for" in updated_job["error_message"]
    assert listed[0]["document"]["state"] == "failed"
    assert listed[0]["active_version"] is None
