import pytest
from pydantic import ValidationError

from shared.config import AppSettings


def test_settings_defaults_are_usable(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "embeddinggemma")
    settings = AppSettings()  # type: ignore[call-arg]

    assert settings.rag_api_key == "dev-token"
    assert settings.qdrant_collection == "rag_chunks"
    assert settings.embedding_backend == "fake"
    assert settings.embedding_dimension == 8
    assert settings.embedding_model_name == "embeddinggemma"
    assert settings.embedding_endpoint_url == "http://localhost:11434"
    assert settings.embedding_api_key is None
    assert settings.embedding_timeout_seconds == 30
    assert settings.embedding_keep_alive == "5m"
    assert settings.llm_provider == "openai_compatible"
    assert settings.llm_chat_completions_url == "http://localhost:11434/v1/chat/completions"
    assert settings.llm_endpoint_url == "https://generativelanguage.googleapis.com/v1beta"
    assert settings.llm_model == "gemma3:4b"
    assert settings.llm_api_key is None
    assert settings.llm_timeout_seconds == 120
    assert settings.llm_temperature is None
    assert settings.llm_max_tokens is None
    assert settings.chat_min_top_score == 0.5
    assert settings.chat_min_usable_chunks == 1
    assert settings.chat_max_context_chunks == 5
    assert settings.chat_max_chunk_chars == 2000


def test_settings_require_embedding_model_name(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDING_MODEL_NAME", raising=False)

    with pytest.raises(ValidationError, match="EMBEDDING_MODEL_NAME"):
        AppSettings()  # type: ignore[call-arg]


def test_settings_read_aliases(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_BACKEND", "ollama")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "16")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "test-model")
    monkeypatch.setenv("EMBEDDING_ENDPOINT_URL", "http://embedding-provider")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("EMBEDDING_KEEP_ALIVE", "10m")
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_CHAT_COMPLETIONS_URL", "http://llm-provider/v1/chat/completions")
    monkeypatch.setenv("LLM_ENDPOINT_URL", "http://native-llm-provider")
    monkeypatch.setenv("LLM_MODEL", "test-chat-model")
    monkeypatch.setenv("LLM_API_KEY", "test-api-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    monkeypatch.setenv("LLM_MAX_TOKENS", "128")
    monkeypatch.setenv("QDRANT_COLLECTION", "test_chunks")
    monkeypatch.setenv("CHAT_MIN_TOP_SCORE", "0.75")
    monkeypatch.setenv("CHAT_MIN_USABLE_CHUNKS", "2")
    monkeypatch.setenv("CHAT_MAX_CONTEXT_CHUNKS", "3")
    monkeypatch.setenv("CHAT_MAX_CHUNK_CHARS", "400")

    settings = AppSettings()  # type: ignore[call-arg]

    assert settings.qdrant_collection == "test_chunks"
    assert settings.embedding_backend == "ollama"
    assert settings.embedding_dimension == 16
    assert settings.embedding_model_name == "test-model"
    assert settings.embedding_endpoint_url == "http://embedding-provider"
    assert settings.embedding_api_key == "embedding-key"
    assert settings.embedding_timeout_seconds == 60
    assert settings.embedding_keep_alive == "10m"
    assert settings.llm_provider == "openai_compatible"
    assert settings.llm_chat_completions_url == "http://llm-provider/v1/chat/completions"
    assert settings.llm_endpoint_url == "http://native-llm-provider"
    assert settings.llm_model == "test-chat-model"
    assert settings.llm_api_key == "test-api-key"
    assert settings.llm_timeout_seconds == 90
    assert settings.llm_temperature == 0.1
    assert settings.llm_max_tokens == 128
    assert settings.chat_min_top_score == 0.75
    assert settings.chat_min_usable_chunks == 2
    assert settings.chat_max_context_chunks == 3
    assert settings.chat_max_chunk_chars == 400
