from __future__ import annotations

from datetime import UTC, datetime

from tony.models import DATETIME_SENTINEL

_TIME_THRESHOLDS = [
    (31536000, "y"),
    (2592000, "mo"),
    (86400, "d"),
    (3600, "h"),
    (60, "m"),
]


def format_relative_time(dt: datetime) -> str:
    if dt == DATETIME_SENTINEL:
        return ""

    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    seconds = int((now - dt).total_seconds())

    for threshold, suffix in _TIME_THRESHOLDS:
        if seconds >= threshold:
            return f"{seconds // threshold}{suffix} ago"

    return "just now"
