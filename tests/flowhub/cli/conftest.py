"""Shared fixtures for CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest


_VALID_ENV_CONTENT = """\
FLOWHUB_ENV=production
FLOWHUB_DOMAIN=test.example.com
FLOWHUB_PORT=8080
FLOWHUB_DATABASE_URL=postgresql://flowhub_test:test_pg_pass_secure@postgres:5432/flowhub_test
FLOWHUB_POSTGRES_DB=flowhub_test
FLOWHUB_POSTGRES_USER=flowhub_test
FLOWHUB_POSTGRES_PASSWORD=test_pg_pass_secure_abc123xyz
FLOWHUB_JWT_SECRET={}
FLOWHUB_REST_API_SECRET={}
FLOWHUB_NEXTCLOUD_URL=https://cloud.example.com
FLOWHUB_NEXTCLOUD_FILE_PATH=/prices/test.xlsx
FLOWHUB_NEXTCLOUD_USERNAME=test_nc_user
FLOWHUB_NEXTCLOUD_PASSWORD=test_nc_pass_secure_abc123
FLOWHUB_WOOCOMMERCE_URL=https://shop.example.com
FLOWHUB_WOOCOMMERCE_KEY=ck_test_key_secure_deadbeef_abcdef
FLOWHUB_WOOCOMMERCE_SECRET=cs_test_secret_secure_cafebabe_xyz
FLOWHUB_TIMEZONE=UTC
FLOWHUB_CURRENCY=USD
FLOWHUB_ADMIN_EMAIL=admin@example.com
FLOWHUB_STORAGE_PATH=/tmp/flowhub-test-test/storage
FLOWHUB_BACKUP_PATH=/tmp/flowhub-test-test/backups
FLOWHUB_SSL_MODE=off
""".format("a" * 86, "b" * 64)

_PRODUCTION_ENV_CONTENT = """\
FLOWHUB_ENV=production
FLOWHUB_DOMAIN=prod.example.com
FLOWHUB_PORT=8080
FLOWHUB_DATABASE_URL=postgresql://prod_user:prod_pass@postgres:5432/prod_db
FLOWHUB_POSTGRES_DB=prod_db
FLOWHUB_POSTGRES_USER=prod_user
FLOWHUB_POSTGRES_PASSWORD=test_pg_pass_secure_abc123xyz
FLOWHUB_JWT_SECRET={}
FLOWHUB_REST_API_SECRET={}
FLOWHUB_NEXTCLOUD_URL=https://cloud.example.com
FLOWHUB_NEXTCLOUD_FILE_PATH=/prices/prod.xlsx
FLOWHUB_NEXTCLOUD_USERNAME=prod_nc_user
FLOWHUB_NEXTCLOUD_PASSWORD=prod_nc_pass_secure_abc123
FLOWHUB_WOOCOMMERCE_URL=https://shop.example.com
FLOWHUB_WOOCOMMERCE_KEY=ck_test_key_secure_deadbeef_abcdef
FLOWHUB_WOOCOMMERCE_SECRET=cs_test_secret_secure_cafebabe_xyz
FLOWHUB_TIMEZONE=UTC
FLOWHUB_CURRENCY=USD
FLOWHUB_ADMIN_EMAIL=admin@example.com
FLOWHUB_STORAGE_PATH=/tmp/flowhub-prod-test/storage
FLOWHUB_BACKUP_PATH=/tmp/flowhub-prod-test/backups
FLOWHUB_SSL_MODE=off
""".format("a" * 86, "b" * 64)


@pytest.fixture
def valid_env_file(tmp_path: Path) -> Path:
    """A valid .env file with FLOWHUB profile (no real/production values)."""
    env_file = tmp_path / ".env"
    env_file.write_text(_VALID_ENV_CONTENT, encoding="utf-8")
    return env_file


@pytest.fixture
def production_env_file(tmp_path: Path) -> Path:
    """A .env file with production profile (for testing production blocks)."""
    env_file = tmp_path / ".env.prod"
    env_file.write_text(_PRODUCTION_ENV_CONTENT, encoding="utf-8")
    return env_file


@pytest.fixture
def empty_env_file(tmp_path: Path) -> Path:
    """An empty (no variables) .env file."""
    env_file = tmp_path / ".env.empty"
    env_file.write_text("", encoding="utf-8")
    return env_file


@pytest.fixture
def valid_env_content() -> str:
    return _VALID_ENV_CONTENT
