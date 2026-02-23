from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text
from textual.message import Message
from textual.widgets import DataTable

from tony.functions import format_relative_time
from tony.models import Issue


class IssueTable(DataTable):
    @dataclass
    class IssueSelected(Message):
        issue: Issue

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._issues: list[Issue] = []
        self._filtered_issues: list[Issue] = []

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Org", "Repo", "#", "Title", "Labels", "Updated")

    def load_issues(self, issues: list[Issue]) -> None:
        self._issues = issues
        self._filtered_issues = list(issues)
        self._render_rows()

    def filter_issues(self, org: str = "__all__", repo: str = "__all__") -> None:
        self._filtered_issues = [
            issue for issue in self._issues if org in ("__all__", issue.org) and repo in ("__all__", issue.repo)
        ]
        self._render_rows()

    def _render_rows(self) -> None:
        self.clear()
        for issue in self._filtered_issues:
            labels = _render_labels(issue)
            self.add_row(
                issue.org,
                issue.repo,
                str(issue.number),
                Text(issue.title, overflow="ellipsis", no_wrap=True),
                labels,
                format_relative_time(issue.updated_at),
                key=f"{issue.repository}#{issue.number}",
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_idx = event.cursor_row
        if 0 <= row_idx < len(self._filtered_issues):
            self.post_message(self.IssueSelected(issue=self._filtered_issues[row_idx]))

    @property
    def issue_count(self) -> int:
        return len(self._filtered_issues)


def _render_labels(issue: Issue) -> Text:
    label_text = Text()
    for i, label in enumerate(issue.labels):
        color = f"#{label.color}" if label.color else "white"
        try:
            label_text.append(f" {label.name} ", style=f"on {color}")
        except (ValueError, KeyError):
            label_text.append(f" {label.name} ", style="on dark_blue")
        if i < len(issue.labels) - 1:
            label_text.append(" ")
    return label_text
