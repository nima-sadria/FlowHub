"""Shared fixtures for BU5 API v2 tests."""

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the in-memory login rate limiter before each test.

    Multiple test files each log in once; without this the shared deque
    fills up and triggers HTTP 429 mid-suite.
    """
    from app.flowhub.auth.rate_limiter import clear_all
    clear_all()
    yield
    clear_all()
