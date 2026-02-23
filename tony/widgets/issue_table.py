from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from operator import attrgetter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable

from tony.functions import format_relative_time
from tony.models import DATETIME_SENTINEL, Issue

COLUMNS = ("Repo", "#", "Title", "Labels", "Updated")

COLUMN_WIDTHS: dict[str, int] = {
    "Repo": 20,
    "#": 6,
    "Labels": 20,
    "Updated": 22,
}

SORT_KEY_MAP: dict[str, str] = {
    "Repo": "repo",
    "#": "number",
    "Title": "title",
    "Updated": "updated_at",
}

SORTABLE_COLUMNS = [col for col in COLUMNS if col in SORT_KEY_MAP]


class IssueTable(DataTable):
    BINDINGS = [
        Binding("enter", "activate", "Open", priority=True, show=True),
    ]

    @dataclass
    class IssueSelected(Message):
        issue: Issue

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._issues: list[Issue] = []
        self._filtered_issues: list[Issue] = []
        self._sort_column: str = "Updated"
        self._sort_reverse: bool = True
        self._project_issue_keys: set[str] | None = None
        self._focused_header: int | None = None

    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        for col in COLUMNS:
            self.add_column(self._build_column_label(col), key=col, width=COLUMN_WIDTHS.get(col))

    def _build_column_label(self, col: str) -> Text:
        arrow = ""
        if col == self._sort_column:
            arrow = " ▼" if self._sort_reverse else " ▲"
        label_str = f"{col}{arrow}"
        focused_idx = self._focused_header
        is_focused = focused_idx is not None and SORTABLE_COLUMNS[focused_idx] == col
        if is_focused:
            return Text(f"▸{label_str}◂", style="bold yellow")
        return Text(label_str)

    def load_issues(self, issues: list[Issue]) -> None:
        self._issues = issues
        self._filtered_issues = list(issues)
        self._apply_sort()
        self._render_rows()

    def filter_issues(self, org: str = "__all__", project_keys: set[str] | None = None) -> None:
        filtered = self._issues
        if org != "__all__":
            filtered = [i for i in filtered if i.org == org]
        if project_keys is not None:
            filtered = [i for i in filtered if f"{i.repository}#{i.number}" in project_keys]
        self._filtered_issues = filtered
        self._apply_sort()
        self._render_rows()

    def sort_by(self, column: str) -> None:
        if column not in SORT_KEY_MAP:
            return
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column == "Updated"
        self._update_column_labels()
        self._apply_sort()
        self._render_rows()

    def _apply_sort(self) -> None:
        attr = SORT_KEY_MAP.get(self._sort_column)
        if not attr:
            return
        self._filtered_issues.sort(key=attrgetter(attr), reverse=self._sort_reverse)

    def _update_column_labels(self) -> None:
        for col in COLUMNS:
            column_obj = self.columns.get(col)
            if column_obj:
                column_obj.label = self._build_column_label(col)
        self._update_count += 1
        self._clear_caches()
        self.refresh()

    def _render_rows(self) -> None:
        self.clear()
        for issue in self._filtered_issues:
            labels = _render_labels(issue)
            updated = _format_updated(issue.updated_at)
            self.add_row(
                issue.repo,
                str(issue.number),
                Text(issue.title, overflow="ellipsis", no_wrap=True),
                labels,
                updated,
                key=f"{issue.repository}#{issue.number}",
            )

    def set_header_focus(self, index: int | None) -> None:
        self._focused_header = index
        self._update_column_labels()
        self._update_enter_binding()

    def _update_enter_binding(self) -> None:
        desc = "Sort" if self._focused_header is not None else "Open"
        bindings = self._bindings.key_to_bindings.get("enter", [])
        for i, binding in enumerate(bindings):
            if binding.action == "activate":
                bindings[i] = dataclasses.replace(binding, description=desc)
                break
        self.refresh_bindings()

    def action_activate(self) -> None:
        if self._focused_header is not None:
            self.sort_by(SORTABLE_COLUMNS[self._focused_header])
        else:
            row_idx = self.cursor_row
            if 0 <= row_idx < len(self._filtered_issues):
                self.post_message(self.IssueSelected(issue=self._filtered_issues[row_idx]))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = str(event.column_key)
        self.sort_by(col_key)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._focused_header is not None:
            return
        row_idx = event.cursor_row
        if 0 <= row_idx < len(self._filtered_issues):
            self.post_message(self.IssueSelected(issue=self._filtered_issues[row_idx]))

    @property
    def issue_count(self) -> int:
        return len(self._filtered_issues)


def _format_updated(dt: datetime) -> Text:
    if dt == DATETIME_SENTINEL:
        return Text("")
    date_str = dt.strftime("%Y-%m-%d %H:%M")
    relative = format_relative_time(dt)
    return Text(f"{date_str}  {relative}")


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
