import hashlib

from fastapi import FastAPI
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.schemas import HealthResponse

configure_logging()

app = FastAPI(title="Personal RAG Embedding Service")


class ModelInfoResponse(BaseModel):
    model_name: str
    dimension: int


class EmbedRequest(BaseModel):
    text: str = Field(min_length=1)


class EmbedResponse(BaseModel):
    embedding: list[float]
    model_name: str
    dimension: int


class BatchEmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1)


class BatchEmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model_name: str
    dimension: int


def fake_embedding(text: str, dimension: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [round(digest[index] / 255.0, 6) for index in range(dimension)]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(service="embedding-service", status="ok")


@app.get("/model-info", response_model=ModelInfoResponse)
def model_info() -> ModelInfoResponse:
    settings = get_settings()
    return ModelInfoResponse(
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    settings = get_settings()
    return EmbedResponse(
        embedding=fake_embedding(request.text, settings.embedding_dimension),
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )


@app.post("/embed/batch", response_model=BatchEmbedResponse)
def embed_batch(request: BatchEmbedRequest) -> BatchEmbedResponse:
    settings = get_settings()
    return BatchEmbedResponse(
        embeddings=[fake_embedding(text, settings.embedding_dimension) for text in request.texts],
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )
