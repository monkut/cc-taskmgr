from __future__ import annotations

import time
from dataclasses import dataclass

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Button, DataTable, Static

from tony.models import Issue

SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60


@dataclass
class ActionEntry:
    issue: Issue
    mode: str
    started_at: float  # monotonic time
    finished_at: float | None  # None if still running


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a human-readable string."""
    if seconds < SECONDS_PER_MINUTE:
        return f"{int(seconds)}s"
    minutes = int(seconds // SECONDS_PER_MINUTE)
    secs = int(seconds % SECONDS_PER_MINUTE)
    if minutes < MINUTES_PER_HOUR:
        return f"{minutes}m {secs:02d}s"
    hours = minutes // MINUTES_PER_HOUR
    mins = minutes % MINUTES_PER_HOUR
    return f"{hours}h {mins:02d}m"


COLUMNS = ("Project", "Repo", "#", "Title", "Action", "Status", "Elapsed")

COLUMN_WIDTHS: dict[str, int] = {
    "Project": 15,
    "Repo": 20,
    "#": 6,
    "Action": 14,
    "Status": 14,
    "Elapsed": 12,
}


class InProgressDetail(Static):
    """Full-screen detail view of in-progress and recently-finished actions."""

    BINDINGS = [
        Binding("escape", "request_back", "Back", priority=True),
    ]

    class BackRequested(Message):
        pass

    @dataclass
    class IssueSelected(Message):
        issue: Issue

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: list[ActionEntry] = []
        self._elapsed_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="in-progress-detail-toolbar"):
            yield Button("< Back", id="in-progress-back-btn", variant="default")
            yield Static(
                "[bold yellow]In Progress — Detail View[/bold yellow]",
                id="in-progress-detail-title",
            )
        yield DataTable(id="in-progress-table")

    def on_mount(self) -> None:
        table = self.query_one("#in-progress-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        for col in COLUMNS:
            table.add_column(col, key=col, width=COLUMN_WIDTHS.get(col))

    def update_entries(self, entries: list[ActionEntry]) -> None:
        """Replace the displayed entries and re-render the table."""
        self._entries = entries
        self._render_rows()
        if entries and self._elapsed_timer is None:
            self._elapsed_timer = self.set_interval(1, self._tick_elapsed)
        elif not entries and self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None

    def _render_rows(self) -> None:
        table = self.query_one("#in-progress-table", DataTable)
        table.clear()
        now = time.monotonic()
        for entry in self._entries:
            running = entry.finished_at is None
            if running:
                elapsed = now - entry.started_at
                status = Text("running", style="bold green")
            else:
                elapsed = entry.finished_at - entry.started_at
                ago = now - entry.finished_at
                status = Text(f"done ({_format_elapsed(ago)} ago)", style="dim")
            table.add_row(
                entry.issue.org,
                entry.issue.repo,
                str(entry.issue.number),
                Text(entry.issue.title, overflow="ellipsis", no_wrap=True),
                entry.mode,
                status,
                _format_elapsed(elapsed),
                key=f"{entry.issue.repository}#{entry.issue.number}",
            )

    def _tick_elapsed(self) -> None:
        """Refresh the table every second to update elapsed times."""
        self._render_rows()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "in-progress-back-btn":
            self.post_message(self.BackRequested())

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_idx = event.cursor_row
        if 0 <= row_idx < len(self._entries):
            self.post_message(self.IssueSelected(issue=self._entries[row_idx].issue))

    def action_request_back(self) -> None:
        self.post_message(self.BackRequested())

    def on_unmount(self) -> None:
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None
