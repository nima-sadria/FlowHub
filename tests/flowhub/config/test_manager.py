"""Tests for app.flowhub.config.manager (ConfigurationManager integration)."""

import sys

import pytest

from app.flowhub.config.manager import ConfigurationManager, NotLoadedError, NotValidError
from app.flowhub.config.profiles import ConfigProfile


class TestManagerLoad:
    def test_load_from_env_vars(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        assert manager._loaded is True

    def test_load_from_env_file(self, valid_env, tmp_path, monkeypatch):
        # Remove FLOWHUB_DOMAIN from process env so the file value is used
        monkeypatch.delenv("FLOWHUB_DOMAIN", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("FLOWHUB_DOMAIN=from_env_file\n", encoding="utf-8")
        manager = ConfigurationManager(env_file=env_file, check_paths=False)
        manager.load()
        assert manager._env.get("FLOWHUB_DOMAIN") == "from_env_file"

    def test_load_twice_resets_state(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        result1 = manager.validate()
        # Mutate and reload
        monkeypatch.setenv("FLOWHUB_ENV", "dev")
        manager.load()
        assert manager._validation_result is None  # reset
        assert manager._config is None

    def test_defaults_applied_after_load(self, valid_env, monkeypatch):
        valid_env.pop("FLOWHUB_LOG_LEVEL", None)
        monkeypatch.delenv("FLOWHUB_LOG_LEVEL", raising=False)
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        assert manager._env.get("FLOWHUB_LOG_LEVEL") == "INFO"

    def test_plugin_dir_default_computed(self, valid_env, monkeypatch):
        valid_env.pop("FLOWHUB_PLUGIN_DIR", None)
        monkeypatch.delenv("FLOWHUB_PLUGIN_DIR", raising=False)
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        expected = valid_env["FLOWHUB_STORAGE_PATH"] + "/plugins"
        assert manager._env.get("FLOWHUB_PLUGIN_DIR") == expected


class TestManagerValidate:
    def test_validate_returns_valid_result(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        result = manager.validate()
        assert result.is_valid, result.format_errors()

    def test_validate_returns_errors_for_missing_fields(self, monkeypatch):
        monkeypatch.delenv("FLOWHUB_DOMAIN", raising=False)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        result = manager.validate()
        assert not result.is_valid
        assert any(e.field == "FLOWHUB_DOMAIN" for e in result.errors)

    def test_validate_auto_loads_if_not_loaded(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        # Don't call load() - validate() should auto-load
        result = manager.validate()
        assert manager._loaded is True

    def test_validate_never_raises(self, monkeypatch):
        monkeypatch.delenv("FLOWHUB_ENV", raising=False)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        result = manager.validate()  # should not raise even with invalid data
        assert result is not None


class TestManagerGet:
    def test_get_returns_FLOWHUB_config(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        manager.validate()
        config = manager.get()
        assert config.domain == "test.example.com"
        assert config.port == 8080

    def test_get_raises_not_loaded_before_load(self):
        manager = ConfigurationManager(check_paths=False)
        with pytest.raises(NotLoadedError):
            manager.get()

    def test_get_raises_not_valid_after_invalid_env(self, monkeypatch):
        monkeypatch.delenv("FLOWHUB_DOMAIN", raising=False)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        manager.validate()
        with pytest.raises(NotValidError):
            manager.get()

    def test_get_auto_validates_if_validate_not_called(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        # No validate() call - get() should auto-validate
        config = manager.get()
        assert config is not None

    def test_get_caches_config_object(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        manager.validate()
        config1 = manager.get()
        config2 = manager.get()
        assert config1 is config2


class TestManagerSet:
    def test_set_updates_env_dict(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        manager.set("FLOWHUB_DOMAIN", "new.example.com")
        assert manager._env["FLOWHUB_DOMAIN"] == "new.example.com"

    def test_set_invalidates_cached_config(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        manager.validate()
        manager.get()  # cache config
        assert manager._config is not None
        manager.set("FLOWHUB_DOMAIN", "changed.example.com")
        assert manager._config is None
        assert manager._validation_result is None


class TestManagerVerify:
    def test_verify_returns_empty_when_no_config_file(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        drifts = manager.verify()
        assert drifts == []

    def test_verify_detects_drift(self, valid_env, tmp_path, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("FLOWHUB_ENV", "production")
        config_toml = tmp_path / "config.toml"
        config_toml.write_text(
            '[meta]\nversion = "FLOWHUB-1.0.0"\n[app]\nenv = "dev"\n',
            encoding="utf-8",
        )
        manager = ConfigurationManager(
            config_file=config_toml,
            check_paths=False,
        )
        manager.load()
        drifts = manager.verify()
        assert any("FLOWHUB_ENV" in d for d in drifts)


class TestManagerProfile:
    def test_profile_returns_FLOWHUB(self, valid_env, monkeypatch):
        monkeypatch.setenv("FLOWHUB_ENV", "production")
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        assert manager.profile() == ConfigProfile.PRODUCTION

    def test_profile_returns_dev(self, monkeypatch):
        monkeypatch.setenv("FLOWHUB_ENV", "dev")
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        assert manager.profile() == ConfigProfile.DEV

    def test_profile_auto_loads(self, monkeypatch):
        monkeypatch.setenv("FLOWHUB_ENV", "production")
        manager = ConfigurationManager(check_paths=False)
        profile = manager.profile()  # should auto-load
        assert manager._loaded is True
        assert profile == ConfigProfile.PRODUCTION


class TestManagerMigrate:
    def test_migrate_returns_empty_when_no_config_file(self, valid_env, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        manager = ConfigurationManager(check_paths=False)
        manager.load()
        changes = manager.migrate()
        assert changes == []

    def test_migrate_adds_version_to_missing_meta(self, valid_env, tmp_path, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        config_toml = tmp_path / "config.toml"
        config_toml.write_text('[app]\nenv = "production"\n', encoding="utf-8")
        manager = ConfigurationManager(
            config_file=config_toml,
            check_paths=False,
        )
        manager.load()
        changes = manager.migrate()
        assert len(changes) == 1
        assert "meta.version" in changes[0]


class TestManagerTomlConfigFile:
    def test_loads_toml_config_and_expands_template_variables(self, valid_env, tmp_path, monkeypatch):
        for k, v in valid_env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("FLOWHUB_ENV", "production")
        toml_content = '[meta]\nversion = "FLOWHUB-1.0.0"\n[app]\nenv = "${FLOWHUB_ENV}"\n'
        config_toml = tmp_path / "config.toml"
        config_toml.write_text(toml_content, encoding="utf-8")
        manager = ConfigurationManager(
            config_file=config_toml,
            check_paths=False,
        )
        manager.load()
        # The toml should have been expanded
        assert manager._config_dict.get("app", {}).get("env") == "production"
