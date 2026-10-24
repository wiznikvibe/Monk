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


def test_analyze_persists_findings_and_notifies_reviewer(client):
    pr_id = uuid.uuid4()
    findings = [
        {
            "file": "scripts/test.py",
            "line": 3,
            "severity": "error",
            "message": "eval is unsafe",
            "agent": "security",
        }
    ]

    pattern_result = MagicMock()
    pattern_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=pattern_result)
    session.add = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_cm():
        yield session

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {"findings": findings}

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=MagicMock())
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("main.get_installation_token", AsyncMock(return_value="tok")),
        patch("main.fetch_diff", AsyncMock(return_value="diff --git a/x")),
        patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()),
        patch("main.build_graph", return_value=mock_graph),
        patch("main.httpx.AsyncClient", return_value=mock_http),
    ):
        response = client.post(
            "/analyze",
            json={
                "pr_id": str(pr_id),
                "pr_number": 1,
                "repo_full_name": "acme/demo",
                "head_sha": "deadbeef",
                "installation_id": 11,
            },
        )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    session.add.assert_called()
    mock_http.post.assert_awaited()
    payload = mock_http.post.await_args.kwargs["json"]
    assert payload["pr_id"] == str(pr_id)
    assert payload["findings"] == findings
