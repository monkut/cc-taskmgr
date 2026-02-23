from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Label, Select, Static

if TYPE_CHECKING:
    from tony.models import Project

ALL_OPTION = ("All", "__all__")


class FilterBar(Static):
    can_focus = False

    org: reactive[str] = reactive("__all__")
    project: reactive[str] = reactive("__all__")

    @dataclass
    class Changed(Message):
        org: str
        project_key: str

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._orgs: list[str] = []
        self._projects_by_org: dict[str, list[Project]] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="filter-bar"):
            yield Label("Org:", classes="filter-label")
            yield Select[str](
                [ALL_OPTION],
                prompt="Org",
                id="org-select",
                allow_blank=False,
                value="__all__",
            )
            yield Label("Project:", classes="filter-label")
            yield Select[str](
                [ALL_OPTION],
                prompt="Project",
                id="project-select",
                allow_blank=False,
                value="__all__",
            )

    def update_options(self, orgs: list[str], projects_by_org: dict[str, list[Project]]) -> None:
        self._orgs = sorted(orgs)
        self._projects_by_org = projects_by_org

        org_select = self.query_one("#org-select", Select)
        project_select = self.query_one("#project-select", Select)
        org_options = [ALL_OPTION, *((o, o) for o in self._orgs)]

        with org_select.prevent(Select.Changed), project_select.prevent(Select.Changed):
            org_select.set_options(org_options)
            self._update_project_options()

    def update_projects(self, projects_by_org: dict[str, list[Project]]) -> None:
        """Update project data and refresh the project dropdown without touching org select."""
        self._projects_by_org = projects_by_org
        project_select = self.query_one("#project-select", Select)
        with project_select.prevent(Select.Changed):
            self._update_project_options()

    def _update_project_options(self) -> None:
        project_select = self.query_one("#project-select", Select)

        if self.org == "__all__":
            projects = [p for ps in self._projects_by_org.values() for p in ps]
        else:
            projects = self._projects_by_org.get(self.org, [])

        project_options: list[tuple[str, str]] = [ALL_OPTION]
        for p in sorted(projects, key=lambda x: x.title):
            key = f"{p.owner}/{p.number}"
            project_options.append((p.title, key))
        project_select.set_options(project_options)

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id
        if select_id == "org-select":
            self.org = str(event.value) if event.value is not None else "__all__"
            self.project = "__all__"
            self._update_project_options()
        elif select_id == "project-select":
            self.project = str(event.value) if event.value is not None else "__all__"

        self.post_message(self.Changed(org=self.org, project_key=self.project))
