import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def _opened_payload(**overrides):
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "head": {"sha": "abc123"},
            "merged": False,
        },
        "repository": {"full_name": "acme/demo"},
        "installation": {"id": 99},
    }
    payload.update(overrides)
    return payload


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_skips_unsupported_action(client):
    response = client.post("/events", json={"action": "labeled"})
    assert response.status_code == 202
    assert response.json() == {"status": "skipped"}


def test_opened_enqueues_analyze(client):
    pr_id = uuid.uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", pr_id))
    session.add = MagicMock()

    @asynccontextmanager
    async def session_cm():
        yield session

    with (
        patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()),
        patch("main.analyze_pr.apply_async") as enqueue,
    ):
        response = client.post("/events", json=_opened_payload())

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    session.add.assert_called_once()
    enqueue.assert_called_once()
    args = enqueue.call_args.kwargs["args"]
    assert args[0] == str(pr_id)
    assert args[1] == 42
    assert args[2] == "acme/demo"
    assert args[3] == "abc123"
    assert args[4] == 99


def test_duplicate_sha_returns_already_processing(client):
    existing = MagicMock()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def session_cm():
        yield session

    with (
        patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()),
        patch("main.analyze_pr.apply_async") as enqueue,
    ):
        response = client.post("/events", json=_opened_payload())

    assert response.status_code == 202
    assert response.json() == {"status": "already_processing"}
    enqueue.assert_not_called()


def test_merged_pr_triggers_learning(client):
    pr = MagicMock()
    pr.id = uuid.uuid4()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = pr
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def session_cm():
        yield session

    payload = {
        "action": "closed",
        "pull_request": {"number": 7, "merged": True},
        "repository": {"full_name": "acme/demo"},
    }

    with (
        patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()),
        patch("main.trigger_learning.apply_async") as enqueue,
    ):
        response = client.post("/events", json=payload)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    enqueue.assert_called_once_with(
        args=["acme/demo", str(pr.id)],
        queue="learning",
    )


def test_analyze_pr_posts_to_orchestrator():
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=None)
    mock_client.post = MagicMock()

    with patch("worker.httpx.Client", return_value=mock_client):
        from worker import analyze_pr

        analyze_pr("pr-1", 1, "acme/demo", "sha", 9)

    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == "http://orchestrator:8002/analyze"
    assert kwargs["json"]["pr_id"] == "pr-1"
    assert kwargs["json"]["installation_id"] == 9
