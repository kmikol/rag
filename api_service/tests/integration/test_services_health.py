import os

import httpx


def test_services_are_healthy() -> None:
    service_urls = {
        "api-service": os.environ["API_SERVICE_URL"],
        "ingestion-worker": os.environ["INGESTION_WORKER_URL"],
        "embedding-service": os.environ["EMBEDDING_SERVICE_URL"],
    }

    for service_name, base_url in service_urls.items():
        response = httpx.get(f"{base_url}/health", timeout=5)
        assert response.status_code == 200
        assert response.json() == {"service": service_name, "status": "ok"}


def test_embedding_service_contract() -> None:
    base_url = os.environ["EMBEDDING_SERVICE_URL"]

    model_response = httpx.get(f"{base_url}/model-info", timeout=5)
    embed_response = httpx.post(f"{base_url}/embed", json={"text": "hello"}, timeout=5)

    assert model_response.status_code == 200
    assert embed_response.status_code == 200
    model_info = model_response.json()
    embedding = embed_response.json()
    assert embedding["embedding_model_name"] == model_info["embedding_model_name"]
    assert embedding["dimension"] == model_info["dimension"]
    assert len(embedding["embedding"]) == model_info["dimension"]
