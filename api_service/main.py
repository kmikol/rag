from collections.abc import Iterator
from functools import lru_cache
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound

from api_service.chat import (
    AnswerabilityConfig,
    ChatCompletionClient,
    GenerationError,
    OpenAIChatCompletionClient,
    assess_answerability,
    build_grounded_messages,
)
from api_service.retrieval import (
    HttpQueryEmbeddingClient,
    QueryEmbeddingClient,
    RetrievalError,
    SearchRetriever,
    VectorIndex,
)
from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.repository import MetadataRepository, create_metadata_engine
from shared.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentListResponse,
    DocumentResponse,
    HealthResponse,
    IngestionJobResponse,
    IngestRequest,
    SearchRequest,
    SearchResponse,
)
from shared.vector_index import QdrantVectorIndex

configure_logging()

app = FastAPI(title="Personal RAG API Service")
bearer_auth = HTTPBearer(auto_error=False)


@lru_cache
def get_metadata_engine() -> Engine:
    """Return the configured PostgreSQL metadata engine for API requests."""
    return create_metadata_engine(get_settings().postgres_url)


@lru_cache
def get_query_embedding_client() -> QueryEmbeddingClient:
    """Return the embedding-service client used for interactive search queries."""
    return HttpQueryEmbeddingClient(get_settings().embedding_service_url)


@lru_cache
def get_vector_index() -> VectorIndex:
    """Return the configured Qdrant vector index for retrieval."""
    return QdrantVectorIndex()


@lru_cache
def get_chat_completion_client() -> ChatCompletionClient:
    """Return the OpenAI-compatible chat client used for grounded answers."""
    settings = get_settings()
    return OpenAIChatCompletionClient(
        base_url=settings.ollama_url,
        model_name=settings.ollama_generation_model,
        timeout_seconds=settings.ollama_generation_timeout_seconds,
    )


def open_metadata_repository() -> Iterator[MetadataRepository]:
    """Open a transaction-scoped metadata repository for one API request."""
    with get_metadata_engine().begin() as connection:
        yield MetadataRepository(connection)


def require_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_auth)],
) -> None:
    """Require the configured bearer token for protected API endpoints."""
    settings = get_settings()
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not compare_digest(credentials.credentials, settings.rag_api_key)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    get_settings()
    return HealthResponse(service="api-service", status="ok")


@app.post(
    "/ingest",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_key)],
)
def create_ingestion_job(
    repository: Annotated[MetadataRepository, Depends(open_metadata_repository)],
    request: IngestRequest | None = None,
) -> IngestionJobResponse:
    job = repository.create_ingestion_job(
        requested_path=request.requested_path if request is not None else None
    )
    return IngestionJobResponse(**job)


@app.get(
    "/ingest/{job_id}",
    response_model=IngestionJobResponse,
    dependencies=[Depends(require_api_key)],
)
def get_ingestion_job(
    job_id: str,
    repository: Annotated[MetadataRepository, Depends(open_metadata_repository)],
) -> IngestionJobResponse:
    try:
        job = repository.get_ingestion_job(job_id)
    except NoResultFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found",
        ) from error
    return IngestionJobResponse(**job)


@app.get(
    "/documents",
    response_model=DocumentListResponse,
    dependencies=[Depends(require_api_key)],
)
def list_documents(
    repository: Annotated[MetadataRepository, Depends(open_metadata_repository)],
) -> DocumentListResponse:
    documents = [
        DocumentResponse(**row["document"], active_version=row["active_version"])
        for row in repository.list_documents()
    ]
    return DocumentListResponse(documents=documents)


@app.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_api_key)],
)
def chat(
    request: ChatRequest,
    repository: Annotated[MetadataRepository, Depends(open_metadata_repository)],
    embedding_client: Annotated[QueryEmbeddingClient, Depends(get_query_embedding_client)],
    vector_index: Annotated[VectorIndex, Depends(get_vector_index)],
    chat_client: Annotated[ChatCompletionClient, Depends(get_chat_completion_client)],
) -> ChatResponse:
    settings = get_settings()
    retriever = SearchRetriever(
        embedding_client=embedding_client,
        vector_index=vector_index,
    )
    try:
        citations = retriever.search(request.query, request.limit, repository)
    except RetrievalError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    refusal_reason = assess_answerability(
        citations,
        AnswerabilityConfig(
            min_top_score=settings.chat_min_top_score,
            min_usable_chunks=settings.chat_min_usable_chunks,
        ),
    )
    if refusal_reason is not None:
        return ChatResponse(
            answer=None,
            citations=citations,
            refused=True,
            refusal_reason=refusal_reason,
        )

    try:
        answer = chat_client.complete(build_grounded_messages(request.query, citations))
    except GenerationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    return ChatResponse(
        answer=answer,
        citations=citations,
        refused=False,
        refusal_reason=None,
    )


@app.post(
    "/search",
    response_model=SearchResponse,
    dependencies=[Depends(require_api_key)],
)
def search(
    request: SearchRequest,
    repository: Annotated[MetadataRepository, Depends(open_metadata_repository)],
    embedding_client: Annotated[QueryEmbeddingClient, Depends(get_query_embedding_client)],
    vector_index: Annotated[VectorIndex, Depends(get_vector_index)],
) -> SearchResponse:
    retriever = SearchRetriever(
        embedding_client=embedding_client,
        vector_index=vector_index,
    )
    try:
        results = retriever.search(request.query, request.limit, repository)
    except RetrievalError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
    return SearchResponse(results=results)
