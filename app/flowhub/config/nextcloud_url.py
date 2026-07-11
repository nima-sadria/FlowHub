"""Validation and normalization for Nextcloud server and WebDAV URLs."""

from __future__ import annotations

from urllib.parse import unquote, urlparse


INVALID_NEXTCLOUD_URL = "Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings."
PUBLIC_SHARE_NOT_SUPPORTED = (
    "Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL."
)
CREDENTIALS_IN_URL_NOT_ALLOWED = (
    "Credentials must not be embedded in the Nextcloud URL. Use the separate username and app-password fields."
)


class NextcloudUrlValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "INVALID_NEXTCLOUD_URL") -> None:
        self.code = code
        super().__init__(message)


def normalize_nextcloud_url(raw_url: str, configured_username: str = "") -> dict[str, str]:
    """Normalize a root or personal WebDAV URL without retaining URL userinfo."""
    parsed = urlparse(str(raw_url or "").strip())
    try:
        has_userinfo = parsed.username is not None or parsed.password is not None
    except ValueError as exc:
        raise NextcloudUrlValidationError(INVALID_NEXTCLOUD_URL) from exc
    if has_userinfo:
        raise NextcloudUrlValidationError(
            CREDENTIALS_IN_URL_NOT_ALLOWED,
            code="CREDENTIALS_IN_URL_NOT_ALLOWED",
        )
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise NextcloudUrlValidationError(INVALID_NEXTCLOUD_URL)

    path = (parsed.path or "").rstrip("/")
    lowered = path.lower()
    if (
        "/index.php/s/" in lowered
        or lowered.endswith("/index.php/s")
        or lowered == "/s"
        or lowered.endswith("/s")
        or lowered.startswith("/s/")
        or "/s/" in lowered
        or "/public.php/dav/files" in lowered
    ):
        raise NextcloudUrlValidationError(PUBLIC_SHARE_NOT_SUPPORTED, code="PUBLIC_SHARE_NOT_SUPPORTED")

    marker = "/remote.php/dav/files"
    marker_index = lowered.find(marker)
    if marker_index >= 0:
        if parsed.query or parsed.fragment:
            raise NextcloudUrlValidationError(INVALID_NEXTCLOUD_URL)
        remainder = path[marker_index + len(marker):].strip("/")
        username_from_url = unquote(remainder.split("/", 1)[0]) if remainder else ""
        if not username_from_url:
            raise NextcloudUrlValidationError(INVALID_NEXTCLOUD_URL)
        username = str(configured_username or "").strip()
        if username and username != username_from_url:
            raise NextcloudUrlValidationError(
                "WebDAV URL username does not match configured username.",
                code="WEBDAV_USERNAME_MISMATCH",
            )
        server_path = path[:marker_index].rstrip("/")
        server_root_url = f"{parsed.scheme}://{parsed.netloc}{server_path}".rstrip("/")
        return {
            "server_root_url": server_root_url,
            "webdav_files_root_url": f"{server_root_url}/remote.php/dav/files/{username_from_url}/",
            "username": username or username_from_url,
            "username_from_url": username_from_url,
        }

    if "/remote.php/dav" in lowered or "/apps/files" in lowered or parsed.query or parsed.fragment:
        raise NextcloudUrlValidationError(INVALID_NEXTCLOUD_URL)
    server_root_url = f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")
    username = str(configured_username or "").strip()
    return {
        "server_root_url": server_root_url,
        "webdav_files_root_url": f"{server_root_url}/remote.php/dav/files/{username}/" if username else "",
        "username": username,
        "username_from_url": "",
    }
