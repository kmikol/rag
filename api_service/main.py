import json
import logging
import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound

from api_service.chat import (
    AnswerabilityConfig,
    GenerationError,
    GenerationOptions,
    GoogleGenerateContentLLMClient,
    GroundingConfig,
    LLMClient,
    OpenAICompatibleLLMClient,
    assess_answerability,
    build_grounded_messages,
    select_grounding_citations,
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
    DocumentDeleteResponse,
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
logger = logging.getLogger(__name__)
CHAT_GENERATION_ERROR_DETAIL = "Chat generation failed."
DOCUMENT_DELETION_ERROR_DETAIL = "Document deletion failed."


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
def get_chat_completion_client() -> LLMClient:
    """Return the configured LLM client used for grounded answers."""
    settings = get_settings()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleLLMClient(
            chat_completions_url=settings.llm_chat_completions_url,
            model_name=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            api_key=settings.llm_api_key,
        )
    if settings.llm_provider == "google_genai":
        return GoogleGenerateContentLLMClient(
            endpoint_url=settings.llm_endpoint_url,
            model_name=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            api_key=settings.llm_api_key,
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Unsupported LLM provider: {settings.llm_provider}",
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


@app.delete(
    "/documents/{document_id}",
    response_model=DocumentDeleteResponse,
    dependencies=[Depends(require_api_key)],
)
def delete_document(
    document_id: str,
    repository: Annotated[MetadataRepository, Depends(open_metadata_repository)],
    vector_index: Annotated[VectorIndex, Depends(get_vector_index)],
) -> DocumentDeleteResponse:
    settings = get_settings()
    deletion_target = repository.get_document_deletion_target(document_id)
    if deletion_target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    document = deletion_target["document"]
    source_path = str(document["source_path"])
    try:
        source_file = _validate_path_under_roots(
            source_path, _parse_path_list(settings.watch_roots)
        )
        managed_files = [
            _validate_path_under_root(path, Path(settings.document_store_path).expanduser())
            for path in deletion_target["managed_store_paths"]
        ]
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    try:
        vector_index.delete_by_document_id(document_id)
        source_file_deleted = _delete_file_if_present(source_file)
        managed_store_paths_deleted = _delete_unique_files(managed_files)
    except Exception as error:
        logger.exception("Document deletion cleanup failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=DOCUMENT_DELETION_ERROR_DETAIL,
        ) from error

    repository.delete_document(document_id)
    return DocumentDeleteResponse(
        id=document_id,
        source_path=source_path,
        deleted=True,
        source_file_deleted=source_file_deleted,
        managed_store_paths_deleted=managed_store_paths_deleted,
    )


def _parse_path_list(value: str) -> tuple[Path, ...]:
    return tuple(
        Path(part.strip()).expanduser() for part in value.split(os.pathsep) if part.strip()
    )


def _validate_path_under_roots(path: str, roots: tuple[Path, ...]) -> Path:
    if not roots:
        raise ValueError("WATCH_ROOTS must contain at least one path for document deletion.")
    for root in roots:
        try:
            return _validate_path_under_root(path, root)
        except ValueError:
            continue
    raise ValueError(f"Path is outside configured watch roots: {path}")


def _validate_path_under_root(path: str | Path, root: Path) -> Path:
    resolved_path = Path(path).expanduser().resolve(strict=False)
    resolved_root = root.expanduser().resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"Path is outside configured root: {path}") from error
    return resolved_path


def _delete_file_if_present(path: Path) -> bool:
    if not path.exists():
        return False
    if not path.is_file():
        raise ValueError(f"Deletion target is not a file: {path}")
    path.unlink()
    return True


def _delete_unique_files(paths: list[Path]) -> list[str]:
    deleted: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if _delete_file_if_present(path):
            deleted.append(str(path))
    return deleted


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
    chat_client: Annotated[LLMClient, Depends(get_chat_completion_client)],
) -> ChatResponse | StreamingResponse:
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

    grounding_config = GroundingConfig(
        max_context_chunks=settings.chat_max_context_chunks,
        max_chunk_chars=settings.chat_max_chunk_chars,
    )
    grounding_citations = select_grounding_citations(citations, grounding_config)
    refusal_reason = assess_answerability(
        grounding_citations,
        AnswerabilityConfig(
            min_top_score=settings.chat_min_top_score,
            min_usable_chunks=settings.chat_min_usable_chunks,
        ),
    )
    if refusal_reason is not None:
        if request.stream:
            event = {
                "type": "done",
                "answer": None,
                "citations": [citation.model_dump() for citation in grounding_citations],
                "refused": True,
                "refusal_reason": refusal_reason,
            }
            return StreamingResponse(
                iter([f"data: {json.dumps(event)}\n\n"]),
                media_type="text/event-stream",
            )
        return ChatResponse(
            answer=None,
            citations=grounding_citations,
            refused=True,
            refusal_reason=refusal_reason,
        )

    messages = build_grounded_messages(request.query, grounding_citations, grounding_config)
    options = GenerationOptions(
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )

    if request.stream:

        def event_stream() -> Iterator[str]:
            answer_parts: list[str] = []
            try:
                for token in chat_client.stream_complete(messages, options):
                    answer_parts.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"
            except GenerationError:
                logger.exception("Chat stream generation failed.")
                yield (
                    f"data: "
                    f"{json.dumps({'type': 'error', 'detail': CHAT_GENERATION_ERROR_DETAIL})}"
                    f"\n\n"
                )
                return
            final_answer = "".join(answer_parts)
            done_event = {
                "type": "done",
                "answer": final_answer,
                "citations": [citation.model_dump() for citation in grounding_citations],
                "refused": False,
                "refusal_reason": None,
            }
            yield f"data: {json.dumps(done_event)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        answer = chat_client.complete(messages, options)
    except GenerationError as error:
        logger.exception("Chat generation failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=CHAT_GENERATION_ERROR_DETAIL,
        ) from error

    return ChatResponse(
        answer=answer,
        citations=grounding_citations,
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
