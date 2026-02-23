from __future__ import annotations

import asyncio
import logging
import subprocess

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, LoadingIndicator, Static

from tony.config import AppConfig
from tony.github import (
    GitHubRateLimitError,
    add_comment,
    add_label,
    check_gh_auth,
    fetch_issue_detail,
    fetch_issues,
    fetch_project_item_keys,
    fetch_projects,
    find_repo_dir,
)
from tony.models import Issue, Project
from tony.screens.action_select import ActionSelectScreen
from tony.screens.confirm_action import ConfirmActionScreen
from tony.screens.settings import SettingsScreen
from tony.widgets.filters import FilterBar
from tony.widgets.issue_detail import IssueDetail
from tony.widgets.issue_table import SORTABLE_COLUMNS, IssueTable

logger = logging.getLogger(__name__)


def _start_process(cmd: list[str], cwd: str) -> subprocess.Popen:  # noqa: S603
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # noqa: S603


class TonyApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Tony - GitHub Issue Manager"

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("s", "settings", "Settings"),
        ("q", "quit", "Quit"),
        ("escape", "back", "Back"),
    ]

    # Nav zones: 0=org, 1=project, 2..2+N-1=column headers, 2+N=issue rows
    _NAV_ORG = 0
    _NAV_PROJECT = 1
    _NAV_FIRST_COL = 2
    _NAV_ROWS = _NAV_FIRST_COL + len(SORTABLE_COLUMNS)
    _NAV_COUNT = _NAV_ROWS + 1

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = AppConfig.load()
        self._issues: list[Issue] = []
        self._showing_detail = False
        self._projects_by_org: dict[str, list[Project]] = {}
        self._nav_index: int = self._NAV_ROWS
        self._running_actions: dict[str, subprocess.Popen] = {}
        self._running_action_modes: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield FilterBar(id="filters")
        yield IssueTable(id="issue-table")
        yield IssueDetail(id="issue-detail")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#issue-detail", IssueDetail).display = False

        if not check_gh_auth():
            self._set_status("[red]gh CLI not authenticated. Run: gh auth login[/red]")
            return

        if not self._config.is_configured:
            self._prompt_settings()
        else:
            self._load_issues()

    def _prompt_settings(self) -> None:
        def handle_result(result: tuple[str, list[str]] | None) -> None:
            if result:
                username, project_dirs = result
                self._config.github_username = username
                self._config.project_dirs = project_dirs
                self._config.save()
                self._load_issues()
            elif not self._config.is_configured:
                self._set_status("[yellow]Username required to fetch issues[/yellow]")

        self.push_screen(
            SettingsScreen(
                current_username=self._config.github_username,
                current_project_dirs=self._config.project_dirs,
            ),
            callback=handle_result,
        )

    def _load_issues(self) -> None:
        self._set_status("Loading issues...")
        loading = LoadingIndicator(id="loading-indicator")
        table = self.query_one("#issue-table", IssueTable)
        table.display = False
        self.mount(loading, after=self.query_one("#filters"))
        self.run_worker(self._fetch_and_display(), exclusive=True)

    async def _fetch_and_display(self) -> None:
        try:
            await self._do_fetch_and_display()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch and display issues")
            self._cleanup_loading()
            self._set_status("[red]Error loading issues — check logs[/red]")
            self.notify("Error loading issues", severity="error", timeout=10)

    def _cleanup_loading(self) -> None:
        try:
            loading = self.query_one("#loading-indicator", LoadingIndicator)
            loading.remove()
        except (LookupError, ValueError):
            pass
        try:
            table = self.query_one("#issue-table", IssueTable)
            table.display = True
        except (LookupError, ValueError):
            pass

    async def _do_fetch_and_display(self) -> None:
        try:
            issues = await fetch_issues(
                self._config.github_username,
                state=self._config.default_state,
                limit=self._config.max_issues,
            )
        except GitHubRateLimitError:
            self._cleanup_loading()
            self._set_status("[red]GitHub API rate limit exceeded — try again later[/red]")
            self.notify("GitHub API rate limit exceeded — try again later", severity="error", timeout=10)
            return

        self._issues = issues
        self._projects_by_org = {}

        orgs = sorted({i.org for i in issues if i.org})

        self._cleanup_loading()

        table = self.query_one("#issue-table", IssueTable)
        table.display = True
        table.load_issues(issues)

        filter_bar = self.query_one("#filters", FilterBar)
        filter_bar.update_options(orgs, {})

        self._set_status(f"Loaded {len(issues)} issues for {self._config.github_username}")

    def on_filter_bar_changed(self, event: FilterBar.Changed) -> None:
        self._set_status("Filtering...")
        self.run_worker(self._apply_filter(event.org, event.project_key))

    async def _apply_filter(self, org: str, project_key: str) -> None:
        # Lazy-load projects when an org is selected for the first time
        if org != "__all__" and org not in self._projects_by_org:
            try:
                projects = await fetch_projects(org)
                self._projects_by_org[org] = projects
            except GitHubRateLimitError:
                self._set_status("[red]GitHub API rate limit exceeded[/red]")
                self.notify("GitHub API rate limit exceeded", severity="error", timeout=10)
                return

            filter_bar = self.query_one("#filters", FilterBar)
            filter_bar.update_options(
                sorted({i.org for i in self._issues if i.org}),
                self._projects_by_org,
            )

        project_keys: set[str] | None = None
        if project_key != "__all__":
            parts = project_key.split("/", 1)
            if len(parts) > 1:
                owner = parts[0]
                project_number = int(parts[1])
                try:
                    project_keys = await fetch_project_item_keys(owner, project_number)
                except GitHubRateLimitError:
                    self._set_status("[red]GitHub API rate limit exceeded[/red]")
                    self.notify("GitHub API rate limit exceeded", severity="error", timeout=10)
                    return

        table = self.query_one("#issue-table", IssueTable)
        table.filter_issues(org=org, project_keys=project_keys)
        self._set_status(f"Showing {table.issue_count} issues")

    def on_issue_table_issue_selected(self, event: IssueTable.IssueSelected) -> None:
        self._show_detail(event.issue)

    def _show_detail(self, issue: Issue) -> None:
        self._showing_detail = True
        table = self.query_one("#issue-table", IssueTable)
        filters = self.query_one("#filters", FilterBar)
        detail = self.query_one("#issue-detail", IssueDetail)

        table.display = False
        filters.display = False
        detail.display = True
        detail.display_issue(issue)
        self._update_action_status_for_issue(issue)

        self._set_status(f"Fetching details for {issue.repository}#{issue.number}...")
        self.run_worker(self._fetch_detail(issue.repository, issue.number))

    async def _fetch_detail(self, repo: str, number: int) -> None:
        try:
            full_issue = await fetch_issue_detail(repo, number)
        except GitHubRateLimitError:
            self._set_status("[red]GitHub API rate limit exceeded[/red]")
            self.notify("GitHub API rate limit exceeded", severity="error", timeout=10)
            return
        if full_issue:
            detail = self.query_one("#issue-detail", IssueDetail)
            detail.display_issue(full_issue)
            self._set_status(f"{repo}#{number} - {len(full_issue.comments)} comments")

    def on_issue_detail_back_requested(self, _event: IssueDetail.BackRequested) -> None:
        self._show_list()

    def _show_list(self) -> None:
        self._showing_detail = False
        table = self.query_one("#issue-table", IssueTable)
        filters = self.query_one("#filters", FilterBar)
        detail = self.query_one("#issue-detail", IssueDetail)

        detail.display = False
        filters.display = True
        table.display = True

    def on_issue_detail_comment_submitted(self, event: IssueDetail.CommentSubmitted) -> None:
        self._set_status("Posting comment...")
        self.run_worker(self._post_comment(event.repo, event.number, event.body))

    async def _post_comment(self, repo: str, number: int, body: str) -> None:
        try:
            success = await add_comment(repo, number, body)
        except GitHubRateLimitError:
            self._set_status("[red]GitHub API rate limit exceeded[/red]")
            self.notify("GitHub API rate limit exceeded", severity="error", timeout=10)
            return
        if not success:
            self._set_status("[red]Failed to post comment[/red]")
            return
        self._set_status("Comment posted, refreshing...")
        try:
            full_issue = await fetch_issue_detail(repo, number)
        except GitHubRateLimitError:
            self._set_status("[red]Comment posted but rate limited on refresh[/red]")
            self.notify("GitHub API rate limit exceeded", severity="error", timeout=10)
            return
        if full_issue:
            detail = self.query_one("#issue-detail", IssueDetail)
            detail.display_issue(full_issue)
            self._set_status(f"Comment posted on {repo}#{number}")

    def on_issue_detail_action_requested(self, event: IssueDetail.ActionRequested) -> None:
        issue = event.issue
        key = f"{issue.repository}#{issue.number}"
        if key in self._running_actions:
            self.notify("Action already running for this issue", severity="warning")
            return

        def handle_mode(mode: str | None) -> None:
            if mode is None:
                return
            self.push_screen(
                ConfirmActionScreen(mode=mode, repo=issue.repository, number=issue.number),
                callback=lambda confirmed: self._on_action_confirmed(confirmed, issue),
            )

        self.push_screen(ActionSelectScreen(), callback=handle_mode)

    def _on_action_confirmed(self, mode: str | None, issue: Issue) -> None:
        if mode is None:
            return
        self.run_worker(self._execute_action(mode, issue))

    async def _execute_action(self, mode: str, issue: Issue) -> None:
        key = f"{issue.repository}#{issue.number}"

        # Add label
        try:
            await add_label(issue.repository, issue.number, f"action:{mode}")
        except GitHubRateLimitError:
            self.notify("Rate limited adding label", severity="error")
            return

        # Resolve working directory
        repo_dir = find_repo_dir(self._config.project_dirs, issue.repo)
        cwd = str(repo_dir) if repo_dir else None
        if not cwd:
            self.notify(
                f"No project directory found for '{issue.repo}'. Add project dirs in Settings.",
                severity="error",
                timeout=10,
            )
            return

        # Launch subprocess in thread
        cmd = ["askcc", mode, "--github-issue-url", issue.url]
        try:
            proc = await asyncio.to_thread(_start_process, cmd, cwd)
        except FileNotFoundError:
            self.notify("askcc not found — ensure it is installed and on PATH", severity="error")
            return

        self._running_actions[key] = proc
        self._running_action_modes[key] = mode
        self._update_action_status_for_issue(issue)
        self._update_status_bar_actions()
        self._set_status(f"Action '{mode}' started for {key}")

        # Wait for completion in background thread
        await asyncio.to_thread(proc.wait)

        self._running_actions.pop(key, None)
        self._running_action_modes.pop(key, None)
        self._update_action_status_for_issue(issue)
        self._update_status_bar_actions()

        if proc.returncode == 0:
            self.notify(f"Action '{mode}' completed for {key}", severity="information")
        else:
            self.notify(f"Action '{mode}' failed for {key} (exit {proc.returncode})", severity="error")

    def _update_action_status_for_issue(self, issue: Issue) -> None:
        if not self._showing_detail:
            return
        try:
            detail = self.query_one("#issue-detail", IssueDetail)
        except LookupError:
            return
        key = f"{issue.repository}#{issue.number}"
        mode = self._running_action_modes.get(key)
        if mode:
            detail.set_action_status(f"[bold yellow]Action running: {mode}[/bold yellow]")
        else:
            detail.set_action_status("")

    def _update_status_bar_actions(self) -> None:
        count = len(self._running_actions)
        if count > 0:
            suffix = f" | {count} action{'s' if count != 1 else ''} running"
        else:
            suffix = ""
        status = self.query_one("#status-bar", Static)
        current = status.renderable
        text = str(current)
        # Strip any previous action suffix
        if " | " in text and "action" in text.rsplit(" | ", maxsplit=1)[-1]:
            text = text.rsplit(" | ", 1)[0]
        status.update(text + suffix)

    def action_focus_next(self) -> None:
        if self._showing_detail:
            super().action_focus_next()
            return
        self._nav_index = (self._nav_index + 1) % self._NAV_COUNT
        self._apply_nav_focus()

    def action_focus_previous(self) -> None:
        if self._showing_detail:
            super().action_focus_previous()
            return
        self._nav_index = (self._nav_index - 1) % self._NAV_COUNT
        self._apply_nav_focus()

    def _apply_nav_focus(self) -> None:
        table = self.query_one("#issue-table", IssueTable)
        idx = self._nav_index

        if idx == self._NAV_ORG:
            table.show_cursor = False
            table.set_header_focus(None)
            self.query_one("#org-select").focus()
        elif idx == self._NAV_PROJECT:
            table.show_cursor = False
            table.set_header_focus(None)
            self.query_one("#project-select").focus()
        elif idx < self._NAV_ROWS:
            col_idx = idx - self._NAV_FIRST_COL
            table.show_cursor = False
            table.set_header_focus(col_idx)
            table.focus()
        else:
            table.set_header_focus(None)
            table.show_cursor = True
            table.focus()

    def action_refresh(self) -> None:
        if self._showing_detail:
            return
        self._load_issues()

    def action_settings(self) -> None:
        self._prompt_settings()

    def action_back(self) -> None:
        if self._showing_detail:
            self._show_list()

    def _set_status(self, message: str) -> None:
        status = self.query_one("#status-bar", Static)
        status.update(message)


def main() -> None:
    app = TonyApp()
    app.run()


if __name__ == "__main__":
    main()
