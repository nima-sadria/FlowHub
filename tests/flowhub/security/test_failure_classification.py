"""Honest attribution for failures surfaced as channel/source errors.

Production evidence (2026-08-18) showed 13 WooCommerce webhook receipts
dead-lettered with an error body that was the literal serialized
``normalize_upstream_error`` dict, every one carrying
``code: CHANNEL_UPSTREAM_ERROR`` and ``error_category: "temporary"`` -- while
the same store's ``/orders`` endpoint was answering 200 OK throughout. The
"upstream" label was the catch-all ``else`` branch, not evidence about
WooCommerce.

These tests pin the distinction the catch-all erased: an exception is only
attributed to the external service when something actually came from (or
failed against) that service.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.flowhub.data_layer.job_lifecycle import RefreshJobAlreadyRunning
from app.flowhub.security.upstream_errors import (
    CATEGORY_AUTH_FAILED,
    CATEGORY_INTERNAL_ERROR,
    CATEGORY_TIMEOUT,
    CATEGORY_UPSTREAM_UNAVAILABLE,
    PUBLIC_ERROR_KEYS,
    classify_failure,
    normalize_upstream_error,
)


def test_public_payload_shape_is_unchanged_by_the_honest_taxonomy():
    """The over-the-wire contract must stay byte-compatible.

    Consumers assert on this exact dict, so `category` /
    `upstream_attributable` live only in `classify_failure`.
    """

    payload = normalize_upstream_error(
        ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="Unexpected WooCommerce status: HTTP 500",
            provider="woocommerce",
            http_status=500,
        ),
        source="woocommerce",
    )

    assert tuple(payload) == PUBLIC_ERROR_KEYS
    assert payload["code"] == "CHANNEL_UPSTREAM_ERROR"


def test_cloudflare_522_is_a_genuine_upstream_failure():
    """522 is Cloudflare reaching the origin and the origin never answering.

    It is NOT in the client's retry set, so it surfaces as PROVIDER_ERROR with
    the status attached -- exactly the shape the six earliest production dead
    letters carried on attempt #1.
    """

    result = classify_failure(
        ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="Unexpected WooCommerce status: HTTP 522",
            provider="woocommerce",
            http_status=522,
        ),
        source="woocommerce",
    )

    assert result["code"] == "CHANNEL_UPSTREAM_ERROR"
    assert result["http_status"] == 522
    assert result["category"] == CATEGORY_UPSTREAM_UNAVAILABLE
    assert result["upstream_attributable"] is True


def test_internal_lease_conflict_is_never_blamed_on_woocommerce():
    """The regression that produced http_status=None dead letters.

    `RefreshJobAlreadyRunning` is raised by FlowHub's own single-flight lease
    before any provider call happens. Classifying it as CHANNEL_UPSTREAM_ERROR
    told the Owner their store was broken when nothing had been contacted.
    """

    result = classify_failure(RefreshJobAlreadyRunning(4321), source="woocommerce")

    assert result["code"] == "CHANNEL_INTERNAL_ERROR"
    assert result["category"] == CATEGORY_INTERNAL_ERROR
    assert result["upstream_attributable"] is False
    assert result["source"] == "flowhub"
    # The public message must stay generic and non-leaky.
    assert "4321" not in result["message"]


@pytest.mark.parametrize(
    "error",
    [
        KeyError("product_id"),
        AttributeError("'NoneType' object has no attribute 'products_read'"),
        TypeError("unsupported operand type(s)"),
        ValueError("invalid literal for int()"),
        OperationalError("SELECT 1", {}, Exception("database is locked")),
    ],
    ids=["keyerror", "attributeerror", "typeerror", "valueerror", "sqlalchemy"],
)
def test_internal_bugs_are_classified_as_internal_not_upstream(error):
    """A bug in normalization or persistence is FlowHub's failure.

    These all reach `refresh_channel_cache`'s blanket `except Exception`, which
    sits around the persistence work too -- not just the provider I/O.
    """

    result = classify_failure(error, source="woocommerce")

    assert result["category"] == CATEGORY_INTERNAL_ERROR
    assert result["upstream_attributable"] is False
    assert result["code"] == "CHANNEL_INTERNAL_ERROR"


@pytest.mark.parametrize(
    ("error", "expected_category", "expected_code"),
    [
        (
            ConnectorError(
                code=ConnectorErrorCode.TIMEOUT,
                message="WooCommerce request timed out",
                provider="woocommerce",
            ),
            CATEGORY_TIMEOUT,
            "CHANNEL_TIMEOUT",
        ),
        (
            ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="WooCommerce authentication failed",
                provider="woocommerce",
                http_status=401,
            ),
            CATEGORY_AUTH_FAILED,
            "CHANNEL_AUTH_FAILED",
        ),
        (
            ConnectorError(
                code=ConnectorErrorCode.NETWORK,
                message="WooCommerce connection failed.",
                provider="woocommerce",
            ),
            CATEGORY_UPSTREAM_UNAVAILABLE,
            "CHANNEL_UPSTREAM_ERROR",
        ),
    ],
    ids=["timeout", "auth", "network"],
)
def test_typed_connector_errors_stay_upstream_attributable(
    error, expected_category, expected_code
):
    result = classify_failure(error, source="woocommerce")

    assert result["category"] == expected_category
    assert result["code"] == expected_code
    assert result["upstream_attributable"] is True


def test_raw_httpx_transport_errors_are_upstream_attributable():
    """An httpx error escaping the provider call is real network evidence,
    even when it was never wrapped in a ConnectorError."""

    result = classify_failure(
        httpx.ConnectTimeout("timed out"), source="woocommerce"
    )

    assert result["upstream_attributable"] is True


def test_unsafe_upstream_bodies_stay_upstream_and_never_leak():
    result = classify_failure(
        Exception("<!DOCTYPE html><html><body>cloudflare secret=cs_live_x</body></html>"),
        source="woocommerce",
    )

    assert result["upstream_attributable"] is True
    assert result["category"] == CATEGORY_UPSTREAM_UNAVAILABLE
    assert "cs_live_x" not in result["message"]
    assert "<html" not in result["message"].lower()
