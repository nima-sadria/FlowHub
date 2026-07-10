"""Safe application errors for failures returned by external services."""

from __future__ import annotations

from typing import Any

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.flowhub.integrations.errors import IntegrationError


UPSTREAM_FALLBACK_MESSAGE = "The external service returned an invalid or unavailable response."


class UpstreamServiceError(Exception):
    """Wrap an external failure so the production app emits a safe contract."""

    def __init__(self, error: Exception, *, source: str | None = None) -> None:
        self.error = error
        self.source = source
        super().__init__("External service request failed.")


def normalize_upstream_error(error: Exception, *, source: str | None = None) -> dict[str, Any]:
    """Return a bounded, credential-free error payload for an external failure."""
    provider = _provider_for(error, source)
    prefix = "SOURCE" if provider == "nextcloud" else "CHANNEL" if provider == "woocommerce" else "SOURCE"
    error_code = _connector_code(error)
    http_status = _http_status(error)
    detail = _error_detail(error)

    if is_unsafe_upstream_content(detail):
        return {
            "code": f"{prefix}_UPSTREAM_ERROR",
            "message": UPSTREAM_FALLBACK_MESSAGE,
            "source": provider,
            "http_status": http_status,
        }
    if detail == "connector_not_configured":
        return {
            "code": "connector_not_configured",
            "message": "connector_not_configured",
            "source": provider,
            "http_status": http_status,
        }

    if error_code in {ConnectorErrorCode.AUTH_FAILED, ConnectorErrorCode.PERMISSION}:
        code = f"{prefix}_AUTH_FAILED"
        message = "Authentication failed."
    elif error_code == ConnectorErrorCode.NOT_FOUND:
        code = f"{prefix}_NOT_FOUND"
        message = "The requested external resource was not found."
    elif error_code == ConnectorErrorCode.RATE_LIMITED:
        code = f"{prefix}_RATE_LIMITED"
        message = "The external service rate limit was reached. Try again later."
    elif error_code == ConnectorErrorCode.TIMEOUT:
        code = f"{prefix}_TIMEOUT"
        message = "The external service did not respond in time."
    elif error_code == ConnectorErrorCode.NETWORK:
        lowered_detail = detail.lower()
        if "dns" in lowered_detail or "resolve" in lowered_detail:
            code = f"{prefix}_DNS_ERROR"
            message = "The external service hostname could not be resolved."
        elif "tls" in lowered_detail or "certificate" in lowered_detail or "ssl" in lowered_detail:
            code = f"{prefix}_TLS_ERROR"
            message = "A secure connection to the external service could not be established."
        else:
            code = f"{prefix}_UPSTREAM_ERROR"
            message = UPSTREAM_FALLBACK_MESSAGE
    else:
        code = f"{prefix}_UPSTREAM_ERROR"
        message = UPSTREAM_FALLBACK_MESSAGE

    return {
        "code": code,
        "message": message,
        "source": provider,
        "http_status": http_status,
    }


def upstream_http_status(error: Exception) -> int:
    status = _http_status(error)
    if status is not None and 400 <= status <= 599:
        return status
    code = _connector_code(error)
    return 504 if code == ConnectorErrorCode.TIMEOUT else 502


def is_unsafe_upstream_content(value: object) -> bool:
    """Detect response bodies that must never be copied into an API response."""
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return (
        len(value) > 512
        or text.startswith("<!doctype html")
        or text.startswith("<html")
        or text.startswith("<?xml")
        or "<body" in text
        or "cloudflare" in text
        or "nginx" in text
        or "proxy error" in text
        or "gateway timeout" in text
    )


def _provider_for(error: Exception, source: str | None) -> str:
    value = source or getattr(error, "provider", None) or "proxy"
    normalized = str(value).strip().lower()
    if "nextcloud" in normalized or "webdav" in normalized:
        return "nextcloud"
    if "woocommerce" in normalized or normalized in {"woo", "wc"}:
        return "woocommerce"
    return "proxy"


def _connector_code(error: Exception) -> ConnectorErrorCode | None:
    code = getattr(error, "code", None)
    if isinstance(code, ConnectorErrorCode):
        return code
    message = _error_detail(error).lower()
    if "authentication" in message or "access denied" in message or "permission" in message:
        return ConnectorErrorCode.AUTH_FAILED
    if "not found" in message:
        return ConnectorErrorCode.NOT_FOUND
    if "rate limit" in message or "too many requests" in message:
        return ConnectorErrorCode.RATE_LIMITED
    if "timed out" in message or "timeout" in message:
        return ConnectorErrorCode.TIMEOUT
    if "could not connect" in message or "connection failed" in message or "dns" in message or "tls" in message:
        return ConnectorErrorCode.NETWORK
    return None


def _http_status(error: Exception) -> int | None:
    value = getattr(error, "http_status", None)
    if value is None:
        value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _error_detail(error: Exception) -> str:
    if isinstance(error, ConnectorError):
        return error.message or ""
    if isinstance(error, IntegrationError):
        return error.message or ""
    detail = getattr(error, "detail", None)
    if detail is not None:
        return str(detail)
    return str(error)
