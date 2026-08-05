from __future__ import annotations

import hashlib
import asyncio
from functools import wraps

import pytest

from app.connectors.common.source_http import SourceHttpError, SourceHttpResponse
from app.flowhub.source_acquisition.execution import ProviderAcquisitionError
from app.flowhub.source_acquisition.nextcloud_provider import NextcloudWebDavAcquisitionProvider


def async_test(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        return asyncio.run(function(*args, **kwargs))

    return wrapper


class StubHttpClient:
    def __init__(self, response: SourceHttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def request(self, method: str, url: str, **kwargs) -> SourceHttpResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _provider(**kwargs) -> NextcloudWebDavAcquisitionProvider:
    return NextcloudWebDavAcquisitionProvider(
        webdav_files_root_url="https://cloud.example.com/remote.php/dav/files/user",
        spreadsheet_path="/Prices/قیمت.xlsx",
        username="user",
        app_password="app-secret",
        capture_contract="parse-v1",
        validator=lambda _content: {"schema_headers": ["SKU", "قیمت"]},
        **kwargs,
    )


@async_test
async def test_valid_capture_uses_http_boundary_and_returns_safe_evidence() -> None:
    content = b"validated-xlsx"
    digest = hashlib.sha256(content).hexdigest()
    client = StubHttpClient(
        SourceHttpResponse(
            200,
            {
                "etag": '"version-1"',
                "last-modified": "today",
                "oc-fileid": "42",
            },
            content,
            "https://cloud.example.com/file",
        )
    )

    result = await _provider().capture(client)  # type: ignore[arg-type]

    assert len(client.calls) == 1
    assert client.calls[0]["method"] == "GET"
    assert "%D9%82%DB%8C%D9%85%D8%AA.xlsx" in str(client.calls[0]["url"])
    assert client.calls[0]["basic_auth"] == ("user", "app-secret")
    assert result.resource_identity == "nextcloud:fileid:42"
    assert result.provenance["capture_sha256"] == digest
    assert result.evidence[1]["metadata"]["headers"] == ["SKU", "قیمت"]
    assert "app-secret" not in repr(result)


@async_test
async def test_not_modified_uses_conditional_token_without_observation_payload() -> None:
    client = StubHttpClient(SourceHttpResponse(304, {}, b"", "https://cloud.example.com/file"))
    result = await _provider(previous_change_token="etag-1").capture(client)  # type: ignore[arg-type]

    assert result.result == "not_modified"
    assert result.content is None
    assert client.calls[0]["headers"]["If-None-Match"] == "etag-1"  # type: ignore[index]


@async_test
@pytest.mark.parametrize("status", [401, 403])
async def test_authentication_rejection_is_normalized(status: int) -> None:
    client = StubHttpClient(SourceHttpResponse(status, {}, b"denied", "https://cloud.example.com"))
    with pytest.raises(ProviderAcquisitionError, match="provider_authentication_failed"):
        await _provider().capture(client)  # type: ignore[arg-type]


@async_test
async def test_invalid_workbook_is_rejected_before_capture_is_authoritative() -> None:
    client = StubHttpClient(SourceHttpResponse(200, {}, b"bad", "https://cloud.example.com"))
    provider = NextcloudWebDavAcquisitionProvider(
        webdav_files_root_url="https://cloud.example.com/dav",
        spreadsheet_path="/prices.xlsx",
        username="user",
        app_password="secret",
        capture_contract="parse-v1",
        validator=lambda _content: (_ for _ in ()).throw(ValueError("bad workbook secret")),
    )
    with pytest.raises(ProviderAcquisitionError, match="provider_response_invalid") as exc:
        await provider.capture(client)  # type: ignore[arg-type]
    assert "bad workbook secret" not in str(exc.value)


@async_test
async def test_security_failure_propagates_only_stable_code() -> None:
    client = StubHttpClient(SourceHttpError("unsafe_redirect"))
    with pytest.raises(SourceHttpError, match="unsafe_redirect"):
        await _provider().capture(client)  # type: ignore[arg-type]


@pytest.mark.parametrize("path", ["", "/../secret.xlsx", "/"])
def test_invalid_resource_paths_fail_before_network(path: str) -> None:
    with pytest.raises(ProviderAcquisitionError, match="resource_path_invalid"):
        NextcloudWebDavAcquisitionProvider(
            webdav_files_root_url="https://cloud.example.com/dav",
            spreadsheet_path=path,
            username="user",
            app_password="secret",
            capture_contract="parse-v1",
        )
