"""Shared fixtures for health engine tests.

Imports TestDoubleNetworkAdapter from the connection tests conftest so there is one
canonical test_double - no duplication.
"""

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
from app.flowhub.health.engine import HealthEngine


@pytest.fixture
def test_double_adapter() -> TestDoubleNetworkAdapter:
    return TestDoubleNetworkAdapter()


@pytest.fixture
def engine(test_double_adapter) -> HealthEngine:
    return HealthEngine(adapter=test_double_adapter)
