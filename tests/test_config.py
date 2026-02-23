import tempfile
from pathlib import Path

from tony.config import AppConfig

DEFAULT_MAX_ISSUES = 100


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.github_username == ""
        assert config.default_state == "open"
        assert config.max_issues == DEFAULT_MAX_ISSUES
        assert config.excluded_orgs == []

    def test_is_configured_false_by_default(self):
        config = AppConfig()
        assert not config.is_configured

    def test_is_configured_true_with_username(self):
        config = AppConfig(github_username="testuser")
        assert config.is_configured

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            custom_max = 50

            config = AppConfig(
                github_username="testuser",
                default_state="open",
                max_issues=custom_max,
                excluded_orgs=["archived-org"],
            )
            config.save(path=config_path)

            loaded = AppConfig.load(path=config_path)
            assert loaded.github_username == "testuser"
            assert loaded.default_state == "open"
            assert loaded.max_issues == custom_max
            assert loaded.excluded_orgs == ["archived-org"]

    def test_load_missing_file(self):
        config = AppConfig.load(path=Path("/nonexistent/config.toml"))
        assert config.github_username == ""
        assert config.is_configured is False
