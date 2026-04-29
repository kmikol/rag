import pytest

from api_service.testing.mocks import make_test_client as make_api_client
from embedding_service.testing.mocks import make_test_client as make_embedding_client
from ingestion_worker.testing.mocks import make_test_client as make_ingestion_client
from shared.config import get_settings


def test_api_health_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "fake-model")
    get_settings.cache_clear()

    response = make_api_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "api-service", "status": "ok"}


def test_embedding_health_contract() -> None:
    response = make_embedding_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "embedding-service", "status": "ok"}


def test_ingestion_worker_health_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "fake-model")
    get_settings.cache_clear()

    response = make_ingestion_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "ingestion-worker", "status": "ok"}
