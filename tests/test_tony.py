from datetime import UTC, datetime, timedelta

from tony.functions import format_relative_time
from tony.models import DATETIME_SENTINEL


class TestFormatRelativeTime:
    def test_empty_datetime(self):
        result = format_relative_time(DATETIME_SENTINEL)
        assert result == ""

    def test_just_now(self):
        now = datetime.now(UTC)
        result = format_relative_time(now)
        assert result == "just now"

    def test_minutes_ago(self):
        dt = datetime.now(UTC) - timedelta(minutes=5)
        result = format_relative_time(dt)
        assert result == "5m ago"

    def test_hours_ago(self):
        dt = datetime.now(UTC) - timedelta(hours=3)
        result = format_relative_time(dt)
        assert result == "3h ago"

    def test_days_ago(self):
        dt = datetime.now(UTC) - timedelta(days=7)
        result = format_relative_time(dt)
        assert result == "7d ago"

    def test_naive_datetime_treated_as_utc(self):
        dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
        result = format_relative_time(dt)
        assert "h ago" in result
