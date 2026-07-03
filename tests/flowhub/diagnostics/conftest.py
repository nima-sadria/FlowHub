"""Shared fixtures for diagnostic runner tests."""

from __future__ import annotations

import pytest

from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
from app.flowhub.connections.adapters import (
    DNSResolutionError,
    TCPConnectionError,
    TLSHandshakeError,
    ConnectionTimeoutError,
    AuthenticationError,
    AccessForbiddenError,
)
from app.flowhub.diagnostics.runner import DiagnosticRunner


@pytest.fixture
def test_double_adapter() -> TestDoubleNetworkAdapter:
    return TestDoubleNetworkAdapter()


@pytest.fixture
def runner(test_double_adapter: TestDoubleNetworkAdapter) -> DiagnosticRunner:
    return DiagnosticRunner(adapter=test_double_adapter, config={})


@pytest.fixture
def runner_with_config(test_double_adapter: TestDoubleNetworkAdapter) -> DiagnosticRunner:
    config = {
        "FLOWHUB_NEXTCLOUD_URL": "https://nextcloud.example.com",
        "FLOWHUB_NEXTCLOUD_USERNAME": "admin",
        "FLOWHUB_NEXTCLOUD_PASSWORD": "secret123",
        "FLOWHUB_WOOCOMMERCE_URL": "https://shop.example.com",
        "FLOWHUB_WOOCOMMERCE_KEY": "ck_abc",
        "FLOWHUB_WOOCOMMERCE_SECRET": "cs_xyz",
    }
    return DiagnosticRunner(adapter=test_double_adapter, config=config)
