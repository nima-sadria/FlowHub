from __future__ import annotations

import logging

import pytest

from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.nextcloud import NextcloudClient
from app.flowhub.config.nextcloud_url import NextcloudUrlValidationError, normalize_nextcloud_url


@pytest.mark.parametrize(
    "url",
    [
        "https://user@nextcloud.example.test",
        "https://user:password@nextcloud.example.test",
        "https://user%40example.test:token@nextcloud.example.test/remote.php/dav/files/user",
    ],
)
def test_rejects_credential_bearing_nextcloud_urls(url):
    with pytest.raises(NextcloudUrlValidationError) as exc_info:
        normalize_nextcloud_url(url, "user")

    assert exc_info.value.code == "CREDENTIALS_IN_URL_NOT_ALLOWED"
    assert url not in str(exc_info.value)
    assert "legacy-secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("url", "username", "expected_root"),
    [
        ("https://nextcloud.example.test", "user", "https://nextcloud.example.test"),
        (
            "https://nextcloud.example.test/remote.php/dav/files/user/",
            "user",
            "https://nextcloud.example.test",
        ),
    ],
)
def test_accepts_safe_nextcloud_root_and_webdav_urls(url, username, expected_root):
    normalized = normalize_nextcloud_url(url, username)

    assert normalized["server_root_url"] == expected_root
    assert normalized["webdav_files_root_url"] == f"{expected_root}/remote.php/dav/files/user/"


def test_client_rejects_legacy_credential_url_without_logging_it(caplog):
    class Config:
        values = {
            "nextcloud.url": "https://user:legacy-secret@nextcloud.example.test",
            "nextcloud.username": "user",
            "nextcloud.password": "app-password",
            "nextcloud.webdav_files_root_url": "",
        }

        def get(self, key):
            return self.values.get(key)

    with caplog.at_level(logging.DEBUG), pytest.raises(IntegrationError):
        NextcloudClient.from_config(Config())

    assert "legacy-secret" not in caplog.text
    assert "app-password" not in caplog.text
