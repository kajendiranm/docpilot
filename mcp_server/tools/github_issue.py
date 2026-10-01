"""create_github_issue: open an issue in the one repo set by GITHUB_REPO (or fake it in DRY_RUN)."""

from typing import NotRequired, TypedDict

import httpx

from app.config import Settings

MAX_TITLE = 120
MAX_BODY = 20_000
MAX_LABELS = 5
GITHUB_API = "https://api.github.com"

DESCRIPTION = (
    "Create a GitHub issue to flag or report a problem, for example an outdated or wrong doc. "
    "Use it ONLY when the user explicitly asks to flag, report or raise something. "
    "Confirm the problem with search_docs first and quote the doc file and section in the body. "
    "Returns the issue number and URL."
)


class IssueResult(TypedDict):
    number: int
    url: str
    dry_run: bool
    note: NotRequired[str]


class GitHubIssueError(ValueError):
    pass


def validate_issue(title: str, body: str, labels: list[str]) -> tuple[str, str, list[str]]:
    title, body = title.strip(), body.strip()
    if not title:
        raise GitHubIssueError("The issue title must not be empty.")
    if len(title) > MAX_TITLE:
        raise GitHubIssueError(f"The issue title must be at most {MAX_TITLE} characters.")
    if len(body) > MAX_BODY:
        raise GitHubIssueError(f"The issue body must be at most {MAX_BODY} characters.")
    labels = [label.strip() for label in labels if label.strip()][:MAX_LABELS]
    return title, body, labels or ["docpilot"]


async def create_github_issue(
    title: str,
    body: str,
    labels: list[str],
    *,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> IssueResult:
    title, body, labels = validate_issue(title, body, labels)
    repo = settings.github_repo  # never taken from the model: the tool can't target other repos

    if settings.dry_run:
        return IssueResult(
            number=0,
            url=f"https://github.com/{repo}/issues (dry run)",
            dry_run=True,
            note="DRY_RUN is on: no real issue was created. Tell the user this was a dry run.",
        )

    token = settings.github_token.get_secret_value()
    if not token:
        raise GitHubIssueError("GITHUB_TOKEN is not set, so issues can't be created.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body, "labels": labels}
    async with client or httpx.AsyncClient(base_url=GITHUB_API, timeout=10) as http:
        try:
            resp = await http.post(f"/repos/{repo}/issues", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise GitHubIssueError(f"Could not reach GitHub: {type(exc).__name__}") from exc

    if resp.status_code != 201:
        # GitHub's error body has a "message"; it never contains our token.
        message = resp.json().get("message", "") if resp.content else ""
        hint = " (check GITHUB_REPO and the token's repo access)" if resp.status_code == 404 else ""
        raise GitHubIssueError(f"GitHub returned {resp.status_code}: {message}{hint}")
    data = resp.json()
    return IssueResult(number=data["number"], url=data["html_url"], dry_run=False)
