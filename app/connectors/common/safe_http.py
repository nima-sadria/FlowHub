"""Small server-side HTTP boundary that never propagates credential-bearing URLs."""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

import httpx

_SENSITIVE_QUERY_VALUE = re.compile(
    r"(?i)(?P<name>api_key|access_token|token|key)=(?P<value>[^&\s]+)"
)


def _redact_url_text(value: object) -> object:
    rendered = str(value)
    if not _SENSITIVE_QUERY_VALUE.search(rendered):
        return value
    return _SENSITIVE_QUERY_VALUE.sub(r"\g<name>=********", rendered)


class _SensitiveUrlFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_url_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_url_text(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_url_text(value) for key, value in record.args.items()
            }
        return True


for _logger_name in ("httpx", "httpcore"):
    _logger = logging.getLogger(_logger_name)
    if not any(isinstance(item, _SensitiveUrlFilter) for item in _logger.filters):
        _logger.addFilter(_SensitiveUrlFilter())


class HttpJsonResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class SafeHttpTimeout(RuntimeError):
    """A redacted upstream timeout."""


class SafeHttpNetworkError(RuntimeError):
    """A redacted upstream transport failure."""


class SafeJsonHttpClient:
    """Perform bounded JSON GETs without exposing request URLs in exceptions."""

    def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
    ) -> HttpJsonResponse:
        try:
            return httpx.get(url, params=params, timeout=timeout)
        except httpx.TimeoutException:
            # Do not chain httpx exceptions: their request object retains the
            # provider URL, including query-based authentication.
            raise SafeHttpTimeout("Upstream request timed out.") from None
        except httpx.RequestError:
            raise SafeHttpNetworkError("Upstream service could not be reached.") from None
