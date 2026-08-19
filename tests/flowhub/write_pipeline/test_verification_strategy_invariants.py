"""Regression guard for ADR_CHANNEL_READ_ARCHITECTURE.md Invariant 7:

"Verification scope is never widened by Channel Read strategy selection."

WooCommerce Apply verification is already correctly scoped to
`CurrentStateStrategy.BATCH_BY_ID` (never a full-catalog scan, unlike
SnappShop's pre-existing `COLLECTION_SCAN`). Nothing type-checks that
strategy value at either call site, so a future edit could silently widen
it back to a collection scan without any contract breaking. These tests
exercise both real code paths that set it independently.
"""
from __future__ import annotations

import pytest

from app.connectors.common.auth import AuthConfig
from app.connectors.common.current_state import (
    CurrentStateIdentity,
    CurrentStateRequest,
    CurrentStateStrategy,
)
from app.connectors.destinations.woocommerce.auth import extract_credentials
from app.connectors.destinations.woocommerce.connector import WooCommerceConnector
from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
from app.flowhub.write_pipeline.adapters import ChannelWriteContext

_AUTH = AuthConfig(
    auth_type="api_key",
    credentials={"url": "https://shop.example.com", "key": "ck_abc", "secret": "cs_xyz"},
)


async def _list_batch(_creds, *, product_ids, transport, **_kwargs):
    transport.record_request(stage="product_batch_read", duration_ms=1, failed=False)
    return (
        [{"id": product_id, "regular_price": f"{product_id * 10}.00"} for product_id in product_ids],
        len(product_ids),
        1,
    )


def _verification_request() -> CurrentStateRequest:
    # Mirrors app/flowhub/unified_workspace/connectors.py's post-Apply
    # verification request shape exactly (purpose + zero staleness).
    return CurrentStateRequest(
        channel_id="woocommerce:primary",
        entities=(CurrentStateIdentity(key="listing-10", external_id="10"),),
        required_fields=frozenset({"price"}),
        purpose="post_apply_verification",
        max_staleness_seconds=0,
    )


@pytest.mark.asyncio
async def test_woocommerce_connector_verification_strategy_is_batch_by_id(monkeypatch):
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.connector.list_products_paged",
        _list_batch,
    )
    wc = WooCommerceConnector()
    wc._creds = extract_credentials(_AUTH)

    result = await wc.fetch_current_state(_verification_request())

    assert result.transport.strategy == CurrentStateStrategy.BATCH_BY_ID
    assert result.records["listing-10"].price == 100


@pytest.mark.asyncio
async def test_woocommerce_write_adapter_verification_strategy_is_batch_by_id(monkeypatch):
    # This is the adapter apply_updates() actually calls -- it builds its
    # own TransportRecorder rather than inheriting the connector's, so a
    # regression here would not be caught by the connector-level test above.
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.connector.list_products_paged",
        _list_batch,
    )
    adapter = WooCommercePriceWriteAdapter()
    context = ChannelWriteContext(
        get_setting=lambda key: {
            "woocommerce.url": "https://shop.example.com",
            "woocommerce.key": "ck_abc",
            "woocommerce.secret": "cs_xyz",
        }.get(key),
        requested_by="test",
    )

    result = await adapter.fetch_current_state(_verification_request(), context)

    assert result.transport.strategy == CurrentStateStrategy.BATCH_BY_ID
    assert result.records["listing-10"].price == 100
