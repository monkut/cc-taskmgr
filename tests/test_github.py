import json
from unittest.mock import MagicMock, patch

from tony.github import add_comment_sync, fetch_issue_detail_sync, fetch_issues_sync

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
