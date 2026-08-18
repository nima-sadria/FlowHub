"""Safe application errors for failures returned by external services."""

from __future__ import annotations

from typing import Any

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.flowhub.integrations.errors import IntegrationError


UPSTREAM_FALLBACK_MESSAGE = "The external service returned an invalid or unavailable response."
INTERNAL_FALLBACK_MESSAGE = "An internal error prevented this operation from completing."

# Honest failure taxonomy shared by the channel/source error contract, the
# Diagnostics Advanced Evidence layer, and webhook retryability decisions.
# `internal_error` exists specifically so a failure that FlowHub caused is
# never laundered into "the external service is broken": that mislabelling is
# what made CHANNEL_UPSTREAM_ERROR unactionable.
CATEGORY_AUTH_FAILED = "auth_failed"
CATEGORY_NOT_FOUND = "not_found"
CATEGORY_RATE_LIMITED = "rate_limited"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_DNS_ERROR = "dns_error"
CATEGORY_TLS_ERROR = "tls_error"
CATEGORY_UPSTREAM_UNAVAILABLE = "upstream_unavailable"
CATEGORY_NOT_CONFIGURED = "not_configured"
CATEGORY_INTERNAL_ERROR = "internal_error"
# The work was never attempted because another unexpired lease already owned
# it. Not a failure of any kind -- the caller should simply wait, not retry
# against an attempt budget.
CATEGORY_REFRESH_IN_PROGRESS = "refresh_in_progress"


class UpstreamServiceError(Exception):
    """Wrap an external failure so the production app emits a safe contract."""

    def __init__(self, error: Exception, *, source: str | None = None) -> None:
        self.error = error
        self.source = source
        super().__init__("External service request failed.")


def is_upstream_attributable(error: Exception, *, attributable: bool | None = None) -> bool:
    """Is this failure genuinely attributable to the external service?

    Only three things count as evidence that an external service actually
    misbehaved: the provider boundary raised its own typed error
    (``ConnectorError``/``IntegrationError``), an ``httpx`` transport error
    escaped from the provider call, or the failure carries a real HTTP status
    from the provider. A caller that already knows the failure is upstream may
    assert it with ``attributable=True``.

    Everything else -- ``KeyError``/``AttributeError``/``TypeError`` from a bug
    in normalization or persistence, a SQLAlchemy failure, an internal lease
    conflict -- is FlowHub's own failure. Message pattern-matching is
    deliberately NOT accepted as attribution evidence: treating it as such is
    exactly how internal failures were relabelled ``*_UPSTREAM_ERROR``.
    """

    if attributable is not None:
        return attributable
    if isinstance(error, (ConnectorError, IntegrationError, UpstreamServiceError)):
        return True
    if _is_transport_error(error):
        return True
    status = _http_status(error)
    return status is not None and 100 <= status <= 599


def _is_transport_error(error: Exception) -> bool:
    """Did this exception come from the HTTP transport layer?

    Detected by the defining module rather than by importing httpx: the
    FlowHub runtime is not permitted to import httpx directly (see
    tests/flowhub/test_no_direct_httpx.py) because all WooCommerce/Nextcloud
    HTTP must go through app/connectors/.
    """

    for klass in type(error).__mro__:
        root = str(getattr(klass, "__module__", "")).split(".", 1)[0]
        if root in {"httpx", "httpcore", "ssl", "socket"}:
            return True
    return False


#: Keys that form the public, over-the-wire error contract. Consumers assert
#: on this exact shape, so the honest taxonomy (`category`,
#: `upstream_attributable`) is deliberately kept OUT of it and exposed only to
#: internal callers through `classify_failure`.
PUBLIC_ERROR_KEYS = ("code", "message", "source", "http_status")


def normalize_upstream_error(
    error: Exception,
    *,
    source: str | None = None,
    attributable: bool | None = None,
) -> dict[str, Any]:
    """Return the bounded, credential-free *public* error payload.

    Shape is exactly ``PUBLIC_ERROR_KEYS`` -- unchanged from before the honest
    classification work. Internal callers that need the machine-readable
    category must use `classify_failure` instead.
    """

    return {
        key: value
        for key, value in classify_failure(
            error, source=source, attributable=attributable
        ).items()
        if key in PUBLIC_ERROR_KEYS
    }


