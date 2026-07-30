from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.flowhub.api.v2.exchange_rates import SelectionUpdate, _require_super_admin
from app.flowhub.auth.models import FlowHubUser


def test_selection_contract_requires_three_unique_items():
    assert SelectionUpdate(selections=["usd_sell", "eur", "aed_sell"]).selections == ["usd_sell", "eur", "aed_sell"]
    with pytest.raises(ValueError):
        SelectionUpdate(selections=["usd_sell", "usd_sell", "aed_sell"])
    with pytest.raises(ValueError):
        SelectionUpdate(selections=["usd_sell", " usd_sell ", "aed_sell"])


def test_normal_user_is_rejected_from_admin_actions():
    viewer = FlowHubUser(username="viewer", hashed_password="x", role="viewer", is_active=True)
    with pytest.raises(HTTPException) as exc:
        _require_super_admin(viewer)
    assert exc.value.status_code == 403
