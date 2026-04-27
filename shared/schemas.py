from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: Literal["ok"]


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None


class IngestRequest(BaseModel):
    requested_path: str | None = None


class IngestionJobResponse(BaseModel):
    id: str
    requested_path: str | None
    status: str
    worker_id: str | None
    lease_expires_at: datetime | None
    processed_items: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class DocumentVersionResponse(BaseModel):
    id: str
    document_id: str
    content_hash: str
    managed_store_path: str | None
    state: str
    embedding_model_name: str | None
    embedding_dimension: int | None
    chunking_strategy: str
    created_at: datetime
    activated_at: datetime | None
    error_message: str | None


class DocumentResponse(BaseModel):
    id: str
    source_path: str
    original_filename: str
    active_document_version_id: str | None
    state: str
    created_at: datetime
    updated_at: datetime
    active_version: DocumentVersionResponse | None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
