from fastapi.testclient import TestClient

from api_service.main import app


def make_test_client() -> TestClient:
    """Create a FastAPI test client for the API service.

    The helper gives other modules a stable way to exercise the service
    contract without importing test files or duplicating setup details.
    """
    return TestClient(app)
