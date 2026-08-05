"""SSRF-safe, bounded HTTP boundary for Source acquisition adapters.

Provider adapters must use this module for operator-configured Source targets.
It deliberately owns URL validation, DNS validation, redirect handling, and
bounded response reads; callers receive only stable failure codes.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Mapping
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx


Resolver = Callable[[str, int], Awaitable[list[str]]]
_SECRET_QUERY_NAMES = {"api_key", "access_token", "token", "key", "secret", "password", "sig", "signature"}
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class SourceHttpError(RuntimeError):
    """A transport error that never retains the upstream exception or URL."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SourceHttpPolicy:
    """Deployment-owned egress policy; Source settings cannot mutate it."""

    allow_http_hosts: frozenset[str] = frozenset()
    allowed_private_networks: tuple[ipaddress._BaseNetwork, ...] = ()
    max_redirects: int = 3
    max_response_bytes: int = 25 * 1024 * 1024
    max_header_bytes: int = 32 * 1024
    dns_timeout_seconds: float = 3.0
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 60.0


@dataclass(frozen=True)
class SourceHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes
    url: str


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    values = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({item[4][0] for item in values})


def redact_url(url: str) -> str:
    """Safe for logs: strips userinfo and masks credential-like query values."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "[invalid-url]"
    query = []
    for pair in parsed.query.split("&"):
        key, separator, value = pair.partition("=")
        query.append(f"{key}{separator}{'********' if key.lower() in _SECRET_QUERY_NAMES else value}")
    host = parsed.hostname or ""
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "&".join(query), ""))


class SourceHttpClient:
    """Explicit, non-redirecting HTTP client with validated/pinned destinations."""

    def __init__(
        self,
        *,
        policy: SourceHttpPolicy | None = None,
        resolver: Resolver = system_resolver,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self.policy = policy or SourceHttpPolicy()
        self._resolver = resolver
        self._client_factory = client_factory

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        basic_auth: tuple[str, str] | None = None,
    ) -> SourceHttpResponse:
        deadline = asyncio.get_running_loop().time() + self.policy.total_timeout_seconds
        origin: tuple[str, str, int] | None = None
        visited: set[str] = set()
        current_url = url
        request_headers = dict(headers or {})
        for redirect_count in range(self.policy.max_redirects + 1):
            target, addresses = await self._validated_target(current_url, deadline)
            normalized = redact_url(current_url)
            if normalized in visited:
                raise SourceHttpError("redirect_loop")
            visited.add(normalized)
            current_origin = (target.scheme, target.hostname or "", target.port or self._default_port(target.scheme))
            if origin is None:
                origin = current_origin
                if basic_auth is not None:
                    encoded = base64.b64encode(f"{basic_auth[0]}:{basic_auth[1]}".encode()).decode()
                    request_headers["Authorization"] = f"Basic {encoded}"
            elif current_origin != origin:
                request_headers.pop("Authorization", None)
                request_headers.pop("Cookie", None)
            response = await self._send(method, target, addresses[0], request_headers, content, deadline)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response
            location = response.headers.get("location")
            if not location:
                return response
            if redirect_count >= self.policy.max_redirects:
                raise SourceHttpError("redirect_limit_exceeded")
            current_url = str(httpx.URL(current_url).join(location))
            if target.scheme == "https" and urlsplit(current_url).scheme == "http":
                raise SourceHttpError("unsafe_redirect")
        raise SourceHttpError("redirect_limit_exceeded")

    async def _validated_target(self, url: str, deadline: float) -> tuple[SplitResult, list[str]]:
        try:
            target = urlsplit(url)
        except ValueError as exc:
            raise SourceHttpError("invalid_url") from exc
        if not target.scheme or not target.hostname:
            raise SourceHttpError("invalid_url")
        if target.username is not None or target.password is not None:
            raise SourceHttpError("credentials_in_url")
        scheme = target.scheme.lower()
        host = target.hostname.rstrip(".").lower()
        if scheme not in {"https", "http"}:
            raise SourceHttpError("unsupported_scheme")
        if scheme == "http" and host not in self.policy.allow_http_hosts:
            raise SourceHttpError("unsupported_scheme")
        if host == "localhost" or host.endswith(".localhost") or host.isdecimal():
            raise SourceHttpError("unsafe_destination")
        port = target.port or self._default_port(scheme)
        try:
            literal = ipaddress.ip_address(host)
            addresses = [str(literal)]
        except ValueError:
            try:
                addresses = await asyncio.wait_for(self._resolver(host, port), self._remaining(deadline))
            except asyncio.TimeoutError as exc:
                raise SourceHttpError("timeout") from exc
            except OSError as exc:
                raise SourceHttpError("dns_resolution_failed") from exc
        if not addresses:
            raise SourceHttpError("dns_resolution_failed")
        for address in addresses:
            self._validate_address(address)
        return target, sorted(addresses)

    async def _send(self, method: str, target: SplitResult, address: str, headers: dict[str, str], content: bytes | None, deadline: float) -> SourceHttpResponse:
        host = target.hostname or ""
        port = target.port
        netloc = f"[{address}]" if ":" in address else address
        if port is not None:
            netloc = f"{netloc}:{port}"
        pinned_url = urlunsplit((target.scheme, netloc, target.path or "/", target.query, ""))
        outbound_headers = dict(headers)
        outbound_headers["Host"] = host if port is None else f"{host}:{port}"
        timeout = httpx.Timeout(self.policy.read_timeout_seconds, connect=self.policy.connect_timeout_seconds)
        try:
            async with self._client_factory(follow_redirects=False, timeout=timeout, trust_env=False) as client:
                request = client.build_request(method, pinned_url, headers=outbound_headers, content=content)
                if host != address:
                    request.extensions["sni_hostname"] = host
                async with asyncio.timeout(self._remaining(deadline)):
                    response = await client.send(request, stream=True)
                    header_size = sum(len(key) + len(value) + 4 for key, value in response.headers.items())
                    if header_size > self.policy.max_header_bytes:
                        await response.aclose()
                        raise SourceHttpError("response_too_large")
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > self.policy.max_response_bytes:
                        await response.aclose()
                        raise SourceHttpError("response_too_large")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.policy.max_response_bytes:
                            await response.aclose()
                            raise SourceHttpError("decompression_limit_exceeded" if response.headers.get("content-encoding") else "response_too_large")
                        chunks.append(chunk)
                    return SourceHttpResponse(response.status_code, dict(response.headers), b"".join(chunks), redact_url(str(target.geturl())))
        except SourceHttpError:
            raise
        except asyncio.TimeoutError as exc:
            raise SourceHttpError("total_timeout") from exc
        except httpx.ConnectTimeout as exc:
            raise SourceHttpError("connect_timeout") from exc
        except httpx.ReadTimeout as exc:
            raise SourceHttpError("read_timeout") from exc
        except httpx.TimeoutException as exc:
            raise SourceHttpError("timeout") from exc
        except httpx.ConnectError as exc:
            raise SourceHttpError("tls_error" if "ssl" in str(exc).lower() or "cert" in str(exc).lower() else "connection_failed") from exc
        except httpx.RequestError as exc:
            raise SourceHttpError("connection_failed") from exc

    def _validate_address(self, value: str) -> None:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise SourceHttpError("dns_resolution_failed") from exc
        mapped = getattr(address, "ipv4_mapped", None)
        if mapped is not None:
            address = mapped
        allowed_private = any(address in network for network in self.policy.allowed_private_networks)
        unsafe = address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved or address in _CGNAT
        if unsafe or (address.is_private and not allowed_private):
            raise SourceHttpError("unsafe_destination")

    @staticmethod
    def _default_port(scheme: str) -> int:
        return 443 if scheme == "https" else 80

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise SourceHttpError("total_timeout")
        return remaining
