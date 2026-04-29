import json
from typing import Any, cast
from urllib import request

from embedding_service.testing.mocks import make_fake_embedding, make_test_client
from shared.config import get_settings


def test_fake_embedding_is_deterministic() -> None:
    first = make_fake_embedding("hello", 8)
    second = make_fake_embedding("hello", 8)

    assert first == second
    assert len(first) == 8


def test_embed_endpoint_returns_configured_shape(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "fake")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "8")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "fake-embedding-model")
    get_settings.cache_clear()

    client = make_test_client()
    response = client.post("/embed", json={"text": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["dimension"] == 8
    assert len(body["embedding"]) == 8
    assert body["embedding_model_name"] == "fake-embedding-model"


def test_batch_embed_endpoint_returns_one_vector_per_text(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "fake")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "8")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "fake-embedding-model")
    get_settings.cache_clear()

    client = make_test_client()
    response = client.post("/embed/batch", json={"texts": ["one", "two"]})

    assert response.status_code == 200
    body = response.json()
    assert len(body["embeddings"]) == 2
    assert all(len(vector) == 8 for vector in body["embeddings"])


def test_model_info_includes_backend(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "embeddinggemma")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
    get_settings.cache_clear()

    client = make_test_client()
    response = client.get("/model-info")

    assert response.status_code == 200
    body = response.json()
    assert body["backend"] == "ollama"
    assert body["embedding_model_name"] == "embeddinggemma"
    assert body["dimension"] == 768


def test_ollama_backend_embed_and_batch(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "embeddinggemma")
    monkeypatch.setenv("EMBEDDING_ENDPOINT_URL", "http://ollama:11434")
    monkeypatch.setenv("EMBEDDING_KEEP_ALIVE", "5m")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "30")
    get_settings.cache_clear()

    client = make_test_client()

    class FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req: request.Request, timeout: int):
        assert req.full_url == "http://ollama:11434/api/embed"
        assert timeout == 30
        assert isinstance(req.data, bytes)
        payload = json.loads(cast(bytes, req.data).decode("utf-8"))
        assert payload["model"] == "embeddinggemma"
        assert payload["keep_alive"] == "5m"

        texts = payload["input"]
        vectors = [[float(index + 1)] * 3 for index, _ in enumerate(texts)]
        return FakeResponse({"embeddings": vectors})

    monkeypatch.setattr("embedding_service.main.request.urlopen", fake_urlopen)

    single = client.post("/embed", json={"text": "hello"})
    assert single.status_code == 200
    assert single.json()["dimension"] == 3
    assert single.json()["embedding"] == [1.0, 1.0, 1.0]

    batch = client.post("/embed/batch", json={"texts": ["one", "two"]})
    assert batch.status_code == 200
    assert batch.json()["dimension"] == 3
    assert batch.json()["embeddings"] == [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]


def test_google_backend_uses_rest_embed_content_per_input(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "google")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "gemini-embedding-2")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
    monkeypatch.setenv("EMBEDDING_ENDPOINT_URL", "https://generativelanguage.googleapis.com/v1beta")
    monkeypatch.setenv("EMBEDDING_API_KEY", "google-secret")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "45")
    get_settings.cache_clear()

    client = make_test_client()
    captured: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def read(self) -> bytes:
            return json.dumps({"embedding": {"values": self._values}}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req: request.Request, timeout: int):
        assert req.full_url == (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-embedding-2:embedContent"
        )
        assert timeout == 45
        assert req.headers["X-goog-api-key"] == "google-secret"
        assert isinstance(req.data, bytes)
        payload = json.loads(cast(bytes, req.data).decode("utf-8"))
        captured.append(payload)
        return FakeResponse([float(len(captured))] * 3)

    monkeypatch.setattr("embedding_service.main.request.urlopen", fake_urlopen)

    single = client.post("/embed", json={"text": "hello"})
    batch = client.post("/embed/batch", json={"texts": ["one", "two"]})

    assert single.status_code == 200
    assert batch.status_code == 200
    assert single.json()["embedding"] == [1.0, 1.0, 1.0]
    assert batch.json()["embeddings"] == [[2.0, 2.0, 2.0], [3.0, 3.0, 3.0]]
    assert captured[0]["model"] == "models/gemini-embedding-2"
    assert captured[0]["outputDimensionality"] == 768
    assert captured[0]["content"]["parts"][0]["text"].startswith(
        "task: question answering | query: "
    )
    assert captured[1]["content"]["parts"][0]["text"].startswith("title: none | text: ")
    assert captured[2]["content"]["parts"][0]["text"].startswith("title: none | text: ")
