from fastapi.testclient import TestClient

from embedding_service.main import app, fake_embedding


def make_test_client() -> TestClient:
    """Create a FastAPI test client for the embedding service.

    Other modules can use this helper when they need the embedding API
    contract in tests without depending on private test implementation.
    """
    return TestClient(app)


def make_fake_embedding(text: str, dimension: int = 8) -> list[float]:
    """Return the deterministic fake embedding used by the service skeleton.

    This keeps tests for callers aligned with the current fake provider while
    the real embedding model is intentionally deferred.
    """
    return fake_embedding(text, dimension)
