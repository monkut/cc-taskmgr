from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

DATETIME_SENTINEL = datetime.min  # noqa: DTZ901


@dataclass
class Label:
    name: str
    color: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Label:
        return cls(
            name=data.get("name", ""),
            color=data.get("color", ""),
            description=data.get("description", ""),
        )


@dataclass
class Comment:
    author: str
    body: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dict(cls, data: dict) -> Comment:
        return cls(
            author=data.get("author", {}).get("login", "unknown"),
            body=data.get("body", ""),
            created_at=_parse_datetime(data.get("createdAt", "")),
            updated_at=_parse_datetime(data.get("updatedAt", "")),
        )


@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str
    url: str
    repository: str
    author: str
    created_at: datetime
    updated_at: datetime
    labels: list[Label] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    comment_count: int = 0

    @property
    def org(self) -> str:
        parts = self.repository.split("/")
        return parts[0] if len(parts) > 1 else ""

    @property
    def repo(self) -> str:
        parts = self.repository.split("/")
        return parts[1] if len(parts) > 1 else self.repository

    @classmethod
    def from_dict(cls, data: dict) -> Issue:
        repo = data.get("repository", {})
        repo_name = repo.get("nameWithOwner", "") if isinstance(repo, dict) else str(repo)

        labels_raw = data.get("labels", [])
        if isinstance(labels_raw, list) and labels_raw and isinstance(labels_raw[0], dict):
            labels = [Label.from_dict(lb) for lb in labels_raw]
        elif isinstance(labels_raw, list) and labels_raw and isinstance(labels_raw[0], str):
            labels = [Label(name=lb) for lb in labels_raw]
        else:
            labels = []

        comments_raw = data.get("comments", [])
        if isinstance(comments_raw, list):
            comments = [Comment.from_dict(c) for c in comments_raw if isinstance(c, dict)]
        else:
            comments = []

        comment_count = data.get("commentsCount", 0)
        if isinstance(comments_raw, list) and len(comments_raw) > comment_count:
            comment_count = len(comments_raw)

        author_raw = data.get("author")
        if isinstance(author_raw, dict):
            author = author_raw.get("login", "unknown")
        else:
            author = str(author_raw) if author_raw else "unknown"

        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            state=data.get("state", "OPEN"),
            url=data.get("url", ""),
            repository=repo_name,
            author=author,
            created_at=_parse_datetime(data.get("createdAt", "")),
            updated_at=_parse_datetime(data.get("updatedAt", "")),
            labels=labels,
            comments=comments,
            comment_count=comment_count,
        )


@dataclass
class Project:
    number: int
    title: str
    owner: str
    url: str = ""
    item_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        owner_data = data.get("owner", {})
        owner_login = owner_data.get("login", "") if isinstance(owner_data, dict) else str(owner_data)
        return cls(
            number=data.get("number", 0),
            title=data.get("title", ""),
            owner=owner_login,
            url=data.get("url", ""),
            item_count=data.get("items", {}).get("totalCount", 0),
        )


def _parse_datetime(value: str) -> datetime:
    if not value:
        return DATETIME_SENTINEL
    try:
        return datetime.fromisoformat(value)
    except (ValueError, AttributeError):
        return DATETIME_SENTINEL
