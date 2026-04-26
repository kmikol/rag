from fastapi import FastAPI

from shared.config import get_settings
from shared.logging_config import configure_logging
from shared.schemas import HealthResponse

configure_logging()

app = FastAPI(title="Personal RAG Ingestion Worker")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    get_settings()
    return HealthResponse(service="ingestion-worker", status="ok")
