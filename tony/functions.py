from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def process(filepath: Path, output_directory: Path) -> None:
    logger.debug(f"filepath={filepath}")
    logger.debug(f"output_directory={output_directory}")
