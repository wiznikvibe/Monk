import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import main


def _sign(body: bytes, secret: str = "test-webhook-secret") -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_rejects_invalid_signature(client):
    body = b'{"action":"opened"}'
    response = client.post(
        "/webhook/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid signature"


def test_webhook_forwards_valid_payload(client):
    body = b'{"action":"opened","pull_request":{"number":1}}'
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("main.httpx.AsyncClient", return_value=mock_client):
        response = client.post(
            "/webhook/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": _sign(body),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_client.post.assert_awaited_once()
    args, kwargs = mock_client.post.await_args
    assert args[0] == "http://webhook:8001/events"
    assert kwargs["content"] == body


def test_webhook_propagates_upstream_failure(client):
    body = b'{"action":"opened"}'
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("upstream 500")

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("main.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(Exception, match="upstream 500"):
            client.post(
                "/webhook/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": _sign(body),
                },
            )
