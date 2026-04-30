from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


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


class QueryLimitRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)


class SearchRequest(QueryLimitRequest):
    pass


class SearchResult(BaseModel):
    score: float
    text: str
    document_id: str
    document_version_id: str
    chunk_id: str
    source_path: str
    original_filename: str
    page_number: int | None
    heading_path: list[str] | None
    section_title: str | None
    start_offset: int | None
    end_offset: int | None


class SearchResponse(BaseModel):
    results: list[SearchResult]


class ChatRequest(QueryLimitRequest):
    stream: bool = False


class ChatResponse(BaseModel):
    answer: str | None
    citations: list[SearchResult]
    refused: bool
    refusal_reason: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if self.refused:
            if self.answer is not None:
                raise ValueError("Refused chat responses must not include an answer.")
            if not self.refusal_reason:
                raise ValueError("Refused chat responses must include a refusal reason.")
        else:
            if not self.answer:
                raise ValueError("Answered chat responses must include an answer.")
            if self.refusal_reason is not None:
                raise ValueError("Answered chat responses must not include a refusal reason.")
        return self
