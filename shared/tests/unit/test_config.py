from shared.config import AppSettings


def test_settings_defaults_are_usable() -> None:
    settings = AppSettings()

    assert settings.rag_api_key == "dev-token"
    assert settings.qdrant_collection == "rag_chunks"
    assert settings.embedding_backend == "fake"
    assert settings.embedding_dimension == 8
    assert settings.embedding_model_name == "embeddinggemma"
    assert settings.ollama_embed_timeout_seconds == 30
    assert settings.ollama_keep_alive == "5m"


def test_settings_read_aliases(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "16")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "test-model")
    monkeypatch.setenv("OLLAMA_EMBED_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("QDRANT_COLLECTION", "test_chunks")

    settings = AppSettings()

    assert settings.qdrant_collection == "test_chunks"
    assert settings.embedding_backend == "ollama"
    assert settings.embedding_dimension == 16
    assert settings.embedding_model_name == "test-model"
    assert settings.ollama_embed_timeout_seconds == 60
    assert settings.ollama_keep_alive == "10m"
