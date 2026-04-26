from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Environment-driven configuration shared by service skeletons."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rag_api_key: str = Field(default="dev-token", alias="RAG_API_KEY")
    postgres_url: str = Field(
        default="postgresql://rag:rag@localhost:5432/rag", alias="POSTGRES_URL"
    )
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    embedding_service_url: str = Field(
        default="http://localhost:8001", alias="EMBEDDING_SERVICE_URL"
    )
    ollama_url: str = Field(default="http://localhost:11434", alias="OLLAMA_URL")
    watch_roots: str = Field(default="./watch", alias="WATCH_ROOTS")
    document_store_path: str = Field(default="./documents", alias="DOCUMENT_STORE_PATH")
    embedding_model_name: str = Field(default="fake-embedding-model", alias="EMBEDDING_MODEL_NAME")
    embedding_dimension: int = Field(default=8, alias="EMBEDDING_DIMENSION")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
