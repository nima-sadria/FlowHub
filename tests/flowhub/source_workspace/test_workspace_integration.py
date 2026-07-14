from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.data_layer.models import DlProductCache
from app.flowhub.database import FlowHubBase
from app.flowhub.setup.service import AppConfigService
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.services import UnifiedWorkspaceService


def test_source_product_workspace_groups_listings_and_auto_selects_ready_changes() -> None:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    db = Session(engine)
    user = FlowHubUser(id=1, username="owner", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    AppConfigService(db).set("server.currency", "EUR")
    AppConfigService(db).set("server.currency_unit", "EUR")
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            external_id=101,
            sku="CABLE-101",
            name="iPhone Cable",
            product_type="simple",
            price="100",
            regular_price="100",
            stock_qty=5,
            status="publish",
            stock_status="instock",
            manage_stock=True,
            freshness="fresh",
            last_fetched_at=datetime.utcnow(),
            last_successful_read=datetime.utcnow(),
            exists=True,
            record_hash="cache-101",
        )
    )
    db.commit()
    workspace_service = UnifiedWorkspaceService(db)
    workspace_service.create_manual_workspace(
        name="materialize",
        selections=[{"connector_id": "woocommerce:primary", "product_id": "101"}],
        user=user,
        correlation_id="materialize",
    )
    source_service = SourceWorkspaceService(db)
    sheet = source_service.create_sheet(
        name="Daily prices",
        columns=[
            {"column_key": "name", "name": "Product", "position": 1},
            {"column_key": "wc-id", "name": "Woo ID", "position": 2},
            {"column_key": "wc-price", "name": "Woo Price", "position": 3},
        ],
        user=user,
    )
    sheet = source_service.append_sheet_rows(
        sheet_id=sheet["id"], expected_version=sheet["version"], count=1, user=user
    )
    row_key = sheet["rows"][0]["rowKey"]
    sheet = source_service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {"row_key": row_key, "column_key": "name", "value": "iPhone Cable"},
            {"row_key": row_key, "column_key": "wc-id", "value": "101"},
            {"row_key": row_key, "column_key": "wc-price", "value": "125"},
        ],
        user=user,
    )
    source = source_service.get_source(sheet["sourceId"], user)
    source_service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=[
            {"field": "name", "reference_type": "column_id", "reference_value": "name", "required": True}
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {"field": "external_id", "reference_type": "column_id", "reference_value": "wc-id"},
                    {"field": "price", "reference_type": "column_id", "reference_value": "wc-price"},
                ],
            }
        ],
        value_policy={},
        user=user,
    )
    workspace = asyncio.run(
        workspace_service.create_source_workspace(
            name="Daily Source Workspace",
            source_id=source["id"],
            source_currency=None,
            source_unit=None,
            user=user,
            correlation_id="source-create",
        )
    )
    assert workspace["sourceAnalysis"]["detectedChanges"] == 1
    assert workspace["sourceAnalysis"]["automaticallySelected"] == 1
    grouped = workspace_service.grouped_grid(
        workspace["id"], user, page=1, page_size=100, search=None, view="changed"
    )
    assert grouped["total"] == 1
    assert grouped["items"][0]["name"] == "iPhone Cable"
    assert grouped["items"][0]["children"][0]["listingId"]
    assert grouped["items"][0]["children"][0]["fields"]["price"]["target"] == "125"
    assert grouped["summary"]["selected"] == 1
