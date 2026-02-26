from __future__ import annotations

import asyncio
import logging
import subprocess
import time

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, LoadingIndicator, Static

from tony.config import AppConfig
from tony.github import (
    GitHubRateLimitError,
    add_comment,
    add_label,
    check_gh_auth,
    fetch_issue_detail,
    fetch_issue_project_status,
    fetch_issues,
    fetch_project_item_keys,
    fetch_projects,
    find_repo_dir,
    is_in_review_status,
)
from tony.models import Issue, Project
from tony.screens.action_select import ActionSelectScreen
from tony.screens.confirm_action import ConfirmActionScreen
from tony.screens.settings import SettingsScreen
from tony.widgets.filters import FilterBar
from tony.widgets.in_progress import InProgressBar
from tony.widgets.in_progress_detail import ActionEntry, InProgressDetail
from tony.widgets.issue_detail import IssueDetail
from tony.widgets.issue_table import SORTABLE_COLUMNS, IssueTable

logger = logging.getLogger(__name__)


def _start_process(cmd: list[str], cwd: str) -> subprocess.Popen:  # noqa: S603
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # noqa: S603


class TonyApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Tony - GitHub Issue Manager"

    BINDINGS = [
        Binding("up", "issue_up", show=False, priority=True),
        Binding("down", "issue_down", show=False, priority=True),
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
        self._action_start_times: dict[str, float] = {}
        self._action_issues: dict[str, Issue] = {}
        self._recently_finished: dict[str, tuple[str, float]] = {}  # key → (mode, finished_monotonic)
        self._showing_in_progress: bool = False
        self._initial_load_done: bool = False
        self._status_text: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield FilterBar(id="filters")
        yield InProgressBar(id="in-progress")
        yield IssueTable(id="issue-table")
        yield IssueDetail(id="issue-detail")
        yield InProgressDetail(id="in-progress-detail")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#issue-detail", IssueDetail).display = False
        self.query_one("#in-progress-detail", InProgressDetail).display = False

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

        # Eagerly fetch projects for all orgs so the project filter is populated
        for org in orgs:
            try:
                self._projects_by_org[org] = await fetch_projects(org)
            except GitHubRateLimitError:
                logger.warning(f"Rate limited fetching projects for {org}")

        self._cleanup_loading()

        table = self.query_one("#issue-table", IssueTable)
        table.display = True
        table.load_issues(issues)

        filter_bar = self.query_one("#filters", FilterBar)
        filter_bar.update_options(orgs, self._projects_by_org)

        in_progress = self.query_one("#in-progress", InProgressBar)
        in_progress.update_issues(issues)

        self._initial_load_done = True
        self._set_status(f"Loaded {len(issues)} issues for {self._config.github_username}")

        # Start polling for in-progress issue status
        self.set_interval(60, self._poll_in_progress_status)

    def on_filter_bar_changed(self, event: FilterBar.Changed) -> None:
        if not self._initial_load_done:
            return
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
            filter_bar.update_projects(self._projects_by_org)

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
        if table.issue_count == 0:
            self.notify("No 'assigned' issues for selected filters", severity="warning")
        self._set_status(f"Showing {table.issue_count} issues")

    def on_issue_table_issue_selected(self, event: IssueTable.IssueSelected) -> None:
        self._show_detail(event.issue)

    def _show_detail(self, issue: Issue) -> None:
        self._showing_detail = True
        self._showing_in_progress = False
        table = self.query_one("#issue-table", IssueTable)
        filters = self.query_one("#filters", FilterBar)
        in_progress = self.query_one("#in-progress", InProgressBar)
        ip_detail = self.query_one("#in-progress-detail", InProgressDetail)
        detail = self.query_one("#issue-detail", IssueDetail)

        table.display = False
        filters.display = False
        in_progress.display = False
        ip_detail.display = False
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
        in_progress = self.query_one("#in-progress", InProgressBar)
        detail = self.query_one("#issue-detail", IssueDetail)

        detail.display = False
        in_progress.display = True
        in_progress.update_issues(self._issues)
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
        if self._running_actions:
            running_key = next(iter(self._running_actions))
            self.notify(f"Action already running for {running_key}", severity="warning")
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
        if mode == "automated":
            self.run_worker(self._execute_automated(issue))
        else:
            self.run_worker(self._execute_action(mode, issue))

    def _resolve_action_cwd(self, issue: Issue) -> str | None:
        repo_dir = find_repo_dir(self._config.project_dirs, issue.repo)
        if not repo_dir:
            self.notify(
                f"Related repository, {issue.repository}, NOT found, cannot run EXECUTE ACTION",
                severity="error",
                timeout=10,
            )
            return None
        return str(repo_dir)

    async def _execute_action(self, mode: str, issue: Issue) -> None:
        key = f"{issue.repository}#{issue.number}"

        # Add label
        try:
            await add_label(issue.repository, issue.number, f"action:{mode}")
        except GitHubRateLimitError:
            self.notify("Rate limited adding label", severity="error")
            return

        cwd = self._resolve_action_cwd(issue)
        if not cwd:
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
        self._action_start_times[key] = time.monotonic()
        self._action_issues[key] = issue
        self._update_action_status_for_issue(issue)
        self._update_status_bar_actions()
        self._sync_table_running_actions()
        self._set_status(f"Action '{mode}' started for {key}")

        # Wait for completion in background thread
        await asyncio.to_thread(proc.wait)

        finished_mode = self._running_action_modes.pop(key, mode)
        self._running_actions.pop(key, None)
        self._recently_finished[key] = (finished_mode, time.monotonic())
        self._update_action_status_for_issue(issue)
        self._update_status_bar_actions()
        self._sync_table_running_actions()

        if proc.returncode == 0:
            self.notify(f"Action '{mode}' completed for {key}", severity="information")
        else:
            self.notify(f"Action '{mode}' failed for {key} (exit {proc.returncode})", severity="error")

    async def _execute_automated(self, issue: Issue) -> None:
        """Run askcc steps (plan → develop → review) sequentially, stopping at review status."""
        key = f"{issue.repository}#{issue.number}"
        steps = ["plan", "develop", "review"]

        # Add label
        try:
            await add_label(issue.repository, issue.number, "action:automated")
        except GitHubRateLimitError:
            self.notify("Rate limited adding label", severity="error")
            return

        cwd = self._resolve_action_cwd(issue)
        if not cwd:
            return

        self._action_start_times[key] = time.monotonic()
        self._action_issues[key] = issue

        for step in steps:
            # Check if already in review before starting step
            try:
                in_review = await asyncio.to_thread(is_in_review_status, issue.org, issue.repo, issue.number)
            except GitHubRateLimitError:
                in_review = False
            if in_review:
                self.notify(f"Issue {key} reached review status, stopping automated action", severity="information")
                break

            # Update tracking to show current step
            self._running_action_modes[key] = f"auto: {step}"
            self._update_action_status_for_issue(issue)
            self._update_status_bar_actions()
            self._sync_table_running_actions()

            cmd = ["askcc", step, "--github-issue-url", issue.url]
            try:
                proc = await asyncio.to_thread(_start_process, cmd, cwd)
            except FileNotFoundError:
                self.notify("askcc not found — ensure it is installed and on PATH", severity="error")
                break

            self._running_actions[key] = proc
            self._set_status(f"Automated '{step}' started for {key}")

            await asyncio.to_thread(proc.wait)
            self._running_actions.pop(key, None)

            if proc.returncode != 0:
                self.notify(f"Automated step '{step}' failed for {key} (exit {proc.returncode})", severity="error")
                break

            # Check project status after step completes
            try:
                in_review = await asyncio.to_thread(is_in_review_status, issue.org, issue.repo, issue.number)
            except GitHubRateLimitError:
                in_review = False
            if in_review:
                self.notify(f"Issue {key} reached review status after '{step}'", severity="information")
                break

        # Cleanup
        self._running_actions.pop(key, None)
        finished_mode = self._running_action_modes.pop(key, "automated")
        self._recently_finished[key] = (finished_mode, time.monotonic())
        self._update_action_status_for_issue(issue)
        self._update_status_bar_actions()
        self._sync_table_running_actions()
        self._set_status(f"Automated action completed for {key}")

    async def _poll_in_progress_status(self) -> None:
        """Fetch project column status for in-progress issues and update the bar."""
        in_progress = self.query_one("#in-progress", InProgressBar)
        action_issues: list[Issue] = []
        for issue in self._issues:
            for label in issue.labels:
                if label.name.startswith("action:"):
                    action_issues.append(issue)
                    break

        if not action_issues:
            return

        statuses: dict[str, str] = {}
        for issue in action_issues:
            try:
                project_statuses = await fetch_issue_project_status(issue.org, issue.repo, issue.number)
                if project_statuses:
                    statuses[f"{issue.repository}#{issue.number}"] = project_statuses[0]
            except GitHubRateLimitError:
                logger.warning(f"Rate limited polling status for {issue.repository}#{issue.number}")

        in_progress.update_statuses(statuses)

    def _build_action_entries(self) -> list[ActionEntry]:
        """Build list of running + recently-finished (<=30 min) action entries."""
        now = time.monotonic()
        cutoff = now - 30 * 60
        entries: list[ActionEntry] = []

        # Running actions
        for key, mode in self._running_action_modes.items():
            issue = self._action_issues.get(key)
            if issue:
                entries.append(
                    ActionEntry(
                        issue=issue,
                        mode=mode,
                        started_at=self._action_start_times.get(key, now),
                        finished_at=None,
                    )
                )

        # Recently finished
        expired = []
        for key, (mode, finished_at) in self._recently_finished.items():
            if finished_at < cutoff:
                expired.append(key)
                continue
            issue = self._action_issues.get(key)
            if issue:
                entries.append(
                    ActionEntry(
                        issue=issue,
                        mode=mode,
                        started_at=self._action_start_times.get(key, finished_at),
                        finished_at=finished_at,
                    )
                )

        # Clean up expired entries
        for key in expired:
            self._recently_finished.pop(key)
            self._action_issues.pop(key, None)
            self._action_start_times.pop(key, None)

        return entries

    def on_in_progress_bar_detail_requested(self, _event: InProgressBar.DetailRequested) -> None:
        self._show_in_progress_detail()

    def _show_in_progress_detail(self) -> None:
        self._showing_in_progress = True
        table = self.query_one("#issue-table", IssueTable)
        filters = self.query_one("#filters", FilterBar)
        in_progress = self.query_one("#in-progress", InProgressBar)
        detail = self.query_one("#in-progress-detail", InProgressDetail)

        table.display = False
        filters.display = False
        in_progress.display = False
        detail.display = True
        detail.update_entries(self._build_action_entries())
        self._set_status("In Progress — Detail View")

    def on_in_progress_detail_back_requested(self, _event: InProgressDetail.BackRequested) -> None:
        self._show_list_from_in_progress()

    def on_in_progress_detail_issue_selected(self, event: InProgressDetail.IssueSelected) -> None:
        self._show_list_from_in_progress()
        self._show_detail(event.issue)

    def _show_list_from_in_progress(self) -> None:
        self._showing_in_progress = False
        detail = self.query_one("#in-progress-detail", InProgressDetail)
        table = self.query_one("#issue-table", IssueTable)
        filters = self.query_one("#filters", FilterBar)
        in_progress = self.query_one("#in-progress", InProgressBar)

        detail.display = False
        in_progress.display = True
        in_progress.update_issues(self._issues)
        filters.display = True
        table.display = True

    def _update_action_status_for_issue(self, issue: Issue) -> None:
        if not self._showing_detail:
            return
        try:
            detail = self.query_one("#issue-detail", IssueDetail)
        except LookupError:
            return
        key = f"{issue.repository}#{issue.number}"
        mode = self._running_action_modes.get(key)
        detail.set_action_status(mode or "")

    def _sync_table_running_actions(self) -> None:
        try:
            table = self.query_one("#issue-table", IssueTable)
            table.set_running_actions(set(self._running_action_modes.keys()))
        except LookupError:
            pass

    def _update_status_bar_actions(self) -> None:
        self._render_status_bar()

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

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ("issue_up", "issue_down"):
            return not self._showing_detail and not self._showing_in_progress
        return True

    def action_issue_up(self) -> None:
        table = self.query_one("#issue-table", IssueTable)
        if self._nav_index != self._NAV_ROWS:
            self._nav_index = self._NAV_ROWS
            self._apply_nav_focus()
        table.action_cursor_up()

    def action_issue_down(self) -> None:
        table = self.query_one("#issue-table", IssueTable)
        if self._nav_index != self._NAV_ROWS:
            self._nav_index = self._NAV_ROWS
            self._apply_nav_focus()
        table.action_cursor_down()

    def action_back(self) -> None:
        if self._showing_detail:
            self._show_list()
        elif self._showing_in_progress:
            self._show_list_from_in_progress()

    def _set_status(self, message: str) -> None:
        self._status_text = message
        self._render_status_bar()

    def _render_status_bar(self) -> None:
        count = len(self._running_actions)
        suffix = f" | {count} action{'s' if count != 1 else ''} running" if count > 0 else ""
        status = self.query_one("#status-bar", Static)
        status.update(self._status_text + suffix)


def main() -> None:
    app = TonyApp()
    app.run()


if __name__ == "__main__":
    main()
