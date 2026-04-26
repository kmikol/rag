from embedding_service.testing.mocks import make_fake_embedding, make_test_client


def test_fake_embedding_is_deterministic() -> None:
    first = make_fake_embedding("hello", 8)
    second = make_fake_embedding("hello", 8)

    assert first == second
    assert len(first) == 8


def test_embed_endpoint_returns_configured_shape() -> None:
    client = make_test_client()

    response = client.post("/embed", json={"text": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["dimension"] == 8
    assert len(body["embedding"]) == 8
    assert body["model_name"] == "fake-embedding-model"


def test_batch_embed_endpoint_returns_one_vector_per_text() -> None:
    client = make_test_client()

    response = client.post("/embed/batch", json={"texts": ["one", "two"]})

    assert response.status_code == 200
    body = response.json()
    assert len(body["embeddings"]) == 2
    assert all(len(vector) == 8 for vector in body["embeddings"])
