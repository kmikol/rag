import hashlib
import json
from dataclasses import dataclass
from typing import Protocol
from urllib import error, request

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.schemas import HealthResponse

configure_logging()

app = FastAPI(title="Personal RAG Embedding Service")


class ModelInfoResponse(BaseModel):
    backend: str
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


class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> list[float]:
        """Embed one string input and return a vector."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of string inputs and return one vector per input."""


@dataclass
class FakeEmbeddingBackend:
    dimension: int

    def embed(self, text: str) -> list[float]:
        return fake_embedding(text, self.dimension)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


@dataclass
class OllamaEmbeddingBackend:
    url: str
    model_name: str
    timeout_seconds: int
    keep_alive: str

    def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        payload = json.dumps(
            {
                "model": self.model_name,
                "input": texts,
                "keep_alive": self.keep_alive,
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self.url.rstrip('/')}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise HTTPException(status_code=502, detail=f"Ollama HTTP error: {detail}") from exc
        except error.URLError as exc:
            raise HTTPException(status_code=502, detail=f"Ollama unavailable: {exc.reason}") from exc

        embeddings = body.get("embeddings")
        if not isinstance(embeddings, list):
            raise HTTPException(status_code=502, detail="Invalid Ollama response: missing embeddings")

        return embeddings

    def embed(self, text: str) -> list[float]:
        embeddings = self._request_embeddings([text])
        return embeddings[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._request_embeddings(texts)
        if len(embeddings) != len(texts):
            raise HTTPException(status_code=502, detail="Invalid Ollama response: wrong embedding count")
        return embeddings


def _make_embedding_backend() -> EmbeddingBackend:
    settings = get_settings()
    if settings.embedding_backend == "ollama":
        return OllamaEmbeddingBackend(
            url=settings.ollama_url,
            model_name=settings.embedding_model_name,
            timeout_seconds=settings.ollama_embed_timeout_seconds,
            keep_alive=settings.ollama_keep_alive,
        )

    return FakeEmbeddingBackend(dimension=settings.embedding_dimension)


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
        backend=settings.embedding_backend,
        model_name=settings.embedding_model_name,
        dimension=settings.embedding_dimension,
    )


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    settings = get_settings()
    embedding = _make_embedding_backend().embed(request.text)

    return EmbedResponse(
        embedding=embedding,
        model_name=settings.embedding_model_name,
        dimension=len(embedding),
    )


@app.post("/embed/batch", response_model=BatchEmbedResponse)
def embed_batch(request: BatchEmbedRequest) -> BatchEmbedResponse:
    settings = get_settings()
    embeddings = _make_embedding_backend().embed_batch(request.texts)
    dimension = len(embeddings[0]) if embeddings else 0

    return BatchEmbedResponse(
        embeddings=embeddings,
        model_name=settings.embedding_model_name,
        dimension=dimension,
    )
