"""Tests for app.flowhub.config.profiles."""

import pytest

from app.flowhub.config.profiles import ConfigProfile


class TestConfigProfileFromString:
    def test_production_value(self):
        assert ConfigProfile.from_string("production") == ConfigProfile.PRODUCTION

    def test_dev_lower(self):
        assert ConfigProfile.from_string("dev") == ConfigProfile.DEV

    def test_production_lower(self):
        assert ConfigProfile.from_string("production") == ConfigProfile.PRODUCTION

    def test_case_insensitive(self):
        assert ConfigProfile.from_string("production") == ConfigProfile.PRODUCTION
        assert ConfigProfile.from_string("DEV") == ConfigProfile.DEV
        assert ConfigProfile.from_string("PRODUCTION") == ConfigProfile.PRODUCTION

    def test_strips_whitespace(self):
        assert ConfigProfile.from_string("  production  ") == ConfigProfile.PRODUCTION

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="not valid"):
            ConfigProfile.from_string("staging")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            ConfigProfile.from_string("")


class TestConfigProfileMethods:
    def test_is_production(self):
        assert ConfigProfile.PRODUCTION.is_production() is True
        assert ConfigProfile.DEV.is_production() is False

    def test_is_dev(self):
        assert ConfigProfile.DEV.is_dev() is True
        assert ConfigProfile.PRODUCTION.is_dev() is False

    def test_banner_production_exact(self):
        assert ConfigProfile.PRODUCTION.banner() == "[PRODUCTION]"

    def test_banner_dev(self):
        assert ConfigProfile.DEV.banner() == "[LOCAL DEVELOPMENT]"

    def test_banner_production(self):
        assert "[PRODUCTION]" in ConfigProfile.PRODUCTION.banner()

    def test_str_value(self):
        assert ConfigProfile.PRODUCTION.value == "production"
        assert ConfigProfile.DEV.value == "dev"
