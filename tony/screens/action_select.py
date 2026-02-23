from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

ASKCC_MODES = ["plan", "develop", "review", "explore", "diagnose"]


class ActionSelectScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="action-select-dialog"):
            yield Static("Select Action Mode", id="action-select-title")
            for mode in ASKCC_MODES:
                yield Button(mode.capitalize(), id=f"mode-{mode}", variant="primary")
            yield Button("Cancel", id="action-cancel-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "action-cancel-btn":
            self.dismiss(None)
            return
        if event.button.id and event.button.id.startswith("mode-"):
            mode = event.button.id.removeprefix("mode-")
            self.dismiss(mode)

    def action_cancel(self) -> None:
        self.dismiss(None)
