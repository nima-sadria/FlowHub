"""Canonical public URL helpers for provider callback endpoints."""

from __future__ import annotations

import os
from urllib.parse import quote, urlsplit, urlunsplit


def canonical_public_url(value: str | None = None) -> str | None:
    """Return the normalized configured public URL, never a request-derived URL."""
    raw = (value if value is not None else os.getenv("FLOWHUB_PUBLIC_URL", "")).strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.query or parsed.fragment:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def public_webhook_url(provider: str, channel_id: str, *, public_url: str | None = None) -> str | None:
    """Build a provider webhook URL from the canonical configured public base."""
    base = canonical_public_url(public_url)
    if base is None:
        return None
    return f"{base}/api/v2/webhooks/{quote(provider, safe='')}/{quote(channel_id, safe='')}"
