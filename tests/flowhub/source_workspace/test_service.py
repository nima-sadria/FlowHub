from __future__ import annotations

import base64

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.models import WorkspaceChannel


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _user(db: Session) -> FlowHubUser:
    user = FlowHubUser(id=1, username="owner", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.add_all(
        [
            WorkspaceChannel(
                id="woocommerce:primary",
                connector_type="woocommerce",
                name="WooCommerce",
                implementation_state="implemented",
                capabilities_json={"price": {"read": True, "write": True}},
                capability_version="wc-1",
                enabled=True,
            ),
            WorkspaceChannel(
                id="snappshop:main",
                connector_type="snappshop",
                name="SnappShop",
                implementation_state="implemented",
                capabilities_json={"price": {"read": True, "write": True}},
                capability_version="snap-1",
                enabled=True,
            ),
            WorkspaceChannel(
                id="digikala:coming-soon",
                connector_type="digikala",
                name="Digikala",
                implementation_state="coming_soon",
                capabilities_json={},
                capability_version="none",
                enabled=True,
            ),
        ]
    )
    db.commit()
    return user


def test_sheet_revisions_are_batched_versioned_and_formula_calculated() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    sheet = service.create_sheet(
        name="Pricing",
        columns=[
            {"column_key": "name", "name": "نام کالا", "position": 1},
            {"column_key": "cost", "name": "Cost", "position": 2},
            {"column_key": "target", "name": "Target", "position": 3},
        ],
        user=user,
    )
    sheet = service.append_sheet_rows(
        sheet_id=sheet["id"], expected_version=sheet["version"], count=2, user=user
    )
    first = sheet["rows"][0]
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {"row_key": first["rowKey"], "column_key": "name", "value": "کابل آیفون"},
            {"row_key": first["rowKey"], "column_key": "cost", "value": "100"},
            {"row_key": first["rowKey"], "column_key": "target", "value": "=B1*1.2"},
        ],
        user=user,
    )
    assert sheet["version"] == 3
    assert sheet["rows"][0]["cells"]["target"]["value"] == "120"
    assert sheet["rows"][0]["cells"]["target"]["formula"] == "=B1*1.2"


def test_mapping_supports_arbitrary_columns_multiple_channels_and_conservative_policy() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    sheet = service.create_sheet(
        name="Irregular",
        columns=[
            {"column_key": "notes", "name": "یادداشت", "position": 1},
            {"column_key": "name", "name": "نام محصول", "position": 2},
            {"column_key": "wc-id", "name": "شناسه وو", "position": 15},
            {"column_key": "wc-price", "name": "قیمت وو", "position": 7},
            {"column_key": "snap-id", "name": "شماره اسنپ", "position": 16},
        ],
        user=user,
    )
    source = service.get_source(sheet["sourceId"], user)
    mapping = service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=3,
        source_fields=[
            {"field": "name", "reference_type": "header_name", "reference_value": "نام محصول", "required": True},
            {"field": "source_key", "reference_type": "disabled", "reference_value": None},
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "O"},
                    {"field": "price", "reference_type": "column_id", "reference_value": "wc-price"},
                ],
            },
            {
                "channel_id": "snappshop:main",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "P"},
                    {"field": "stock", "reference_type": "disabled", "reference_value": None},
                ],
            },
        ],
        value_policy={},
        user=user,
    )
    assert mapping["version"] == 1
    assert {item["channelId"] for item in mapping["channels"]} == {
        "woocommerce:primary",
        "snappshop:main",
    }
    assert mapping["valuePolicy"]["blank"] == "no_change"
    assert "digikala:coming-soon" not in {
        item["channelId"] for item in service.available_channels()["items"]
    }


def test_csv_import_preserves_original_bytes_and_metadata() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    original = "نام,قیمت\nکابل,120\n".encode()
    encoded = base64.b64encode(original).decode()
    preview = service.preview_import(
        filename="pricing.csv", content_base64=encoded, worksheet_name=None
    )
    imported = service.import_sheet(
        name="Imported",
        filename="pricing.csv",
        content_base64=encoded,
        worksheet_name="Sheet1",
        expected_checksum=preview["sourceChecksum"],
        data_start_row=2,
        user=user,
    )
    assert base64.b64decode(encoded) == original
    assert imported["total"] == 2
    assert imported["columns"][0]["name"] == "نام"


def test_special_source_values_are_conservative_and_distinct() -> None:
    policy = {
        "blank": "no_change",
        "x": "unavailable",
        "dash": "no_change",
        "zero": "explicit_zero",
        "formula": "calculated_value",
        "invalid": "blocked",
    }
    interpret = SourceWorkspaceService._interpret_target
    assert interpret("", "price", policy)["target"] is None
    assert interpret("x", "price", policy)["target"] is None
    assert interpret("-", "price", policy)["target"] is None
    assert interpret("0", "price", policy)["target"] == "0"
    assert interpret("not-a-number", "price", policy)["issue"] == "INVALID_NUMERIC_VALUE"
    blocked_zero = {**policy, "zero": "blocked"}
    assert interpret("0", "stock", blocked_zero)["issue"] == "ZERO_VALUE_BLOCKED"
