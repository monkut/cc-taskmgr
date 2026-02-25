import json
from unittest.mock import MagicMock, patch

import pytest

from tony import github
from tony.github import (
    GitHubRateLimitError,
    add_comment_sync,
    fetch_issue_detail_sync,
    fetch_issue_project_status_sync,
    fetch_issues_sync,
    fetch_project_item_keys_sync,
    fetch_projects_sync,
    is_in_review_status,
)


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Clear module-level caches before each test."""
    github._projects_cache.clear()
    github._item_keys_cache.clear()


SAMPLE_SEARCH_RESULT = [
    {
        "number": 42,
        "title": "Fix the bug",
        "state": "OPEN",
        "url": "https://github.com/org/repo/issues/42",
        "repository": {"nameWithOwner": "org/repo"},
        "author": {"login": "alice"},
        "createdAt": "2024-01-15T10:30:00Z",
        "updatedAt": "2024-01-16T12:00:00Z",
        "labels": [{"name": "bug", "color": "d73a4a", "description": ""}],
        "commentsCount": 2,
        "body": "Some body text",
    }
]

EXPECTED_ISSUE_NUMBER = 42

SAMPLE_ISSUE_DETAIL = {
    "number": EXPECTED_ISSUE_NUMBER,
    "title": "Fix the bug",
    "state": "OPEN",
    "url": "https://github.com/org/repo/issues/42",
    "author": {"login": "alice"},
    "createdAt": "2024-01-15T10:30:00Z",
    "updatedAt": "2024-01-16T12:00:00Z",
    "labels": [{"name": "bug", "color": "d73a4a", "description": ""}],
    "body": "Full body text with details",
    "comments": [
        {
            "author": {"login": "bob"},
            "body": "I can reproduce this",
            "createdAt": "2024-01-16T09:00:00Z",
            "updatedAt": "2024-01-16T09:00:00Z",
        },
    ],
}


class TestFetchIssuesSync:
    @patch("tony.github._run_gh")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(SAMPLE_SEARCH_RESULT),
        )
        issues = fetch_issues_sync("alice")
        assert len(issues) == 1
        assert issues[0].number == EXPECTED_ISSUE_NUMBER
        assert issues[0].title == "Fix the bug"
        assert issues[0].org == "org"

    @patch("tony.github._run_gh")
    def test_failure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        issues = fetch_issues_sync("alice")
        assert issues == []

    @patch("tony.github._run_gh")
    def test_invalid_json(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        issues = fetch_issues_sync("alice")
        assert issues == []


class TestFetchIssueDetailSync:
    @patch("tony.github._run_gh")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(SAMPLE_ISSUE_DETAIL),
        )
        issue = fetch_issue_detail_sync("org/repo", EXPECTED_ISSUE_NUMBER)
        assert issue is not None
        assert issue.number == EXPECTED_ISSUE_NUMBER
        assert issue.body == "Full body text with details"
        assert len(issue.comments) == 1
        assert issue.comments[0].author == "bob"

    @patch("tony.github._run_gh")
    def test_failure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        issue = fetch_issue_detail_sync("org/repo", EXPECTED_ISSUE_NUMBER)
        assert issue is None


class TestAddCommentSync:
    @patch("tony.github._run_gh")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0)
        result = add_comment_sync("org/repo", EXPECTED_ISSUE_NUMBER, "My comment")
        assert result is True

    @patch("tony.github._run_gh")
    def test_failure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        result = add_comment_sync("org/repo", EXPECTED_ISSUE_NUMBER, "My comment")
        assert result is False


SAMPLE_PROJECTS = {
    "projects": [
        {
            "number": 1,
            "title": "Sprint Board",
            "owner": {"login": "myorg", "type": "Organization"},
            "url": "https://github.com/orgs/myorg/projects/1",
            "items": {"totalCount": 5},
        },
    ],
    "totalCount": 1,
}

SAMPLE_PROJECT_ITEMS = {
    "items": [
        {
            "content": {
                "type": "Issue",
                "number": 42,
                "repository": "org/repo",
                "title": "Fix the bug",
            },
            "id": "PVTI_123",
        },
        {
            "content": {
                "type": "Issue",
                "number": 10,
                "repository": "org/other-repo",
                "title": "Another issue",
            },
            "id": "PVTI_456",
        },
    ],
    "totalCount": 2,
}


class TestFetchProjectsSync:
    @patch("tony.github._run_gh")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_PROJECTS))
        projects = fetch_projects_sync("myorg")
        assert len(projects) == 1
        assert projects[0].title == "Sprint Board"
        assert projects[0].owner == "myorg"

    @patch("tony.github._run_gh")
    def test_failure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        projects = fetch_projects_sync("myorg")
        assert projects == []


class TestFetchProjectItemKeysSync:
    @patch("tony.github._run_gh")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_PROJECT_ITEMS))
        keys = fetch_project_item_keys_sync("myorg", 1)
        assert keys == {"org/repo#42", "org/other-repo#10"}

    @patch("tony.github._run_gh")
    def test_failure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        keys = fetch_project_item_keys_sync("myorg", 1)
        assert keys == set()


SAMPLE_PROJECT_STATUS_RESPONSE = {
    "data": {
        "repository": {
            "issue": {
                "projectItems": {
                    "nodes": [
                        {"fieldValueByName": {"name": "In Progress"}},
                        {"fieldValueByName": {"name": "In Review"}},
                    ]
                }
            }
        }
    }
}

SAMPLE_PROJECT_STATUS_EMPTY = {"data": {"repository": {"issue": {"projectItems": {"nodes": []}}}}}


class TestFetchIssueProjectStatusSync:
    @patch("tony.github._run_gh")
    def test_success(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_PROJECT_STATUS_RESPONSE))
        statuses = fetch_issue_project_status_sync("org", "repo", 42)
        assert statuses == ["In Progress", "In Review"]

    @patch("tony.github._run_gh")
    def test_empty(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_PROJECT_STATUS_EMPTY))
        statuses = fetch_issue_project_status_sync("org", "repo", 42)
        assert statuses == []

    @patch("tony.github._run_gh")
    def test_failure(self, mock_run: MagicMock):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        statuses = fetch_issue_project_status_sync("org", "repo", 42)
        assert statuses == []


class TestIsInReviewStatus:
    @patch("tony.github.fetch_issue_project_status_sync")
    def test_in_review(self, mock_fetch: MagicMock):
        mock_fetch.return_value = ["In Review"]
        assert is_in_review_status("org", "repo", 42) is True

    @patch("tony.github.fetch_issue_project_status_sync")
    def test_in_internal_review(self, mock_fetch: MagicMock):
        mock_fetch.return_value = ["In Internal Review"]
        assert is_in_review_status("org", "repo", 42) is True

    @patch("tony.github.fetch_issue_project_status_sync")
    def test_not_in_review(self, mock_fetch: MagicMock):
        mock_fetch.return_value = ["In Progress"]
        assert is_in_review_status("org", "repo", 42) is False

    @patch("tony.github.fetch_issue_project_status_sync")
    def test_empty(self, mock_fetch: MagicMock):
        mock_fetch.return_value = []
        assert is_in_review_status("org", "repo", 42) is False


class TestRateLimitDetection:
    @patch("tony.github._run_gh")
    def test_rate_limit_raises(self, mock_run: MagicMock):
        mock_run.side_effect = GitHubRateLimitError("API rate limit exceeded for user ID 123")
        with pytest.raises(GitHubRateLimitError):
            fetch_project_item_keys_sync("myorg", 1)
