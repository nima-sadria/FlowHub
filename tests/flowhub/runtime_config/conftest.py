"""Shared fixtures for runtime configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    """A minimal .env file with all editable and installer-only fields set."""
    content = (
        "FLOWHUB_ENV=production\n"
        "FLOWHUB_DOMAIN=FLOWHUB.example.com\n"
        "FLOWHUB_PORT=8080\n"
        "FLOWHUB_SSL_MODE=reverse_proxy\n"
        "FLOWHUB_DATABASE_URL=postgresql://user:pass@localhost/db\n"
        "FLOWHUB_POSTGRES_DB=flowhub\n"
        "FLOWHUB_POSTGRES_USER=flowhub\n"
        "FLOWHUB_POSTGRES_PASSWORD=pgpass\n"
        "FLOWHUB_JWT_SECRET=" + "a" * 64 + "\n"
        "FLOWHUB_REST_API_SECRET=" + "b" * 32 + "\n"
        "FLOWHUB_NEXTCLOUD_URL=https://nextcloud.example.com\n"
        "FLOWHUB_NEXTCLOUD_FILE_PATH=/prices/prices.xlsx\n"
        "FLOWHUB_NEXTCLOUD_USERNAME=ncuser\n"
        "FLOWHUB_NEXTCLOUD_PASSWORD=ncpass\n"
        "FLOWHUB_WOOCOMMERCE_URL=https://shop.example.com\n"
        "FLOWHUB_WOOCOMMERCE_KEY=ck_abc\n"
        "FLOWHUB_WOOCOMMERCE_SECRET=cs_xyz\n"
        "FLOWHUB_TIMEZONE=UTC\n"
        "FLOWHUB_CURRENCY=USD\n"
        "FLOWHUB_ADMIN_EMAIL=admin@example.com\n"
        "FLOWHUB_STORAGE_PATH=/data/flowhub\n"
        "FLOWHUB_BACKUP_PATH=/data/backup\n"
        "FLOWHUB_LOG_LEVEL=INFO\n"
        "FLOWHUB_SCHEDULER_POLL_SECONDS=60\n"
        "FLOWHUB_BACKUP_RETAIN_DAYS=7\n"
        "FLOWHUB_MAX_UPLOAD_MB=100\n"
        "FLOWHUB_WORKER_CONCURRENCY=2\n"
    )
    p = tmp_path / ".env"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture
def empty_env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("", encoding="utf-8")
    return p
