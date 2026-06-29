"""Shared fixtures for BU5 API v2 tests."""

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-memory login rate limiter before each test.

    Multiple test files each log in once; without this the shared deque
    fills up and triggers HTTP 429 mid-suite.
    """
    from app.beta.auth.rate_limiter import clear_all
    clear_all()
    yield
    clear_all()
