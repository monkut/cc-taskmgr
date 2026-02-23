from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class SettingsScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    @dataclass
    class Saved(Message):
        username: str

    def __init__(self, current_username: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_username = current_username

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Static("Settings", id="settings-title")
            yield Label("GitHub Username:")
            yield Input(
                value=self._current_username,
                placeholder="Enter your GitHub username",
                id="username-input",
            )
            yield Button("Save", variant="primary", id="save-btn")
            yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            username_input = self.query_one("#username-input", Input)
            username = username_input.value.strip()
            if username:
                self.dismiss(username)
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        username_input = self.query_one("#username-input", Input)
        username = username_input.value.strip()
        if username:
            self.dismiss(username)

    def action_cancel(self) -> None:
        self.dismiss(None)
