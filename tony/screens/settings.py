from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, TextArea


class SettingsScreen(ModalScreen[tuple[str, list[str]] | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    @dataclass
    class Saved(Message):
        username: str

    def __init__(
        self,
        current_username: str = "",
        current_project_dirs: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._current_username = current_username
        self._current_project_dirs = current_project_dirs or []

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")
            yield Label("GitHub Username:")
            yield Input(
                value=self._current_username,
                placeholder="Enter your GitHub username",
                id="username-input",
            )
            yield Label("Project Directories (one per line):")
            yield TextArea(
                "\n".join(self._current_project_dirs),
                id="project-dirs-input",
            )
            yield Button("Save", variant="primary", id="save-btn")
            yield Button("Cancel", variant="default", id="cancel-btn")

    def _get_result(self) -> tuple[str, list[str]] | None:
        username = self.query_one("#username-input", Input).value.strip()
        if not username:
            return None
        dirs_text = self.query_one("#project-dirs-input", TextArea).text
        project_dirs = [d.strip() for d in dirs_text.splitlines() if d.strip()]
        return (username, project_dirs)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            result = self._get_result()
            if result:
                self.dismiss(result)
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        result = self._get_result()
        if result:
            self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)
