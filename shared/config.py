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
    ollama_url: str = Field(default="http://localhost:11434", alias="OLLAMA_URL")
    watch_roots: str = Field(default="./watch", alias="WATCH_ROOTS")
    document_store_path: str = Field(default="./documents", alias="DOCUMENT_STORE_PATH")
    embedding_backend: str = Field(default="fake", alias="EMBEDDING_BACKEND")
    embedding_model_name: str = Field(default="embeddinggemma", alias="EMBEDDING_MODEL_NAME")
    embedding_dimension: int = Field(default=8, alias="EMBEDDING_DIMENSION")
    ollama_embed_timeout_seconds: int = Field(default=30, alias="OLLAMA_EMBED_TIMEOUT_SECONDS")
    ollama_keep_alive: str = Field(default="5m", alias="OLLAMA_KEEP_ALIVE")
    ollama_generation_model: str = Field(default="gemma3:4b", alias="OLLAMA_GENERATION_MODEL")
    ollama_generation_timeout_seconds: int = Field(
        default=120, alias="OLLAMA_GENERATION_TIMEOUT_SECONDS"
    )
    ollama_api_key: str | None = Field(default=None, alias="OLLAMA_API_KEY")
    chat_min_top_score: float = Field(default=0.5, ge=0, le=1, alias="CHAT_MIN_TOP_SCORE")
    chat_min_usable_chunks: int = Field(default=1, ge=1, alias="CHAT_MIN_USABLE_CHUNKS")
    chat_max_context_chunks: int = Field(default=5, ge=1, le=100, alias="CHAT_MAX_CONTEXT_CHUNKS")
    chat_max_chunk_chars: int = Field(default=2000, ge=1, alias="CHAT_MAX_CHUNK_CHARS")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
