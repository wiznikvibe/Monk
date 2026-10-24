import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_learn_upserts_patterns_for_warning_and_error(client):
    finding_error = MagicMock()
    finding_error.message = "hardcoded secret"
    finding_warning = MagicMock()
    finding_warning.message = "missing timeout"

    result = MagicMock()
    result.scalars.return_value.all.return_value = [finding_error, finding_warning]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_cm():
        yield session

    with patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()):
        response = client.post(
            "/learn",
            json={
                "repo_full_name": "acme/demo",
                "pr_id": str(uuid.uuid4()),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # one select + one upsert per finding
    assert session.execute.await_count == 3
    session.commit.assert_awaited_once()


def test_learn_with_no_findings_still_succeeds(client):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_cm():
        yield session

    with patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()):
        response = client.post(
            "/learn",
            json={
                "repo_full_name": "acme/demo",
                "pr_id": str(uuid.uuid4()),
            },
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert session.execute.await_count == 1
    session.commit.assert_awaited_once()


def test_celery_routes_configured():
    from worker import app

    assert app.conf.task_routes["trigger_learning"]["queue"] == "learning"