def classify_failure(
    error: Exception,
    *,
    source: str | None = None,
    attributable: bool | None = None,
) -> dict[str, Any]:
    """Classify a failure honestly for internal/Advanced Evidence consumers.

    Returns the public ``code``/``message``/``source``/``http_status`` fields
    plus ``category`` (the retryability taxonomy) and
    ``upstream_attributable`` (whether the external service is genuinely to
    blame). Only this function distinguishes "WooCommerce failed" from
    "FlowHub failed"; the public code stays as-is for compatibility.
    """
    provider = _provider_for(error, source)
    prefix = "SOURCE" if provider == "nextcloud" else "CHANNEL" if provider == "woocommerce" else "SOURCE"
    upstream = is_upstream_attributable(error, attributable=attributable)
    error_code = _connector_code(error) if upstream else None
    http_status = _http_status(error)
    detail = _error_detail(error)

    if is_unsafe_upstream_content(detail):
        # Unsafe bodies only ever come off the wire, so this is upstream by
        # construction regardless of the exception type carrying it.
        return {
            "code": f"{prefix}_UPSTREAM_ERROR",
            "message": UPSTREAM_FALLBACK_MESSAGE,
            "source": provider,
            "http_status": http_status,
            "category": CATEGORY_UPSTREAM_UNAVAILABLE,
            "upstream_attributable": True,
        }
    if detail == "connector_not_configured":
        return {
            "code": "connector_not_configured",
            "message": "connector_not_configured",
            "source": provider,
            "http_status": http_status,
            "category": CATEGORY_NOT_CONFIGURED,
            "upstream_attributable": False,
        }

    if not upstream:
        # Honest default. The public message stays generic and non-leaky, but
        # it no longer blames the external service for FlowHub's own failure.
        return {
            "code": f"{prefix}_INTERNAL_ERROR",
            "message": INTERNAL_FALLBACK_MESSAGE,
            "source": "flowhub",
            "http_status": http_status,
            "category": CATEGORY_INTERNAL_ERROR,
            "upstream_attributable": False,
        }

    if error_code in {ConnectorErrorCode.AUTH_FAILED, ConnectorErrorCode.PERMISSION}:
        code = f"{prefix}_AUTH_FAILED"
        message = "Authentication failed."
        category = CATEGORY_AUTH_FAILED
    elif error_code == ConnectorErrorCode.NOT_FOUND:
        code = f"{prefix}_NOT_FOUND"
        message = "The requested external resource was not found."
        category = CATEGORY_NOT_FOUND
    elif error_code == ConnectorErrorCode.RATE_LIMITED:
        code = f"{prefix}_RATE_LIMITED"
        message = "The external service rate limit was reached. Try again later."
        category = CATEGORY_RATE_LIMITED
    elif error_code == ConnectorErrorCode.TIMEOUT:
        code = f"{prefix}_TIMEOUT"
        message = "The external service did not respond in time."
        category = CATEGORY_TIMEOUT
    elif error_code == ConnectorErrorCode.NETWORK:
        lowered_detail = detail.lower()
        if "dns" in lowered_detail or "resolve" in lowered_detail:
            code = f"{prefix}_DNS_ERROR"
            message = "The external service hostname could not be resolved."
            category = CATEGORY_DNS_ERROR
        elif "tls" in lowered_detail or "certificate" in lowered_detail or "ssl" in lowered_detail:
            code = f"{prefix}_TLS_ERROR"
            message = "A secure connection to the external service could not be established."
            category = CATEGORY_TLS_ERROR
        else:
            code = f"{prefix}_UPSTREAM_ERROR"
            message = UPSTREAM_FALLBACK_MESSAGE
            category = CATEGORY_UPSTREAM_UNAVAILABLE
    else:
        code = f"{prefix}_UPSTREAM_ERROR"
        message = UPSTREAM_FALLBACK_MESSAGE
        category = CATEGORY_UPSTREAM_UNAVAILABLE

    return {
        "code": code,
        "message": message,
        "source": provider,
        "http_status": http_status,
        "category": category,
        "upstream_attributable": True,
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
