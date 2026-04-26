from shared.config import AppSettings


def test_settings_defaults_are_usable() -> None:
    settings = AppSettings()

    assert settings.rag_api_key == "dev-token"
    assert settings.embedding_dimension == 8
    assert settings.embedding_model_name == "fake-embedding-model"


def test_settings_read_aliases(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_DIMENSION", "16")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "test-model")

    settings = AppSettings()

    assert settings.embedding_dimension == 16
    assert settings.embedding_model_name == "test-model"
