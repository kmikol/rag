from collections.abc import Iterator
from functools import lru_cache
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.repository import MetadataRepository, create_metadata_engine
from shared.schemas import (
    DocumentListResponse,
    DocumentResponse,
    HealthResponse,
    IngestionJobResponse,
    IngestRequest,
)

configure_logging()

app = FastAPI(title="Personal RAG API Service")
bearer_auth = HTTPBearer(auto_error=False)


@lru_cache
def get_metadata_engine() -> Engine:
    """Return the configured PostgreSQL metadata engine for API requests."""
    return create_metadata_engine(get_settings().postgres_url)


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
