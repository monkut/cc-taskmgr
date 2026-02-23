from __future__ import annotations

import asyncio
import logging

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, LoadingIndicator, Static

from tony.config import AppConfig
from tony.github import (
    GitHubRateLimitError,
    add_comment,
    check_gh_auth,
    fetch_issue_detail,
    fetch_issues,
    fetch_project_item_keys,
    fetch_projects,
)
from tony.models import Issue, Project
from tony.screens.settings import SettingsScreen
from tony.widgets.filters import FilterBar
from tony.widgets.issue_detail import IssueDetail
from tony.widgets.issue_table import IssueTable

logger = logging.getLogger(__name__)


class TonyApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Tony - GitHub Issue Manager"

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("s", "settings", "Settings"),
        ("q", "quit", "Quit"),
        ("escape", "back", "Back"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = AppConfig.load()
        self._issues: list[Issue] = []
        self._showing_detail = False
        self._projects_by_org: dict[str, list[Project]] = {}

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
        def handle_result(username: str | None) -> None:
            if username:
                self._config.github_username = username
                self._config.save()
                self._load_issues()
            elif not self._config.is_configured:
                self._set_status("[yellow]Username required to fetch issues[/yellow]")

        self.push_screen(
            SettingsScreen(current_username=self._config.github_username),
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
        rate_limited = False

        try:
            issues = await fetch_issues(
                self._config.github_username,
                state=self._config.default_state,
                limit=self._config.max_issues,
            )
        except GitHubRateLimitError:
            issues = []
            rate_limited = True

        self._issues = issues

        orgs = sorted({i.org for i in issues if i.org})
        issue_keys = {f"{i.repository}#{i.number}" for i in issues}

        self._projects_by_org = {}
        if not rate_limited:
            try:
                org_projects = await asyncio.gather(*(fetch_projects(org) for org in orgs))
                for org, projects in zip(orgs, org_projects, strict=True):
                    if not projects:
                        continue
                    item_keys_list = await asyncio.gather(*(fetch_project_item_keys(org, p.number) for p in projects))
                    relevant = [p for p, keys in zip(projects, item_keys_list, strict=True) if keys & issue_keys]
                    if relevant:
                        self._projects_by_org[org] = relevant
            except GitHubRateLimitError:
                rate_limited = True

        self._cleanup_loading()

        table = self.query_one("#issue-table", IssueTable)
        table.display = True
        table.load_issues(issues)

        filter_bar = self.query_one("#filters", FilterBar)
        filter_bar.update_options(orgs, self._projects_by_org)

        if rate_limited:
            self._set_status("[red]GitHub API rate limit exceeded — try again later[/red]")
            self.notify("GitHub API rate limit exceeded — try again later", severity="error", timeout=10)
        else:
            self._set_status(f"Loaded {len(issues)} issues for {self._config.github_username}")

    def on_filter_bar_changed(self, event: FilterBar.Changed) -> None:
        self._set_status("Filtering...")
        self.run_worker(self._apply_filter(event.org, event.project_key))

    async def _apply_filter(self, org: str, project_key: str) -> None:
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

        self._set_status(f"Fetching details for {issue.repository}#{issue.number}...")
        self.run_worker(self._fetch_detail(issue.repository, issue.number))

    async def _fetch_detail(self, repo: str, number: int) -> None:
        full_issue = await fetch_issue_detail(repo, number)
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
        success = await add_comment(repo, number, body)
        if success:
            self._set_status("Comment posted, refreshing...")
            full_issue = await fetch_issue_detail(repo, number)
            if full_issue:
                detail = self.query_one("#issue-detail", IssueDetail)
                detail.display_issue(full_issue)
                self._set_status(f"Comment posted on {repo}#{number}")
        else:
            self._set_status("[red]Failed to post comment[/red]")

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
