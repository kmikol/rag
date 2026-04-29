import os
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from ingestion_worker.pipeline import run_next_job
from shared.config import get_settings
from shared.db import chunks
from shared.repository import MetadataRepository, create_metadata_engine

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_doc.md"


def test_rag_pipeline_end_to_end() -> None:
    """Exercise and document the full RAG path through production boundaries.

    The current Compose stack uses Google AI Studio as the model provider, but
    the system flow is provider-neutral. The fixture is synthetic and contains
    no personal information.
    """
    # ---------------------------------------------------------------------
    # 1. Bootstrapping the temporary E2E environment
    # ---------------------------------------------------------------------
    #
    # `docker-compose.e2e.yml` starts real PostgreSQL, Qdrant, api-service,
    # embedding-service, and ingestion-worker containers. The pytest process
    # runs in its own container on the same Compose network. This test applies
    # migrations explicitly because the database volume is created from scratch
    # for every `make test.e2e` run.
    missing = [
        name
        for name in ("GEMINI_API_KEY_E2E_TEST", "API_SERVICE_URL", "RAG_API_KEY")
        if not os.environ.get(name)
    ]
    assert not missing, f"Missing required E2E env vars: {', '.join(missing)}"

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")
    get_settings.cache_clear()

    api_url = os.environ["API_SERVICE_URL"]
    headers = {"Authorization": f"Bearer {os.environ['RAG_API_KEY']}"}
    _wait_for_api(api_url)

    # ---------------------------------------------------------------------
    # 2. Empty-corpus answerability check
    # ---------------------------------------------------------------------
    #
    # Chat always runs retrieval before generation. With an empty temporary
    # corpus, retrieval returns no usable chunks, so `/chat` must refuse before
    # it calls the configured LLM backend. This verifies the "no answer is
    # better than an ungrounded answer" behavior at the external API boundary.
    weak_chat_response = httpx.post(
        f"{api_url}/chat",
        headers=headers,
        json={"query": "What color is the fictional marker?", "limit": 3},
        timeout=30,
    )

    assert weak_chat_response.status_code == 200, weak_chat_response.text

    weak_chat_body = weak_chat_response.json()
    assert weak_chat_body["refused"] is True
    assert weak_chat_body["answer"] is None

    # ---------------------------------------------------------------------
    # 3. Place a source document in the authoritative watch root
    # ---------------------------------------------------------------------
    #
    # Watch roots are the source of truth for corpus membership. The test copies
    # a longer synthetic Markdown document into the E2E watch volume. It does
    # not write directly to PostgreSQL or Qdrant; those stores must be populated
    # by the same ingestion path used in real deployments.
    watch_root = Path(os.environ["WATCH_ROOTS"])
    watch_root.mkdir(parents=True, exist_ok=True)
    source = watch_root / "test_doc.md"
    source.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    assert source.exists()
    assert "cobalt blue" in source.read_text(encoding="utf-8").lower()

    # ---------------------------------------------------------------------
    # 4. Create an ingestion job through api-service
    # ---------------------------------------------------------------------
    #
    # The public API does not ingest files inline. It creates an ingestion job
    # in PostgreSQL and returns quickly. The worker is responsible for claiming
    # and processing that job. Passing `requested_path` keeps this E2E focused
    # on one known fixture rather than a full watch-root scan.
    ingest_response = httpx.post(
        f"{api_url}/ingest",
        headers=headers,
        json={"requested_path": str(source)},
        timeout=30,
    )

    assert ingest_response.status_code == 201, ingest_response.text

    ingest_body = ingest_response.json()
    assert ingest_body["status"] == "pending"
    assert ingest_body["requested_path"] == str(source)

    # ---------------------------------------------------------------------
    # 5. Process the job through the ingestion worker
    # ---------------------------------------------------------------------
    #
    # `run_next_job()` is the worker's one-shot entry point. It claims the
    # pending job, parses Markdown, chunks by document structure, calls
    # embedding-service for chunk vectors, writes document/version/chunk metadata
    # to PostgreSQL, stores a managed copy, and upserts vectors to Qdrant.
    worker_result = run_next_job(worker_id="e2e-worker")

    assert worker_result.status == "active"
    assert worker_result.processed_items == 1

    # ---------------------------------------------------------------------
    # 6. Verify persisted ingestion state in PostgreSQL
    # ---------------------------------------------------------------------
    #
    # This checks that ingestion did more than return success. The document and
    # active version must be marked active, and the fixture must produce at least
    # five stored chunks. That proves the parser/chunker/repository path ran
    # against the temporary test database.
    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        document_rows = [
            row
            for row in repository.list_documents()
            if row["document"]["source_path"] == str(source)
        ]

        assert len(document_rows) == 1

        document = document_rows[0]["document"]
        active_version = document_rows[0]["active_version"]

        assert document["state"] == "active"
        assert active_version is not None
        assert active_version["state"] == "active"

        chunk_count = connection.execute(
            select(func.count())
            .select_from(chunks)
            .where(chunks.c.document_version_id == active_version["id"])
        ).scalar_one()

        assert chunk_count >= 5

    # ---------------------------------------------------------------------
    # 7. Search the indexed corpus through api-service
    # ---------------------------------------------------------------------
    #
    # `/search` embeds the user query through embedding-service, searches Qdrant
    # for nearby vectors, loads active chunk metadata from PostgreSQL, and
    # returns citation-ready results. The top result should contain the known
    # synthetic fact from the fixture.
    search_response = httpx.post(
        f"{api_url}/search",
        headers=headers,
        json={"query": "What color is the calibration marker?", "limit": 3},
        timeout=60,
    )

    assert search_response.status_code == 200, search_response.text

    search_body = search_response.json()
    assert search_body["results"]
    assert "cobalt blue" in search_body["results"][0]["text"].lower()

    # ---------------------------------------------------------------------
    # 8. Generate a grounded answer through `/chat`
    # ---------------------------------------------------------------------
    #
    # `/chat` repeats retrieval internally, applies answerability gates, builds a
    # bounded context prompt from the selected chunks, and calls the configured
    # LLM provider. The response must include a non-refused answer and citations,
    # proving that generation was grounded in retrieved evidence.
    chat_response = httpx.post(
        f"{api_url}/chat",
        headers=headers,
        json={"query": "What color is the calibration marker?", "limit": 3},
        timeout=240,
    )

    assert chat_response.status_code == 200, chat_response.text

    chat_body = chat_response.json()
    assert chat_body["refused"] is False
    assert chat_body["citations"]

    answer = chat_body["answer"].lower()

    assert "cobalt" in answer
    assert "blue" in answer


def _wait_for_api(api_url: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{api_url}/health", timeout=5)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise AssertionError("api-service did not become healthy")
