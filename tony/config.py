from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import tomli_w

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "cc-task-manager"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class AppConfig:
    github_username: str = ""
    default_state: str = "open"
    max_issues: int = 100
    excluded_orgs: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> AppConfig:
        if not path.exists():
            logger.info(f"No config file found at {path}, using defaults")
            return cls()

        with path.open("rb") as f:
            data = tomllib.load(f)

        return cls(
            github_username=data.get("github_username", ""),
            default_state=data.get("default_state", "open"),
            max_issues=data.get("max_issues", 100),
            excluded_orgs=data.get("excluded_orgs", []),
        )

    def save(self, path: Path = CONFIG_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "github_username": self.github_username,
            "default_state": self.default_state,
            "max_issues": self.max_issues,
            "excluded_orgs": self.excluded_orgs,
        }
        with path.open("wb") as f:
            tomli_w.dump(data, f)
        logger.info(f"Config saved to {path}")

    @property
    def is_configured(self) -> bool:
        return bool(self.github_username)
