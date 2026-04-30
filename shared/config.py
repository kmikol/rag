from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Environment-driven configuration shared by service skeletons."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rag_api_key: str = Field(default="dev-token", alias="RAG_API_KEY")
    postgres_url: str = Field(
        default="postgresql+psycopg://rag:rag@localhost:5432/rag", alias="POSTGRES_URL"
    )
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="rag_chunks", alias="QDRANT_COLLECTION")
    embedding_service_url: str = Field(
        default="http://localhost:8001", alias="EMBEDDING_SERVICE_URL"
    )
    watch_roots: str = Field(default="./watch", alias="WATCH_ROOTS")
    document_store_path: str = Field(default="./documents", alias="DOCUMENT_STORE_PATH")
    embedding_backend: str = Field(default="fake", alias="EMBEDDING_BACKEND")
    embedding_model_name: str = Field(alias="EMBEDDING_MODEL_NAME")
    embedding_dimension: int = Field(default=8, alias="EMBEDDING_DIMENSION")
    embedding_endpoint_url: str = Field(
        default="http://localhost:11434", alias="EMBEDDING_ENDPOINT_URL"
    )
    embedding_api_key: str | None = Field(default=None, alias="EMBEDDING_API_KEY")
    embedding_timeout_seconds: int = Field(default=30, alias="EMBEDDING_TIMEOUT_SECONDS")
    embedding_keep_alive: str = Field(default="5m", alias="EMBEDDING_KEEP_ALIVE")
    llm_provider: str = Field(default="openai_compatible", alias="LLM_PROVIDER")
    llm_chat_completions_url: str = Field(
        default="http://localhost:11434/v1/chat/completions",
        alias="LLM_CHAT_COMPLETIONS_URL",
    )
    llm_endpoint_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        alias="LLM_ENDPOINT_URL",
    )
    llm_model: str = Field(default="gemma3:4b", alias="LLM_MODEL")
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_timeout_seconds: int = Field(default=120, alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float | None = Field(default=None, ge=0, alias="LLM_TEMPERATURE")
    llm_max_tokens: int | None = Field(default=None, ge=1, alias="LLM_MAX_TOKENS")
    chat_min_top_score: float = Field(default=0.25, ge=0, le=1, alias="CHAT_MIN_TOP_SCORE")
    chat_min_usable_chunks: int = Field(default=1, ge=1, alias="CHAT_MIN_USABLE_CHUNKS")
    chat_max_context_chunks: int = Field(default=5, ge=1, le=100, alias="CHAT_MAX_CONTEXT_CHUNKS")
    chat_max_chunk_chars: int = Field(default=2000, ge=1, alias="CHAT_MAX_CHUNK_CHARS")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()  # type: ignore[call-arg]
