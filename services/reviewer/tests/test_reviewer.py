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


def test_finding_summary_line_formats_fields():
    line = main._finding_summary_line(
        {
            "severity": "warning",
            "file": "app.py",
            "line": 10,
            "agent": "style",
            "message": "too nested",
        }
    )
    assert "**[WARNING]**" in line
    assert "`app.py:10`" in line
    assert "(style)" in line
    assert "too nested" in line


def test_build_summary_includes_header_and_findings():
    summary = main._build_summary(
        [{"severity": "error", "file": "x.py", "line": 1, "agent": "security", "message": "xss"}]
    )
    assert summary.startswith("## AI Code Review")
    assert "**[ERROR]**" in summary
    assert "xss" in summary


def test_post_review_empty_findings_skips_github(client):
    with patch("main.get_installation_token", return_value="tok") as token_fn:
        response = client.post(
            "/post-review",
            json={
                "pr_id": str(uuid.uuid4()),
                "repo_full_name": "acme/demo",
                "pr_number": 3,
                "installation_id": 1,
                "findings": [],
            },
        )

    assert response.status_code == 202
    assert response.json() == {"status": "ok"}
    token_fn.assert_called_once()


def test_post_review_posts_inline_comments_and_marks_reviewed(client):
    pr_id = uuid.uuid4()
    findings = [
        {
            "file": "scripts/test.py",
            "line": 2,
            "severity": "warning",
            "agent": "security",
            "message": "hardcoded password",
        }
    ]

    github_response = MagicMock()
    github_response.status_code = 200
    github_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=github_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_cm():
        yield session

    with (
        patch("main.get_installation_token", return_value="tok"),
        patch("main.httpx.AsyncClient", return_value=mock_http),
        patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()),
    ):
        response = client.post(
            "/post-review",
            json={
                "pr_id": str(pr_id),
                "repo_full_name": "acme/demo",
                "pr_number": 9,
                "installation_id": 5,
                "findings": findings,
            },
        )

    assert response.status_code == 202
    assert response.json() == {"status": "ok"}
    payload = mock_http.post.await_args.kwargs["json"]
    assert payload["event"] == "COMMENT"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["path"] == "scripts/test.py"
    assert payload["comments"][0]["line"] == 2
    session.execute.assert_awaited()
    session.commit.assert_awaited()


def test_post_review_falls_back_when_inline_comments_invalid(client):
    findings = [
        {
            "file": "a.py",
            "line": 9999,
            "severity": "info",
            "agent": "style",
            "message": "nit",
        }
    ]

    first = MagicMock()
    first.status_code = 422
    first.raise_for_status = MagicMock()

    second = MagicMock()
    second.status_code = 200
    second.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(side_effect=[first, second])
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)

    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def session_cm():
        yield session

    with (
        patch("main.get_installation_token", return_value="tok"),
        patch("main.httpx.AsyncClient", return_value=mock_http),
        patch("main.AsyncSessionLocal", side_effect=lambda: session_cm()),
    ):
        response = client.post(
            "/post-review",
            json={
                "pr_id": str(uuid.uuid4()),
                "repo_full_name": "acme/demo",
                "pr_number": 9,
                "installation_id": 5,
                "findings": findings,
            },
        )

    assert response.status_code == 202
    assert mock_http.post.await_count == 2
    fallback_payload = mock_http.post.await_args_list[1].kwargs["json"]
    assert "comments" not in fallback_payload
    assert fallback_payload["body"].startswith("## AI Code Review")
