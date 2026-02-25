from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path

from tony.models import Comment, Issue, Project

logger = logging.getLogger(__name__)

RATE_LIMIT_MARKER = "rate limit"
CACHE_TTL = 300  # 5 minutes

_projects_cache: dict[str, tuple[float, list[Project]]] = {}
_item_keys_cache: dict[tuple[str, int], tuple[float, set[str]]] = {}


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
    cached = _projects_cache.get(owner)
    if cached and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]

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

    projects = [Project.from_dict(p) for p in data.get("projects", [])]
    _projects_cache[owner] = (time.monotonic(), projects)
    return projects


async def fetch_projects(owner: str, *, limit: int = 100) -> list[Project]:
    return await asyncio.to_thread(fetch_projects_sync, owner, limit=limit)


def fetch_project_item_keys_sync(owner: str, project_number: int, *, limit: int = 1000) -> set[str]:
    """Return set of 'owner/repo#number' keys for issues in a project."""
    cache_key = (owner, project_number)
    cached = _item_keys_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL:
        return cached[1]

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
    _item_keys_cache[cache_key] = (time.monotonic(), keys)
    return keys


async def fetch_project_item_keys(owner: str, project_number: int, *, limit: int = 1000) -> set[str]:
    return await asyncio.to_thread(fetch_project_item_keys_sync, owner, project_number, limit=limit)


def add_label_sync(repo: str, number: int, label: str) -> bool:
    result = _run_gh(["issue", "edit", str(number), "--repo", repo, "--add-label", label])
    return result.returncode == 0


async def add_label(repo: str, number: int, label: str) -> bool:
    return await asyncio.to_thread(add_label_sync, repo, number, label)


def find_repo_dir(project_dirs: list[str], repo_name: str) -> Path | None:
    """Walk 1-level subdirs of each project dir looking for a directory matching repo_name."""
    for dir_path in project_dirs:
        parent = Path(dir_path).expanduser()
        if not parent.is_dir():
            continue
        # Check direct match
        candidate = parent / repo_name
        if candidate.is_dir():
            return candidate
        # Check 1-level subdirs
        try:
            for child in parent.iterdir():
                if child.is_dir() and child.name == repo_name:
                    return child
        except PermissionError:
            continue
    return None


REVIEW_STATUSES = {"in-internal-review", "in-review"}

_PROJECT_STATUS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      projectItems(first: 10) {
        nodes {
          fieldValueByName(name: "Status") {
            ... on ProjectV2ItemFieldSingleSelectValue {
              name
            }
          }
        }
      }
    }
  }
}
"""


def fetch_issue_project_status_sync(owner: str, repo_name: str, number: int) -> list[str]:
    """Fetch project Status field values for an issue via GraphQL."""
    query = _PROJECT_STATUS_QUERY.strip()
    variables = json.dumps({"owner": owner, "repo": repo_name, "number": number})
    result = _run_gh(
        ["api", "graphql", "-f", f"query={query}", "-f", f"variables={variables}"],
        timeout=15,
    )
    if result.returncode != 0:
        logger.error(f"GraphQL project status query failed: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.exception(f"Failed to parse project status response: {result.stdout[:200]}")
        return []

    statuses: list[str] = []
    issue_data = data.get("data", {}).get("repository", {}).get("issue")
    if not issue_data:
        return []
    for node in issue_data.get("projectItems", {}).get("nodes", []):
        field_value = node.get("fieldValueByName")
        if field_value and "name" in field_value:
            statuses.append(field_value["name"])
    return statuses


async def fetch_issue_project_status(owner: str, repo_name: str, number: int) -> list[str]:
    return await asyncio.to_thread(fetch_issue_project_status_sync, owner, repo_name, number)


def is_in_review_status(owner: str, repo_name: str, number: int) -> bool:
    """Check if an issue is in a review-like project column."""
    statuses = fetch_issue_project_status_sync(owner, repo_name, number)
    for s in statuses:
        normalized = s.lower().replace(" ", "-")
        if normalized in REVIEW_STATUSES:
            return True
    return False


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
