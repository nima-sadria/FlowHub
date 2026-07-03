"""Shared fixtures for app/flowhub/config/ tests."""

import pytest

# Minimal valid env that passes ConfigValidator with check_paths=False.
_BASE_VALID_ENV: dict[str, str] = {
    "FLOWHUB_ENV": "production",
    "FLOWHUB_DOMAIN": "test.example.com",
    "FLOWHUB_PORT": "8080",
    "FLOWHUB_DATABASE_URL": "postgresql://user:pass@localhost/db",
    "FLOWHUB_POSTGRES_DB": "flowhub",
    "FLOWHUB_POSTGRES_USER": "flowhub",
    "FLOWHUB_POSTGRES_PASSWORD": "pg_pass_secure_abc123",
    "FLOWHUB_JWT_SECRET": "a" * 64,
    "FLOWHUB_REST_API_SECRET": "b" * 32,
    "FLOWHUB_NEXTCLOUD_URL": "https://cloud.example.com",
    "FLOWHUB_NEXTCLOUD_FILE_PATH": "/prices/test.xlsx",
    "FLOWHUB_NEXTCLOUD_USERNAME": "flowhub_user",
    "FLOWHUB_NEXTCLOUD_PASSWORD": "nc_pass_secure_xyz789",
    "FLOWHUB_WOOCOMMERCE_URL": "https://shop.example.com",
    "FLOWHUB_WOOCOMMERCE_KEY": "ck_test_key_secure_deadbeef",
    "FLOWHUB_WOOCOMMERCE_SECRET": "cs_test_secret_secure_cafebabe",
    "FLOWHUB_TIMEZONE": "Europe/Amsterdam",
    "FLOWHUB_CURRENCY": "EUR",
    "FLOWHUB_ADMIN_EMAIL": "admin@example.com",
    "FLOWHUB_STORAGE_PATH": "/tmp/FLOWHUB_storage",
    "FLOWHUB_BACKUP_PATH": "/tmp/FLOWHUB_backup",
    "FLOWHUB_SSL_MODE": "off",
}


@pytest.fixture
def valid_env() -> dict[str, str]:
    """Complete valid env dict. check_paths=False to avoid filesystem deps."""
    return dict(_BASE_VALID_ENV)


@pytest.fixture
def valid_env_with_paths(tmp_path) -> dict[str, str]:
    """Complete valid env dict with real tmp_path directories."""
    storage = tmp_path / "storage"
    storage.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    env = dict(_BASE_VALID_ENV)
    env["FLOWHUB_STORAGE_PATH"] = str(storage)
    env["FLOWHUB_BACKUP_PATH"] = str(backup)
    return env
