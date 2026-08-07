"""Nextcloud/WebDAV capture adapter for the Source acquisition pipeline."""

from __future__ import annotations

import hashlib
import posixpath
from collections.abc import Callable, Mapping
from urllib.parse import quote, unquote

from app.connectors.common.source_http import SourceHttpClient
from app.flowhub.source_acquisition.execution import ProviderAcquisitionError, ProviderCapture
from app.flowhub.unified_workspace.domain import utcnow


CaptureValidator = Callable[[bytes], Mapping[str, object] | None]


class NextcloudWebDavAcquisitionProvider:
    """Captures one configured WebDAV file through ``SourceHttpClient`` only."""

    def __init__(
        self,
        *,
        webdav_files_root_url: str,
        spreadsheet_path: str,
        username: str,
        app_password: str,
        capture_contract: str,
        validator: CaptureValidator | None = None,
        previous_change_token: str | None = None,
    ) -> None:
        self._root = webdav_files_root_url.rstrip("/")
        self._path = self._clean_path(spreadsheet_path)
        self._username = username
        self._app_password = app_password
        self._capture_contract = capture_contract
        self._validator = validator
        self._previous_change_token = previous_change_token

    async def capture(self, http_client: SourceHttpClient) -> ProviderCapture:
        headers: dict[str, str] = {"Accept": "application/octet-stream"}
        if self._previous_change_token:
            headers["If-None-Match"] = self._previous_change_token
        response = await http_client.request(
            "GET",
            self.resource_url,
            headers=headers,
            basic_auth=(self._username, self._app_password),
        )
        if response.status_code == 304:
            return ProviderCapture(result="not_modified")
        if response.status_code in {401, 403}:
            raise ProviderAcquisitionError("provider_authentication_failed")
        if response.status_code != 200:
            raise ProviderAcquisitionError("upstream_rejected")
        if not response.content:
            raise ProviderAcquisitionError("provider_response_invalid")

        validation: Mapping[str, object] = {}
        if self._validator is not None:
            try:
                validation = self._validator(response.content) or {}
            except Exception as exc:
                raise ProviderAcquisitionError("provider_response_invalid") from exc
        capture_hash = hashlib.sha256(response.content).hexdigest()
        etag = self._header(response.headers, "etag", 240)
        last_modified = self._header(response.headers, "last-modified", 240)
        file_id = self._header(response.headers, "oc-fileid", 120)
        identity_hash = hashlib.sha256(
            f"{self._root.lower()}|{self._path}".encode("utf-8")
        ).hexdigest()
        resource_identity = (
            f"nextcloud:fileid:{file_id}" if file_id else f"nextcloud:locator:{identity_hash}"
        )
        evidence = [
            {
                "kind": "capture_manifest",
                "reference": f"sha256:{capture_hash}",
                "metadata": {
                    "bytes": len(response.content),
                    "status": response.status_code,
                    "etag": etag,
                    "last_modified": last_modified,
                },
            }
        ]
        headers_value = validation.get("schema_headers")
        if isinstance(headers_value, list):
            evidence.append(
                {
                    "kind": "schema_headers",
                    "reference": f"sha256:{capture_hash}:headers",
                    "metadata": {"headers": headers_value},
                }
            )
        return ProviderCapture(
            result="observed",
            resource_identity=resource_identity,
            content=response.content,
            provenance={
                "provider": "nextcloud",
                "transport": "webdav",
                "capture_contract": self._capture_contract,
                "capture_sha256": capture_hash,
                "provider_change_token": etag,
                "change_token_kind": "opaque_equality",
                "byte_size": len(response.content),
            },
            evidence=evidence,
            snapshot_references=[
                {
                    "kind": "raw_capture",
                    "reference": f"sha256:{capture_hash}",
                    "checksum": capture_hash,
                    "metadata": {"format": "xlsx", "bytes": len(response.content)},
                }
            ],
            observed_at=utcnow(),
        )

    @property
    def resource_url(self) -> str:
        return f"{self._root}{quote(self._path, safe='/')}"

    @staticmethod
    def _clean_path(path: str) -> str:
        raw = unquote(str(path or "")).strip().replace("\\", "/")
        if not raw or "\x00" in raw:
            raise ProviderAcquisitionError("resource_path_invalid")
        if not raw.startswith("/"):
            raw = "/" + raw
        if any(part == ".." for part in raw.split("/")):
            raise ProviderAcquisitionError("resource_path_invalid")
        normalized = posixpath.normpath(raw)
        if normalized in {".", "/"}:
            raise ProviderAcquisitionError("resource_path_invalid")
        return normalized if normalized.startswith("/") else f"/{normalized}"

    @staticmethod
    def _header(headers: Mapping[str, str], name: str, limit: int) -> str | None:
        value = str(headers.get(name) or "").strip().strip('"')
        return value[:limit] or None
