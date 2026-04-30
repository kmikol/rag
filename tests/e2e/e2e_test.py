import os
import time
from pathlib import Path
from typing import Any

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from ingestion_worker.pipeline import run_next_job
from shared.config import get_settings
from shared.db import chunks
from shared.repository import MetadataRepository, create_metadata_engine

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_doc.md"
SECOND_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "orbital-seed-catalog.md"
MARKER_QUERY = "What color is the calibration marker?"
BEACON_QUERY = "What is the seed catalog recovery tone?"


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

    empty_marker_search = _search(api_url, headers, MARKER_QUERY)
    empty_beacon_search = _search(api_url, headers, BEACON_QUERY)

    assert empty_marker_search["results"] == []
    assert empty_beacon_search["results"] == []

    # ---------------------------------------------------------------------
    # 3. Place source documents in the authoritative watch root
    # ---------------------------------------------------------------------
    #
    # Watch roots are the source of truth for corpus membership. The test copies
    # two synthetic Markdown documents into the E2E watch volume. It does not
    # write directly to PostgreSQL or Qdrant; those stores must be populated by
    # the same ingestion path used in real deployments.
    watch_root = Path(os.environ["WATCH_ROOTS"])
    watch_root.mkdir(parents=True, exist_ok=True)
    source = watch_root / "test_doc.md"
    second_source = watch_root / "orbital-seed-catalog.md"
    source.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    second_source.write_text(SECOND_FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    assert source.exists()
    assert second_source.exists()
    assert "cobalt blue" in source.read_text(encoding="utf-8").lower()
    assert "silver chime" in second_source.read_text(encoding="utf-8").lower()

    # ---------------------------------------------------------------------
    # 4. Create ingestion jobs through api-service
    # ---------------------------------------------------------------------
    #
    # The public API does not ingest files inline. It creates an ingestion job
    # in PostgreSQL and returns quickly. The worker is responsible for claiming
    # and processing that job. Passing `requested_path` keeps this E2E focused
    # on known fixtures rather than a full watch-root scan.
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

    second_ingest_response = httpx.post(
        f"{api_url}/ingest",
        headers=headers,
        json={"requested_path": str(second_source)},
        timeout=30,
    )

    assert second_ingest_response.status_code == 201, second_ingest_response.text

    second_ingest_body = second_ingest_response.json()
    assert second_ingest_body["status"] == "pending"
    assert second_ingest_body["requested_path"] == str(second_source)

    # ---------------------------------------------------------------------
    # 5. Process the jobs through the ingestion worker
    # ---------------------------------------------------------------------
    #
    # `run_next_job()` is the worker's one-shot entry point. It claims the
    # pending job, parses Markdown, chunks by document structure, calls
    # embedding-service for chunk vectors, writes document/version/chunk metadata
    # to PostgreSQL, stores a managed copy, and upserts vectors to Qdrant.
    worker_result = run_next_job(worker_id="e2e-worker")

    assert worker_result.status == "active"
    assert worker_result.processed_items == 1

    second_worker_result = run_next_job(worker_id="e2e-worker")

    assert second_worker_result.status == "active"
    assert second_worker_result.processed_items == 1

    # ---------------------------------------------------------------------
    # 6. Verify persisted ingestion state in PostgreSQL
    # ---------------------------------------------------------------------
    #
    # This checks that ingestion did more than return success. Each document and
    # active version must be marked active, and the fixture must produce at least
    # five stored chunks. That proves the parser/chunker/repository path ran
    # against the temporary test database.
    engine = create_metadata_engine(os.environ["POSTGRES_URL"])
    with engine.begin() as connection:
        repository = MetadataRepository(connection)
        rows_by_source_path = {
            row["document"]["source_path"]: row for row in repository.list_documents()
        }

        assert str(source) in rows_by_source_path
        assert str(second_source) in rows_by_source_path

        document = rows_by_source_path[str(source)]["document"]
        active_version = rows_by_source_path[str(source)]["active_version"]
        second_document = rows_by_source_path[str(second_source)]["document"]
        second_active_version = rows_by_source_path[str(second_source)]["active_version"]

        assert document["state"] == "active"
        assert active_version is not None
        assert active_version["state"] == "active"
        assert second_document["state"] == "active"
        assert second_active_version is not None
        assert second_active_version["state"] == "active"

        chunk_count = connection.execute(
            select(func.count())
            .select_from(chunks)
            .where(chunks.c.document_version_id == active_version["id"])
        ).scalar_one()

        assert chunk_count >= 5

        second_chunk_count = connection.execute(
            select(func.count())
            .select_from(chunks)
            .where(chunks.c.document_version_id == second_active_version["id"])
        ).scalar_one()

        assert second_chunk_count >= 1

    # ---------------------------------------------------------------------
    # 7. Search the indexed corpus through api-service
    # ---------------------------------------------------------------------
    #
    # `/search` embeds the user query through embedding-service, searches Qdrant
    # for nearby vectors, loads active chunk metadata from PostgreSQL, and
    # returns citation-ready results. The top result should contain the known
    # synthetic fact from the fixture.
    search_body = _search(api_url, headers, MARKER_QUERY)
    assert search_body["results"]
    assert "cobalt blue" in search_body["results"][0]["text"].lower()

    second_search_body = _search(api_url, headers, BEACON_QUERY)
    assert second_search_body["results"]
    assert "silver chime" in second_search_body["results"][0]["text"].lower()

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
        json={"query": MARKER_QUERY, "limit": 3},
        timeout=240,
    )

    assert chat_response.status_code == 200, chat_response.text

    chat_body = chat_response.json()
    assert chat_body["refused"] is False
    assert chat_body["citations"]

    answer = chat_body["answer"].lower()

    assert "cobalt" in answer
    assert "blue" in answer

    # ---------------------------------------------------------------------
    # 9. Delete one document through the API and verify retrieval updates
    # ---------------------------------------------------------------------
    #
    # Explicit deletion must remove the selected document from the authoritative
    # source volume, PostgreSQL metadata, managed storage, and Qdrant. The first
    # document should remain searchable, while the deleted document should no
    # longer provide citable evidence for chat.
    delete_response = httpx.delete(
        f"{api_url}/documents/{second_document['id']}",
        headers=headers,
        timeout=60,
    )

    assert delete_response.status_code == 200, delete_response.text
    delete_body = delete_response.json()
    assert delete_body["id"] == second_document["id"]
    assert delete_body["source_file_deleted"] is True
    assert delete_body["managed_store_paths_deleted"]
    assert not second_source.exists()

    remaining_search_body = _search(api_url, headers, MARKER_QUERY)
    assert remaining_search_body["results"]
    assert "cobalt blue" in remaining_search_body["results"][0]["text"].lower()

    deleted_search_body = _search(api_url, headers, BEACON_QUERY)
    assert all(
        result["document_id"] != second_document["id"] for result in deleted_search_body["results"]
    )
    assert all(
        "silver chime" not in result["text"].lower() for result in deleted_search_body["results"]
    )

    deleted_chat_response = httpx.post(
        f"{api_url}/chat",
        headers=headers,
        json={"query": BEACON_QUERY, "limit": 3},
        timeout=60,
    )

    assert deleted_chat_response.status_code == 200, deleted_chat_response.text

    deleted_chat_body = deleted_chat_response.json()
    assert deleted_chat_body["refused"] is True
    assert deleted_chat_body["answer"] is None


def _wait_for_api(api_url: str) -> None:
    deadline = time.monotonic() + 60
    last_error = "no health request attempted"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{api_url}/health", timeout=5)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code} body={response.text}"
        except httpx.HTTPError as error:
            last_error = f"request failed: {error!r}"
        time.sleep(1)
    raise AssertionError(f"api-service did not become healthy: {last_error}")


def _search(api_url: str, headers: dict[str, str], query: str) -> dict[str, Any]:
    response = httpx.post(
        f"{api_url}/search",
        headers=headers,
        json={"query": query, "limit": 3},
        timeout=60,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body
