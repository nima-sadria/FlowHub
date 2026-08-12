"""Digikala seller Open API connector.

The repository-provided Digikala document defines authentication, a small set
of exact read routes, and generic error semantics.  It does *not* include the
endpoint-specific response/query schemas required to normalize products or
orders into FlowHub records.  This connector therefore deliberately exposes
only schema-safe raw reads, credential refresh, and a read-only connection
probe.  It declares no product, order, cache, or write capability.

Keeping this boundary explicit prevents an apparently working integration from
inventing SKU, price, inventory, or order-field mappings before the supplied
contract contains them.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelHealth,
    ConnectorError,
    ConnectorErrorCategory,
    RetryMetadata,
)
from app.flowhub.channels.marketplace import BaseMarketplaceConnector

DIGIKALA_BASE_URL = "https://seller.digikala.com/open-api/v1"
_ALLOWED_HOSTS = frozenset({"seller.digikala.com"})

# The supplied document explicitly names these routes.  Keeping the transport
# allowlists at this low level prevents a future call site from using this raw
# connector as a generic authenticated HTTP client.
_DOCUMENTED_READ_PATHS = frozenset(
    {
        "/auth/scopes",
        "/categories/tree",
        "/products/seller",
        "/orders",
    }
)
_DOCUMENTED_TOKEN_PATHS = frozenset({"/auth/token", "/auth/refresh-token"})

# The docs require a retry for an idempotent 500 and a wait-and-retry for 429
# after the provider announces a delay.  A bounded shared-read policy keeps
# that behavior safe and avoids turning a diagnostic into an unbounded job.
DIGIKALA_MAX_SAFE_READ_ATTEMPTS = 2
_SAFE_READ_RETRY_BACKOFF_SECONDS = 0.25

# These API areas are named in the supplied document but cannot be enabled:
# route methods/payloads and their mapping to the shared write pipeline are not
# documented.  Packages and shipments are additionally outside Owner authority.
DIGIKALA_DOCUMENTED_NOT_IMPLEMENTED = frozenset(
    {
        "normalized_product_and_inventory_cache",
        "normalized_order_sync_and_incremental_filters",
        "product_creation_and_drafts",
        "variant_price_activation_and_inventory_writes",
        "inventory_writes",
        "package_and_shipment_operations",
        "promotion_and_lightning_deal_operations",
        "webhook_registration",
        "token_revoke",
    }
)


class DigikalaConnectorError(Exception):
    """A structured, secret-safe Digikala connector error."""

    def __init__(self, error: ConnectorError) -> None:
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True)
class DigikalaConfig:
    """Persisted local configuration; tokens are accepted only as secrets."""

    access_token: str
    refresh_token: str | None = None
    base_url: str = DIGIKALA_BASE_URL
    timeout_seconds: int = 30
    enabled: bool = True

    @classmethod
    def from_values(cls, *, settings: dict[str, Any], secrets: dict[str, Any]) -> "DigikalaConfig":
        # Do not fall back to ordinary settings for credentials: callers use
        # ``secrets`` so write-only configuration fields cannot leak via GETs.
        access_token = _nonempty(secrets.get("access_token"))
        refresh_token = _nonempty(secrets.get("refresh_token"))
        base_url = str(settings.get("base_url") or DIGIKALA_BASE_URL).strip().rstrip("/")
        timeout_seconds = _timeout_seconds(settings.get("request_timeout") or 30)
        if not access_token:
            raise ValueError("Digikala access token is required.")
        _validate_base_url(base_url)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            enabled=bool(settings.get("enabled", True)),
        )


@dataclass(frozen=True)
class DigikalaTokenPair:
    """The token pair the documented token and refresh operations replace."""

    access_token: str
    refresh_token: str


class DigikalaConnector(BaseMarketplaceConnector):
    """Read-only adapter for the explicit Digikala Open API routes.

    ``allow_token_refresh`` is deliberately disabled by connection testing so
    a diagnostic probe is observational: it only performs ``GET /orders``.
    Operational raw reads may refresh once after a 401 when a refresh token was
    stored, exactly as the supplied document advises.
    """

    def __init__(
        self,
        *,
        channel_id: str,
        config: DigikalaConfig,
        token_updater: Callable[[str, str], None] | None = None,
        allow_token_refresh: bool = True,
        refresh_lock: asyncio.Lock | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(
            connector_type="digikala",
            channel_id=channel_id,
            capabilities={ChannelCapability.CREDENTIALS_REFRESH},
        )
        self.config = config
        self._access_token = config.access_token
        self._refresh_token = config.refresh_token
        self._token_updater = token_updater
        self._allow_token_refresh = allow_token_refresh
        self._refresh_lock = refresh_lock or asyncio.Lock()
        self._sleeper = sleeper or asyncio.sleep

    async def test_connection(self) -> ChannelHealth:
        """Use the documented authenticated GET /orders as a read-only probe."""

        started = time.perf_counter()
        try:
            # A connection test is never a credential-rotation path, even
            # when this connector was constructed for normal raw reads.
            await self._request(
                "GET",
                "/orders",
                safe_to_retry=True,
                retry_after_refresh=False,
                allow_retry=False,
            )
            return ChannelHealth(
                status="healthy",
                checked_at=_iso(_utcnow()),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except DigikalaConnectorError as exc:
            return ChannelHealth(
                status="unhealthy",
                checked_at=_iso(_utcnow()),
                error=exc.error,
            )

    async def refresh_credentials(self) -> ChannelHealth:
        """Replace both stored tokens using the exact documented refresh body."""

        try:
            await self._refresh_tokens()
            return ChannelHealth(status="healthy", checked_at=_iso(_utcnow()))
        except DigikalaConnectorError as exc:
            return ChannelHealth(
                status="unhealthy",
                checked_at=_iso(_utcnow()),
                error=exc.error,
            )

    # Raw reads intentionally preserve provider payloads until endpoint schemas
    # are supplied.  They make no pagination/filtering assumptions.
    async def read_scopes_payload(self) -> dict[str, Any]:
        return await self._request("GET", "/auth/scopes", safe_to_retry=True)

    async def read_client_scopes_payload(self, client_code: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/auth/scopes/{_path_identifier(client_code, 'client code')}",
            safe_to_retry=True,
        )

    async def read_categories_payload(self) -> dict[str, Any]:
        return await self._request("GET", "/categories/tree", safe_to_retry=True)

    async def read_seller_products_payload(self) -> dict[str, Any]:
        return await self._request("GET", "/products/seller", safe_to_retry=True)

    async def read_inventory_payload(self, product_variant_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/inventories/{_path_identifier(product_variant_id, 'product variant id')}",
            safe_to_retry=True,
        )

    async def read_orders_payload(self) -> dict[str, Any]:
        return await self._request("GET", "/orders", safe_to_retry=True)

    async def read_order_payload(self, order_item_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/orders/{_path_identifier(order_item_id, 'order item id')}",
            safe_to_retry=True,
        )

    async def exchange_authorization_code(self, authorization_code: str) -> DigikalaTokenPair:
        """Exchange a callback code through ``POST /auth/token``.

        The supplied documentation has no callback/client-code configuration
        schema, so this safe primitive is not exposed as a special UI flow.
        """

        code = _required_value(authorization_code, "authorization code")
        payload = await self._token_request(
            "POST",
            "/auth/token",
            json={"authorization_code": code},
            operation="token exchange",
        )
        return _token_pair_from_payload(payload, connector=self)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        safe_to_retry: bool,
        retry_after_refresh: bool = True,
        allow_retry: bool = True,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        normalized_path = _documented_read_path(path, connector=self)
        if normalized_method != "GET":
            # Owner authority explicitly forbids all order mutation.  The
            # broader GET-only rule also prevents every other undocumented
            # product, inventory, promotion, webhook, or token-revoke write.
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
                    "Digikala raw transport permits only documented read-only GET requests.",
                    safe_to_retry=False,
                )
            )

        attempt = 1
        can_refresh = retry_after_refresh
        while True:
            try:
                response = await self._send_authorized(normalized_method, normalized_path)
                return self._decode_response(response, safe_to_retry=safe_to_retry)
            except DigikalaConnectorError as exc:
                if (
                    can_refresh
                    and self._allow_token_refresh
                    and safe_to_retry
                    and exc.error.category == ConnectorErrorCategory.AUTHENTICATION
                    and self._refresh_token
                ):
                    await self._refresh_tokens()
                    can_refresh = False
                    continue

                delay = self._safe_read_retry_delay(
                    exc.error,
                    safe_to_retry=safe_to_retry,
                    allow_retry=allow_retry,
                    attempt=attempt,
                )
                if delay is None:
                    raise
                await self._sleeper(delay)
                attempt += 1

    async def _refresh_tokens(self) -> DigikalaTokenPair:
        if not self._refresh_token:
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.AUTHENTICATION,
                    "Digikala refresh token is not configured.",
                    http_status=401,
                    safe_to_retry=False,
                )
            )
        async with self._refresh_lock:
            payload = await self._token_request(
                "POST",
                "/auth/refresh-token",
                json={
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                },
                operation="token refresh",
            )
            pair = _token_pair_from_payload(payload, connector=self)
            self._access_token = pair.access_token
            self._refresh_token = pair.refresh_token
            if self._token_updater is not None:
                self._token_updater(pair.access_token, pair.refresh_token)
            return pair

    async def _token_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, str],
        operation: str,
    ) -> dict[str, Any]:
        normalized_method = method.upper()
        normalized_path = _documented_token_path(path, connector=self)
        if normalized_method != "POST":
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
                    "Digikala token transport permits only documented POST token operations.",
                    safe_to_retry=False,
                )
            )
        try:
            response = await self._send_without_authorization(
                normalized_method,
                normalized_path,
                json=json,
            )
            return self._decode_response(response, safe_to_retry=False)
        except DigikalaConnectorError:
            raise
        except Exception as exc:  # Defensive boundary for unexpected transports.
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
                    f"Digikala {operation} failed.",
                    safe_to_retry=False,
                )
            ) from exc

    async def _send_authorized(self, method: str, path: str) -> httpx.Response:
        return await self._send(
            method,
            path,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
            authorized=True,
        )

    async def _send_without_authorization(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, str],
    ) -> httpx.Response:
        return await self._send(
            method,
            path,
            headers={"Content-Type": "application/json"},
            json=json,
            authorized=False,
        )

    async def _send(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json: dict[str, str] | None = None,
        authorized: bool,
    ) -> httpx.Response:
        normalized_method = method.upper()
        if authorized:
            normalized_path = _documented_read_path(path, connector=self)
            if normalized_method != "GET":
                raise DigikalaConnectorError(
                    self._error(
                        ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
                        "Digikala authorized transport permits only documented read-only GET requests.",
                        safe_to_retry=False,
                    )
                )
        else:
            normalized_path = _documented_token_path(path, connector=self)
            if normalized_method != "POST":
                raise DigikalaConnectorError(
                    self._error(
                        ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
                        "Digikala token transport permits only documented POST token operations.",
                        safe_to_retry=False,
                    )
                )
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds)
            ) as client:
                return await client.request(
                    normalized_method,
                    self._url(normalized_path),
                    headers=headers,
                    json=json,
                )
        except httpx.TimeoutException as exc:
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.TIMEOUT,
                    "Digikala request timed out.",
                    safe_to_retry=normalized_method == "GET",
                )
            ) from exc
        except httpx.HTTPError as exc:
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
                    "Digikala request failed.",
                    safe_to_retry=normalized_method == "GET",
                )
            ) from exc

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.strip('/')}"

    def _decode_response(
        self,
        response: httpx.Response,
        *,
        safe_to_retry: bool,
    ) -> dict[str, Any]:
        status_code = response.status_code
        if status_code >= 400:
            category = {
                400: ConnectorErrorCategory.VALIDATION,
                401: ConnectorErrorCategory.AUTHENTICATION,
                403: ConnectorErrorCategory.AUTHORIZATION,
                404: ConnectorErrorCategory.NOT_FOUND,
                429: ConnectorErrorCategory.RATE_LIMIT,
            }.get(
                status_code,
                ConnectorErrorCategory.UPSTREAM_UNAVAILABLE
                if status_code >= 500
                else ConnectorErrorCategory.UNEXPECTED_RESPONSE,
            )
            retryable = safe_to_retry and category in {
                ConnectorErrorCategory.RATE_LIMIT,
                ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
            }
            payload = _response_json_or_empty(response)
            provider_code = _nonempty(payload.get("code")) if isinstance(payload, dict) else None
            raise DigikalaConnectorError(
                self._error(
                    category,
                    _error_message(category, status_code),
                    http_status=status_code,
                    provider_code=provider_code,
                    safe_to_retry=retryable,
                    retry_after_seconds=_retry_after_seconds(response),
                )
            )
        if status_code == 204 or not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.UNEXPECTED_RESPONSE,
                    "Digikala returned malformed JSON.",
                    http_status=status_code,
                    safe_to_retry=False,
                )
            ) from exc
        if not isinstance(payload, dict):
            raise DigikalaConnectorError(
                self._error(
                    ConnectorErrorCategory.UNEXPECTED_RESPONSE,
                    "Digikala returned a malformed response.",
                    http_status=status_code,
                    safe_to_retry=False,
                )
            )
        return payload

    def _error(
        self,
        category: ConnectorErrorCategory,
        message: str,
        *,
        http_status: int | None = None,
        provider_code: str | None = None,
        safe_to_retry: bool,
        retry_after_seconds: float | None = None,
    ) -> ConnectorError:
        return ConnectorError(
            category=category,
            message=message,
            connector_type=self.connector_type,
            channel_id=self.channel_id,
            http_status=http_status,
            provider_code=provider_code,
            retry=RetryMetadata(
                retryable=safe_to_retry,
                retry_after_seconds=retry_after_seconds,
                safe_to_retry=safe_to_retry,
                max_attempts=DIGIKALA_MAX_SAFE_READ_ATTEMPTS if safe_to_retry else 0,
            ),
        )

    def _safe_read_retry_delay(
        self,
        error: ConnectorError,
        *,
        safe_to_retry: bool,
        allow_retry: bool,
        attempt: int,
    ) -> float | None:
        """Return a documented, bounded delay for a safe raw-read retry."""

        if (
            not allow_retry
            or not safe_to_retry
            or not error.retry.safe_to_retry
            or attempt >= DIGIKALA_MAX_SAFE_READ_ATTEMPTS
        ):
            return None
        if error.category == ConnectorErrorCategory.RATE_LIMIT:
            # The supplied docs require the provider-announced wait.  Do not
            # invent a rate-limit delay when it did not announce one.
            return error.retry.retry_after_seconds
        if error.category in {
            ConnectorErrorCategory.TIMEOUT,
            ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
        }:
            return _SAFE_READ_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
        return None


def _token_pair_from_payload(
    payload: dict[str, Any],
    *,
    connector: DigikalaConnector,
) -> DigikalaTokenPair:
    # The document only promises that successful token responses contain these
    # fields.  Accepting the generic ``data`` envelope too is forward-compatible
    # without assuming any additional field names or expiry semantics.
    root = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    access_token = _nonempty(root.get("access_token")) if isinstance(root, dict) else None
    refresh_token = _nonempty(root.get("refresh_token")) if isinstance(root, dict) else None
    if not access_token or not refresh_token:
        raise DigikalaConnectorError(
            connector._error(
                ConnectorErrorCategory.UNEXPECTED_RESPONSE,
                "Digikala token response did not contain both replacement tokens.",
                safe_to_retry=False,
            )
        )
    return DigikalaTokenPair(access_token=access_token, refresh_token=refresh_token)


def _validate_base_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/open-api/v1"
    ):
        raise ValueError("Digikala Base URL must use the documented HTTPS Open API endpoint.")


def _timeout_seconds(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Digikala request timeout must be an integer.")
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Digikala request timeout must be an integer.") from exc
    if not timeout.is_integer() or timeout < 1 or timeout > 120:
        raise ValueError("Digikala request timeout must be between 1 and 120 seconds.")
    return int(timeout)


def _path_identifier(value: str, label: str) -> str:
    return quote(_required_value(value, label), safe="")


def _documented_read_path(value: str, *, connector: DigikalaConnector) -> str:
    """Normalize and allow only the exact read routes named by the docs."""

    path = _normalized_contract_path(value)
    if path in _DOCUMENTED_READ_PATHS:
        return path

    parts = path.split("/")
    is_client_scopes = (
        len(parts) == 4
        and parts[1:3] == ["auth", "scopes"]
        and bool(parts[3])
    )
    is_inventory = len(parts) == 3 and parts[1] == "inventories" and bool(parts[2])
    is_order_detail = len(parts) == 3 and parts[1] == "orders" and bool(parts[2])
    if is_client_scopes or is_inventory or is_order_detail:
        return path
    raise DigikalaConnectorError(
        connector._error(
            ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
            "Digikala raw transport permits only documented read-only endpoints.",
            safe_to_retry=False,
        )
    )


def _documented_token_path(value: str, *, connector: DigikalaConnector) -> str:
    """Normalize and allow only the two documented credential token routes."""

    path = _normalized_contract_path(value)
    if path in _DOCUMENTED_TOKEN_PATHS:
        return path
    raise DigikalaConnectorError(
        connector._error(
            ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
            "Digikala token transport permits only documented token endpoints.",
            safe_to_retry=False,
        )
    )


def _normalized_contract_path(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or "?" in raw or "#" in raw:
        return ""
    return f"/{raw.strip('/')}"


def _required_value(value: str, label: str) -> str:
    text = _nonempty(value)
    if not text:
        raise DigikalaConnectorError(
            ConnectorError(
                category=ConnectorErrorCategory.VALIDATION,
                message=f"Digikala {label} is required.",
                connector_type="digikala",
                channel_id="digikala:main",
                retry=RetryMetadata(retryable=False, safe_to_retry=False),
            )
        )
    return text


def _response_json_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _retry_after_seconds(response: httpx.Response) -> float | None:
    # The docs say to honor a provider-announced delay but do not name a header.
    # Honor the conventional header when present without treating it as required.
    raw = response.headers.get("Retry-After")
    try:
        delay = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None
    return delay if delay is not None and delay >= 0 else None


def _error_message(category: ConnectorErrorCategory, status_code: int) -> str:
    messages = {
        ConnectorErrorCategory.VALIDATION: "Digikala rejected request validation.",
        ConnectorErrorCategory.AUTHENTICATION: "Digikala authentication failed.",
        ConnectorErrorCategory.AUTHORIZATION: "Digikala authorization failed.",
        ConnectorErrorCategory.NOT_FOUND: "Digikala resource was not found.",
        ConnectorErrorCategory.RATE_LIMIT: "Digikala rate limit was reached.",
        ConnectorErrorCategory.UPSTREAM_UNAVAILABLE: "Digikala is unavailable.",
    }
    return messages.get(category, f"Digikala request failed with HTTP {status_code}.")


def _nonempty(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"
