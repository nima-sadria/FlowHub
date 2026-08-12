"""Isolated resolution tests for the canonical Channel Gateway.

These tests exercise only channel_id -> connector resolution. Provider
behavior (writes, verification, capabilities) is covered by the connector
tests in tests/flowhub/unified_workspace/test_connectors.py; it is
deliberately not re-exercised here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.flowhub.channels.gateway import WorkspaceConnectorFactory
from app.flowhub.unified_workspace.connectors import (
    SnappShopWorkspaceConnector,
    TapsiShopWorkspaceConnector,
    TechnolifeWorkspaceConnector,
    WooCommerceWorkspaceConnector,
)
from app.flowhub.unified_workspace.domain import WorkspaceDomainError


class _Config:
    values = {
        "server.currency": "EUR",
        "server.currency_unit": "EUR",
        "woocommerce.url": "https://shop.example.test",
    }

    def get(self, key):
        return self.values.get(key)


class _Pricing:
    config = _Config()

    @staticmethod
    def _safe_error(exc):
        return str(exc)


def _commerce() -> SimpleNamespace:
    return SimpleNamespace(
        _snappshop_connector=lambda: None,
        _tapsishop_connector=lambda: None,
        _technolife_connector=lambda: None,
    )


def _factory() -> WorkspaceConnectorFactory:
    return WorkspaceConnectorFactory(_Pricing(), _commerce())


@pytest.mark.parametrize(
    ("channel_id", "connector_type"),
    [
        ("woocommerce:primary", WooCommerceWorkspaceConnector),
        ("snappshop:main", SnappShopWorkspaceConnector),
        ("tapsishop:main", TapsiShopWorkspaceConnector),
        ("technolife:main", TechnolifeWorkspaceConnector),
    ],
)
def test_get_resolves_each_current_channel(channel_id, connector_type) -> None:
    connector = _factory().get(channel_id)
    assert isinstance(connector, connector_type)
    assert connector.channel_id == channel_id


@pytest.mark.parametrize(
    "channel_id",
    ["woocommerce:primary", "snappshop:main", "tapsishop:main", "technolife:main"],
)
def test_get_product_pricing_resolves_each_current_channel(channel_id) -> None:
    connector = _factory().get_product_pricing(channel_id)
    assert connector.channel_id == channel_id


def test_implemented_lists_exactly_the_four_current_channels() -> None:
    channel_ids = {connector.channel_id for connector in _factory().implemented()}
    assert channel_ids == {
        "woocommerce:primary",
        "snappshop:main",
        "tapsishop:main",
        "technolife:main",
    }


def test_digikala_stays_fail_closed_in_the_write_gateway() -> None:
    with pytest.raises(WorkspaceDomainError):
        _factory().get("digikala:main")


def test_digikala_product_pricing_stays_fail_closed_in_the_write_gateway() -> None:
    with pytest.raises(WorkspaceDomainError):
        _factory().get_product_pricing("digikala:main")
