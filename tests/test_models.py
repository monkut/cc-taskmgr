from tony.models import DATETIME_SENTINEL, Comment, Issue, Label, _parse_datetime


class TestParseDateTime:
    def test_valid_iso_with_z(self):
        result = _parse_datetime("2024-01-15T10:30:00Z")
        assert result.year == 2024  # noqa: PLR2004
        assert result.month == 1
        assert result.day == 15  # noqa: PLR2004

    def test_valid_iso_with_offset(self):
        result = _parse_datetime("2024-01-15T10:30:00+00:00")
        assert result.tzinfo is not None

    def test_empty_string(self):
        assert _parse_datetime("") == DATETIME_SENTINEL

    def test_invalid_string(self):
        assert _parse_datetime("not-a-date") == DATETIME_SENTINEL


class TestLabel:
    def test_from_dict(self):
        data = {"name": "bug", "color": "d73a4a", "description": "Something broken"}
        label = Label.from_dict(data)
        assert label.name == "bug"
        assert label.color == "d73a4a"
        assert label.description == "Something broken"

    def test_from_dict_minimal(self):
        label = Label.from_dict({"name": "feature"})
        assert label.name == "feature"
        assert label.color == ""


class TestComment:
    def test_from_dict(self):
        data = {
            "author": {"login": "testuser"},
            "body": "This is a comment",
            "createdAt": "2024-01-15T10:30:00Z",
            "updatedAt": "2024-01-15T11:00:00Z",
        }
        comment = Comment.from_dict(data)
        assert comment.author == "testuser"
        assert comment.body == "This is a comment"
        assert comment.created_at.year == 2024  # noqa: PLR2004


class TestIssue:
    def test_from_dict_full(self):
        data = {
            "number": 42,
            "title": "Fix the bug",
            "body": "Details here",
            "state": "OPEN",
            "url": "https://github.com/org/repo/issues/42",
            "repository": {"nameWithOwner": "org/repo"},
            "author": {"login": "alice"},
            "createdAt": "2024-01-15T10:30:00Z",
            "updatedAt": "2024-01-16T12:00:00Z",
            "labels": [{"name": "bug", "color": "d73a4a", "description": ""}],
            "commentsCount": 3,
        }
        issue = Issue.from_dict(data)
        assert issue.number == 42  # noqa: PLR2004
        assert issue.title == "Fix the bug"
        assert issue.org == "org"
        assert issue.repo == "repo"
        assert issue.author == "alice"
        assert len(issue.labels) == 1
        assert issue.labels[0].name == "bug"
        assert issue.comment_count == 3  # noqa: PLR2004

    def test_from_dict_minimal(self):
        issue = Issue.from_dict({"number": 1, "title": "test"})
        assert issue.number == 1
        assert issue.org == ""
        assert issue.repo == ""

    def test_from_dict_string_labels(self):
        data = {
            "number": 1,
            "title": "test",
            "labels": ["bug", "feature"],
            "repository": {"nameWithOwner": "org/repo"},
        }
        issue = Issue.from_dict(data)
        assert len(issue.labels) == 2  # noqa: PLR2004
        assert issue.labels[0].name == "bug"

    def test_org_repo_properties(self):
        data = {
            "number": 1,
            "title": "test",
            "repository": {"nameWithOwner": "myorg/myrepo"},
        }
        issue = Issue.from_dict(data)
        assert issue.org == "myorg"
        assert issue.repo == "myrepo"

    def test_comments_parsed(self):
        data = {
            "number": 1,
            "title": "test",
            "repository": {"nameWithOwner": "org/repo"},
            "comments": [
                {
                    "author": {"login": "bob"},
                    "body": "Hello",
                    "createdAt": "2024-01-15T10:30:00Z",
                    "updatedAt": "2024-01-15T10:30:00Z",
                },
            ],
        }
        issue = Issue.from_dict(data)
        assert len(issue.comments) == 1
        assert issue.comments[0].author == "bob"
