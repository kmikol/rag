FROM python:3.11-slim-bookworm

ENV PYTHONPATH=/workspace
WORKDIR /workspace

COPY pyproject.toml /workspace/pyproject.toml
COPY alembic.ini /workspace/alembic.ini
COPY api_service /workspace/api_service
COPY embedding_service /workspace/embedding_service
COPY ingestion_worker /workspace/ingestion_worker
COPY shared /workspace/shared
COPY tests /workspace/tests
COPY docs /workspace/docs
COPY migrations /workspace/migrations

RUN pip install --no-cache-dir -e ".[dev]"
