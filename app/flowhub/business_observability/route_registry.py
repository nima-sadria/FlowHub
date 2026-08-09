"""Stable action-route identities for Business Event operator action links.

Per the Owner's amendment to the v1 spec: an indefinitely-retained
``business_event`` row must not embed a raw frontend URL, because a route
change years later would orphan historical events. Producers instead store
a stable ``route_key`` plus ``params``; this module resolves that pair to
the *current* frontend path at read time, so a frontend routing change only
requires updating this one registry.

If a ``route_key`` is retired, resolution simply returns ``None`` rather
than a dead link — the event remains visible, just without a deep link.
"""

from __future__ import annotations

ROUTE_REGISTRY: dict[str, str] = {
    "source.detail": "/sources/{source_id}",
    "channel.detail": "/channels/{channel_id}",
    "workspace.review": "/workspace/{workspace_id}",
    "workspace.home": "/workspace",
}


def resolve_action_route(route_key: str | None, params: dict[str, object]) -> str | None:
    """Resolve a stable route identity to a current frontend path, if possible."""

    if not route_key:
        return None
    template = ROUTE_REGISTRY.get(route_key)
    if template is None:
        return None
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return None
