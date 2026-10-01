import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from tools.github_issue import GITHUB_API, GitHubIssueError, create_github_issue


def settings(**overrides: object) -> Settings:
    base = {
        "github_repo": "me/demo",
        "github_token": SecretStr("ghp_FAKE_SECRET_123"),
        "dry_run": False,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def mock_client(
    status: int, payload: dict[str, object], seen: list[httpx.Request]
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(base_url=GITHUB_API, transport=httpx.MockTransport(handler))


async def test_dry_run_makes_no_http_call() -> None:
    seen: list[httpx.Request] = []
    result = await create_github_issue(
        "Outdated doc", "body", ["docpilot"], settings=settings(dry_run=True),
        client=mock_client(201, {}, seen),
    )  # fmt: skip
    assert result["dry_run"] is True
    assert seen == []


async def test_creates_issue_in_configured_repo() -> None:
    seen: list[httpx.Request] = []
    client = mock_client(
        201, {"number": 42, "html_url": "https://github.com/me/demo/issues/42"}, seen
    )

    result = await create_github_issue(
        "Setup guide says Python 3.8", "Should be 3.11", ["docpilot"], settings=settings(),
        client=client,
    )  # fmt: skip

    assert result == {"number": 42, "url": "https://github.com/me/demo/issues/42", "dry_run": False}
    [request] = seen
    assert request.method == "POST"
    assert request.url.path == "/repos/me/demo/issues"
    assert request.headers["Authorization"] == "Bearer ghp_FAKE_SECRET_123"
    assert json.loads(request.content) == {
        "title": "Setup guide says Python 3.8",
        "body": "Should be 3.11",
        "labels": ["docpilot"],
    }


async def test_empty_labels_fall_back_to_docpilot() -> None:
    seen: list[httpx.Request] = []
    client = mock_client(201, {"number": 1, "html_url": "u"}, seen)
    await create_github_issue("t", "b", ["  "], settings=settings(), client=client)
    assert json.loads(seen[0].content)["labels"] == ["docpilot"]


@pytest.mark.parametrize(
    ("title", "reason"), [("", "must not be empty"), ("x" * 121, "at most 120")]
)
async def test_invalid_title_is_rejected(title: str, reason: str) -> None:
    with pytest.raises(GitHubIssueError, match=reason):
        await create_github_issue(title, "b", [], settings=settings(dry_run=True))


async def test_missing_token_is_a_clear_error() -> None:
    with pytest.raises(GitHubIssueError, match="GITHUB_TOKEN is not set"):
        await create_github_issue("t", "b", [], settings=settings(github_token=SecretStr("")))


async def test_github_error_is_reported_without_the_token() -> None:
    client = mock_client(404, {"message": "Not Found"}, [])
    with pytest.raises(GitHubIssueError, match="404: Not Found") as info:
        await create_github_issue("t", "b", [], settings=settings(), client=client)
    assert "ghp_FAKE_SECRET_123" not in str(info.value)
