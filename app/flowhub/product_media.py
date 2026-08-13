"""Provider-neutral product media normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def normalize_product_media(
    entries: object,
    *,
    source: str | None = None,
) -> list[dict[str, Any]]:
    """Return ordered, safe image media without provider payload details.

    Product image URLs are persisted without query strings, fragments, or
    embedded credentials. Malformed entries are ignored so media can never
    make an otherwise valid product fail normalization.
    """

    if not isinstance(entries, Iterable) or isinstance(entries, (str, bytes, dict)):
        return []

    media: list[dict[str, Any]] = []
    for position, entry in enumerate(entries):
        raw_url: object = entry
        entry_source = source
        if isinstance(entry, dict):
            raw_url = entry.get("url") or entry.get("src")
            entry_source = _text(entry.get("source")) or source
        url = sanitize_media_url(raw_url)
        if url is None:
            continue
        item: dict[str, Any] = {
            "type": "image",
            "url": url,
            "position": position,
        }
        if entry_source:
            item["source"] = entry_source
        media.append(item)
    return media


def primary_image_url(entries: object) -> str | None:
    """Return the first valid image URL from canonical or legacy media."""

    media = normalize_product_media(entries)
    return str(media[0]["url"]) if media else None


def sanitize_media_url(value: object) -> str | None:
    """Sanitize a public HTTP(S) media URL for durable storage."""

    text = _text(value)
    if not text:
        return None
    try:
        parsed = urlsplit(text)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = parsed.port
        netloc = f"{host}:{port}" if port is not None else host
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
