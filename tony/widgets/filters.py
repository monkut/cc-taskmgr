from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Select, Static

ALL_OPTION = ("All", "__all__")


class FilterBar(Static):
    org: reactive[str] = reactive("__all__")
    repo: reactive[str] = reactive("__all__")

    @dataclass
    class Changed(Message):
        org: str
        repo: str

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._orgs: list[str] = []
        self._repos_by_org: dict[str, list[str]] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="filter-bar"):
            yield Select[str](
                [ALL_OPTION],
                prompt="Org",
                id="org-select",
                allow_blank=False,
                value="__all__",
            )
            yield Select[str](
                [ALL_OPTION],
                prompt="Repo",
                id="repo-select",
                allow_blank=False,
                value="__all__",
            )

    def update_options(self, orgs: list[str], repos_by_org: dict[str, list[str]]) -> None:
        self._orgs = sorted(orgs)
        self._repos_by_org = repos_by_org

        org_select = self.query_one("#org-select", Select)
        org_options = [ALL_OPTION, *((o, o) for o in self._orgs)]
        org_select.set_options(org_options)

        self._update_repo_options()

    def _update_repo_options(self) -> None:
        repo_select = self.query_one("#repo-select", Select)

        if self.org == "__all__":
            all_repos = sorted({r for repos in self._repos_by_org.values() for r in repos})
        else:
            all_repos = sorted(self._repos_by_org.get(self.org, []))

        repo_options = [ALL_OPTION, *((r, r) for r in all_repos)]
        repo_select.set_options(repo_options)

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id
        if select_id == "org-select":
            self.org = str(event.value) if event.value is not None else "__all__"
            self.repo = "__all__"
            self._update_repo_options()
        elif select_id == "repo-select":
            self.repo = str(event.value) if event.value is not None else "__all__"

        self.post_message(self.Changed(org=self.org, repo=self.repo))
