from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmActionScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, mode: str, repo: str, number: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self._mode = mode
        self._repo = repo
        self._number = number

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-action-dialog"):
            yield Static("Confirm Action", id="confirm-action-title")
            yield Static(
                f"Run [bold]{self._mode}[/bold] on [bold]{self._repo}#{self._number}[/bold]?",
                id="confirm-action-message",
            )
            yield Button("Confirm", id="confirm-btn", variant="primary")
            yield Button("Cancel", id="confirm-cancel-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(self._mode)
        elif event.button.id == "confirm-cancel-btn":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
