FROM python:3.11-slim-bookworm

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY api_service /app/api_service
COPY embedding_service /app/embedding_service
COPY ingestion_worker /app/ingestion_worker
COPY shared /app/shared
RUN pip install --no-cache-dir -e /app

CMD ["uvicorn", "embedding_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
