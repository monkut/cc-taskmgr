from __future__ import annotations

import logging
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Markdown, Static, TextArea

from tony.functions import format_relative_time
from tony.models import Issue

logger = logging.getLogger(__name__)


class IssueDetail(Static):
    @dataclass
    class CommentSubmitted(Message):
        repo: str
        number: int
        body: str

    @dataclass
    class BackRequested(Message):
        pass

    @dataclass
    class ActionRequested(Message):
        issue: Issue

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._issue: Issue | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="detail-toolbar"):
            yield Button("< Back", id="back-btn", variant="default")
            yield Button("Execute Action", id="execute-action-btn", variant="warning")
            yield Static("", id="action-status")
        yield Static("", id="issue-header")
        with VerticalScroll(id="detail-scroll"):
            yield Markdown("", id="issue-body")
            yield Static("", id="comments-section")
        with Vertical(id="comment-form"):
            yield TextArea(id="comment-input")
            yield Button("Add Comment", id="submit-comment", variant="primary")

    def display_issue(self, issue: Issue) -> None:
        self._issue = issue

        header = self.query_one("#issue-header", Static)
        header.update(
            f"[bold]{issue.repository}#{issue.number}[/bold]  {issue.title}\n"
            f"[dim]by {issue.author} · {format_relative_time(issue.created_at)}[/dim]"
        )

        body_widget = self.query_one("#issue-body", Markdown)
        body_widget.update(issue.body or "*No description*")

        comments_section = self.query_one("#comments-section", Static)
        if issue.comments:
            lines = [f"\n[bold]Comments ({len(issue.comments)})[/bold]\n"]
            for comment in issue.comments:
                lines.append(
                    f"[bold]{comment.author}[/bold] · [dim]{format_relative_time(comment.created_at)}[/dim]\n"
                    f"{comment.body}\n"
                    f"{'─' * 40}\n"
                )
            comments_section.update("\n".join(lines))
        else:
            comments_section.update("\n[dim]No comments[/dim]")

        comment_input = self.query_one("#comment-input", TextArea)
        comment_input.clear()

    def set_action_status(self, text: str) -> None:
        status = self.query_one("#action-status", Static)
        status.update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.post_message(self.BackRequested())
            return

        if event.button.id == "execute-action-btn" and self._issue:
            self.post_message(self.ActionRequested(issue=self._issue))
            return

        if event.button.id == "submit-comment" and self._issue:
            comment_input = self.query_one("#comment-input", TextArea)
            body = comment_input.text.strip()
            if body:
                self.post_message(
                    self.CommentSubmitted(
                        repo=self._issue.repository,
                        number=self._issue.number,
                        body=body,
                    )
                )
