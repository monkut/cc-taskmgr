from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from tony.models import Issue


def _extract_action(issue: Issue) -> str:
    """Extract the last action:* label mode from an issue."""
    action_mode = ""
    for label in issue.labels:
        if label.name.startswith("action:"):
            action_mode = label.name.removeprefix("action:")
    return action_mode


class InProgressBar(Widget):
    """Shows issues with action:* labels grouped by repository."""

    class DetailRequested(Message):
        pass

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._issues_by_repo: dict[str, list[tuple[Issue, str]]] = {}
        self._selected_repo: str | None = None
        self._repo_list: list[str] = []
        self._statuses: dict[str, str] = {}  # "owner/repo#number" → column name

    def compose(self) -> ComposeResult:
        with Vertical(id="in-progress-section"):
            yield Static(
                "[bold yellow]In Progress:[/bold yellow]  [dim]None[/dim]",
                id="in-progress-summary",
            )
            yield Static("", id="in-progress-detail")

    def update_issues(self, issues: list[Issue]) -> None:
        """Filter issues with action:* labels and group by repository."""
        self._issues_by_repo = {}
        for issue in issues:
            action_mode = _extract_action(issue)
            if action_mode:
                repo = issue.repository
                self._issues_by_repo.setdefault(repo, []).append((issue, action_mode))

        if self._selected_repo and self._selected_repo not in self._issues_by_repo:
            self._selected_repo = None
        self._repo_list = sorted(self._issues_by_repo)
        self._render_summary()
        self._update_detail()

    def _render_summary(self) -> None:
        summary = self.query_one("#in-progress-summary", Static)
        label = "[@click=open_detail][bold yellow]In Progress:[/bold yellow][/]"
        if not self._repo_list:
            summary.update(f"{label}  [dim]None[/dim]")
            return
        parts = []
        for i, repo in enumerate(self._repo_list):
            count = len(self._issues_by_repo[repo])
            if repo == self._selected_repo:
                parts.append(f"[@click=select_repo({i})][bold reverse] {repo} ({count}) [/bold reverse][/]")
            else:
                parts.append(f"[@click=select_repo({i})][bold] {repo} ({count}) [/bold][/]")
        summary.update(f"{label}  " + "  ".join(parts))

    def action_open_detail(self) -> None:
        self.post_message(self.DetailRequested())

    def action_select_repo(self, index: int) -> None:
        """Handle click on a repo entry in the summary."""
        if index < 0 or index >= len(self._repo_list):
            return
        repo = self._repo_list[index]
        self._selected_repo = None if self._selected_repo == repo else repo
        self._render_summary()
        self._update_detail()

    def update_statuses(self, statuses: dict[str, str]) -> None:
        """Update project column statuses and re-render detail if visible."""
        self._statuses = statuses
        self._update_detail()

    def _update_detail(self) -> None:
        detail = self.query_one("#in-progress-detail", Static)
        if not self._selected_repo or self._selected_repo not in self._issues_by_repo:
            detail.update("")
            detail.display = False
            return

        items = self._issues_by_repo[self._selected_repo]
        lines = []
        for issue, action_mode in items:
            key = f"{issue.repository}#{issue.number}"
            status = self._statuses.get(key, "")
            status_part = f"  [yellow]{status}[/yellow]" if status else ""
            line = (
                f"  [bold]#{issue.number}[/bold]  "
                f"{issue.title}  "
                f"[dim]{action_mode}[/dim]{status_part}  "
                f"[cyan][link={issue.url}]{issue.url}[/link][/cyan]"
            )
            lines.append(line)
        detail.update("\n".join(lines))
        detail.display = True
