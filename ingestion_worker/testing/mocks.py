from fastapi.testclient import TestClient

from ingestion_worker.main import app


def make_test_client() -> TestClient:
    """Create a FastAPI test client for the ingestion worker health surface.

    The worker is primarily job-driven, but the skeleton exposes HTTP health
    for Compose checks and service-level integration tests.
    """
    return TestClient(app)
