"""Stable action-route resolution tests."""

from __future__ import annotations

from app.flowhub.business_observability.route_registry import resolve_action_route


def test_resolves_known_route_with_params() -> None:
    url = resolve_action_route("source.detail", {"source_id": "source-1"})
    assert url == "/sources/source-1"


def test_resolves_known_route_without_params() -> None:
    assert resolve_action_route("workspace.home", {}) == "/workspace"


def test_returns_none_for_unknown_route_key() -> None:
    assert resolve_action_route("no.such.route", {"foo": "bar"}) is None


def test_returns_none_when_route_key_is_absent() -> None:
    assert resolve_action_route(None, {}) is None


def test_returns_none_when_required_param_is_missing() -> None:
    assert resolve_action_route("channel.detail", {}) is None
