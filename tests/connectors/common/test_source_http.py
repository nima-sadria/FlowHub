from __future__ import annotations

import asyncio
import ipaddress

import httpx
import pytest

from app.connectors.common.source_http import SourceHttpClient, SourceHttpError, SourceHttpPolicy, redact_url


async def _resolve_public(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


async def _resolve_private(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34", "10.0.0.9"]


@pytest.mark.parametrize("url, code", [
    ("", "invalid_url"), ("ftp://example.test/a", "unsupported_scheme"),
    ("https://user:pass@example.test/a", "credentials_in_url"),
    ("https://127.0.0.1/a", "unsafe_destination"),
    ("https://[::1]/a", "unsafe_destination"),
    ("https://169.254.169.254/a", "unsafe_destination"),
    ("https://localhost/a", "unsafe_destination"),
    ("https://2130706433/a", "unsafe_destination"),
])
def test_url_policy_rejects_unsafe_targets(url: str, code: str) -> None:
    async def scenario() -> None:
        with pytest.raises(SourceHttpError) as raised:
            await SourceHttpClient(resolver=_resolve_public)._validated_target(url, asyncio.get_running_loop().time() + 1)
        assert raised.value.code == code
    asyncio.run(scenario())


def test_dns_mixed_answers_fail_closed_and_private_allowlist_is_explicit() -> None:
    async def scenario() -> None:
        client = SourceHttpClient(resolver=_resolve_private)
        with pytest.raises(SourceHttpError, match="unsafe_destination"):
            await client._validated_target("https://example.test/x", asyncio.get_running_loop().time() + 1)
        allowed = SourceHttpClient(
            resolver=lambda _h, _p: _single("10.1.2.3"),
            policy=SourceHttpPolicy(allowed_private_networks=(ipaddress.ip_network("10.0.0.0/8"),)),
        )
        _, addresses = await allowed._validated_target("https://lan.example/x", asyncio.get_running_loop().time() + 1)
        assert addresses == ["10.1.2.3"]
    asyncio.run(scenario())


async def _single(value: str) -> list[str]:
    return [value]


class _Response:
    def __init__(self, status: int, headers: dict[str, str] | None = None, chunks: list[bytes] | None = None) -> None:
        self.status_code, self.headers, self._chunks = status, headers or {}, chunks or []
    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk
    async def aclose(self) -> None:
        return None


class _Client:
    def __init__(self, responses: list[_Response], **_kwargs: object) -> None:
        self.responses, self.requests = responses, []
    async def __aenter__(self): return self
    async def __aexit__(self, *_args: object) -> None: return None
    def build_request(self, *args: object, **kwargs: object) -> httpx.Request:
        return httpx.Request(*args, **kwargs)
    async def send(self, request: httpx.Request, *, stream: bool) -> _Response:
        self.requests.append(request)
        return self.responses.pop(0)


def test_redirect_is_revalidated_and_cross_origin_auth_is_stripped() -> None:
    responses = [_Response(302, {"location": "https://other.test/next"}), _Response(200, chunks=[b"ok"])]
    holder: dict[str, _Client] = {}
    def factory(**kwargs: object) -> _Client:
        holder.setdefault("client", _Client(responses, **kwargs))
        return holder["client"]
    async def scenario() -> None:
        result = await SourceHttpClient(resolver=_resolve_public, client_factory=factory).request("GET", "https://origin.test/a", basic_auth=("u", "secret"))
        assert result.content == b"ok"
        assert "authorization" not in holder["client"].requests[1].headers
    asyncio.run(scenario())


def test_redirect_downgrade_and_streaming_bounds_are_blocked() -> None:
    async def scenario() -> None:
        downgrade = SourceHttpClient(resolver=_resolve_public, client_factory=lambda **k: _Client([_Response(302, {"location": "http://example.test"})], **k))
        with pytest.raises(SourceHttpError, match="unsafe_redirect"):
            await downgrade.request("GET", "https://example.test")
        bounded = SourceHttpClient(policy=SourceHttpPolicy(max_response_bytes=3), resolver=_resolve_public, client_factory=lambda **k: _Client([_Response(200, chunks=[b"12", b"34"])], **k))
        with pytest.raises(SourceHttpError, match="response_too_large"):
            await bounded.request("GET", "https://example.test")
    asyncio.run(scenario())


def test_redaction_masks_query_secrets_and_userinfo() -> None:
    rendered = redact_url("https://user:pass@example.test/a?token=secret&ok=1")
    assert "user" not in rendered and "secret" not in rendered
    assert "token=********" in rendered and "ok=1" in rendered
