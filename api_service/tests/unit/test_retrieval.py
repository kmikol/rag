from __future__ import annotations

from email.message import Message
from io import BytesIO
from urllib import error

import pytest

from api_service import retrieval
from api_service.retrieval import HttpQueryEmbeddingClient, RetrievalError


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_embedding_client_rejects_invalid_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(b"<html>not json</html>")

    monkeypatch.setattr(retrieval.request, "urlopen", fake_urlopen)

    with pytest.raises(RetrievalError, match="invalid JSON response"):
        HttpQueryEmbeddingClient("http://embedding-service").embed_query("alpha")


def test_embedding_client_rejects_invalid_utf8_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        return FakeResponse(b"\xff")

    monkeypatch.setattr(retrieval.request, "urlopen", fake_urlopen)

    with pytest.raises(RetrievalError, match="invalid JSON response"):
        HttpQueryEmbeddingClient("http://embedding-service").embed_query("alpha")


def test_embedding_client_handles_non_utf8_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> FakeResponse:
        raise error.HTTPError(
            url="http://embedding-service/embed",
            code=502,
            msg="Bad Gateway",
            hdrs=Message(),
            fp=BytesIO(b"\xff"),
        )

    monkeypatch.setattr(retrieval.request, "urlopen", fake_urlopen)

    with pytest.raises(RetrievalError, match="<non-UTF-8 response body>"):
        HttpQueryEmbeddingClient("http://embedding-service").embed_query("alpha")
