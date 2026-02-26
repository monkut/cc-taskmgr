from datetime import UTC, datetime, timedelta

from tony.functions import format_relative_time
from tony.models import DATETIME_SENTINEL
from tony.widgets.in_progress_detail import _format_elapsed


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


class TestFormatElapsed:
    def test_seconds(self):
        assert _format_elapsed(5) == "5s"
        assert _format_elapsed(59) == "59s"

    def test_minutes(self):
        assert _format_elapsed(60) == "1m 00s"
        assert _format_elapsed(125) == "2m 05s"
        assert _format_elapsed(3599) == "59m 59s"

    def test_hours(self):
        assert _format_elapsed(3600) == "1h 00m"
        assert _format_elapsed(7260) == "2h 01m"
