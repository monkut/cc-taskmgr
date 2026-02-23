from __future__ import annotations

import asyncio
import json
import logging
import subprocess

from tony.models import Comment, Issue, Project

logger = logging.getLogger(__name__)

RATE_LIMIT_MARKER = "rate limit"


class GitHubRateLimitError(Exception):
    """Raised when the GitHub API rate limit is exceeded."""


GH_SEARCH_FIELDS = [
    "number",
    "title",
    "state",
    "url",
    "repository",
    "author",
    "createdAt",
    "updatedAt",
    "labels",
    "commentsCount",
    "body",
]

GH_DETAIL_FIELDS = [
    "number",
    "title",
    "state",
    "url",
    "author",
    "createdAt",
    "updatedAt",
    "labels",
    "body",
    "comments",
]


def _run_gh(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    cmd = ["gh", *args]
    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
    if result.returncode != 0 and RATE_LIMIT_MARKER in (result.stderr or ""):
        raise GitHubRateLimitError(result.stderr.strip())
    return result


def check_gh_auth() -> bool:
    result = _run_gh(["auth", "status"])
    return result.returncode == 0


def fetch_issues_sync(username: str, state: str = "open", limit: int = 100) -> list[Issue]:
    fields = ",".join(GH_SEARCH_FIELDS)
    result = _run_gh(
        [
            "search",
            "issues",
            "--assignee",
            username,
            "--state",
            state,
            "--limit",
            str(limit),
            "--json",
            fields,
        ]
    )

    if result.returncode != 0:
        logger.error(f"gh search issues failed: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.exception(f"Failed to parse gh output: {result.stdout[:200]}")
        return []

    return [Issue.from_dict(item) for item in data]


async def fetch_issues(username: str, state: str = "open", limit: int = 100) -> list[Issue]:
    return await asyncio.to_thread(fetch_issues_sync, username, state, limit)


def fetch_issue_detail_sync(repo: str, number: int) -> Issue | None:
    fields = ",".join(GH_DETAIL_FIELDS)
    result = _run_gh(
        [
            "issue",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            fields,
        ]
    )

    if result.returncode != 0:
        logger.error(f"gh issue view failed: {result.stderr}")
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.exception(f"Failed to parse gh output: {result.stdout[:200]}")
        return None

    data["repository"] = {"nameWithOwner": repo}

    comments_raw = data.get("comments", [])
    if isinstance(comments_raw, list):
        data["comments"] = comments_raw
        data["commentsCount"] = len(comments_raw)

    return Issue.from_dict(data)


async def fetch_issue_detail(repo: str, number: int) -> Issue | None:
    return await asyncio.to_thread(fetch_issue_detail_sync, repo, number)


def add_comment_sync(repo: str, number: int, body: str) -> bool:
    result = _run_gh(
        [
            "issue",
            "comment",
            str(number),
            "--repo",
            repo,
            "--body",
            body,
        ]
    )

    if result.returncode != 0:
        logger.error(f"gh issue comment failed: {result.stderr}")
        return False
    return True


async def add_comment(repo: str, number: int, body: str) -> bool:
    return await asyncio.to_thread(add_comment_sync, repo, number, body)


def fetch_projects_sync(owner: str, *, limit: int = 100) -> list[Project]:
    result = _run_gh(
        [
            "project",
            "list",
            "--owner",
            owner,
            "--format",
            "json",
            "--limit",
            str(limit),
        ]
    )

    if result.returncode != 0:
        logger.error(f"gh project list failed for {owner}: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.exception(f"Failed to parse gh project list output: {result.stdout[:200]}")
        return []

    return [Project.from_dict(p) for p in data.get("projects", [])]


async def fetch_projects(owner: str, *, limit: int = 100) -> list[Project]:
    return await asyncio.to_thread(fetch_projects_sync, owner, limit=limit)


def fetch_project_item_keys_sync(owner: str, project_number: int, *, limit: int = 1000) -> set[str]:
    """Return set of 'owner/repo#number' keys for issues in a project."""
    result = _run_gh(
        [
            "project",
            "item-list",
            str(project_number),
            "--owner",
            owner,
            "--format",
            "json",
            "--limit",
            str(limit),
        ]
    )

    if result.returncode != 0:
        logger.error(f"gh project item-list failed: {result.stderr}")
        return set()

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.exception(f"Failed to parse project items: {result.stdout[:200]}")
        return set()

    keys: set[str] = set()
    for item in data.get("items", []):
        content = item.get("content", {})
        repo = content.get("repository", "")
        number = content.get("number")
        if repo and number is not None:
            keys.add(f"{repo}#{number}")
    return keys


async def fetch_project_item_keys(owner: str, project_number: int, *, limit: int = 1000) -> set[str]:
    return await asyncio.to_thread(fetch_project_item_keys_sync, owner, project_number, limit=limit)


def fetch_comments_sync(repo: str, number: int) -> list[Comment]:
    result = _run_gh(
        [
            "issue",
            "view",
            str(number),
            "--repo",
            repo,
            "--json",
            "comments",
        ]
    )

    if result.returncode != 0:
        logger.error(f"gh issue view comments failed: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [Comment.from_dict(c) for c in data.get("comments", [])]
