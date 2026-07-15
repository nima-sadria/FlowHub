from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.setup.service import AppConfigService
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.models import (
    ApplyJob,
    CanonicalProduct,
    ChannelCache,
    Listing,
    Review,
    WorkspaceChannel,
    WorkspaceSnapshot,
)


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
            WorkspaceChannel(
                id="tapsishop:main",
                connector_type="tapsishop",
                name="TapsiShop",
                implementation_state="implemented",
                capabilities_json={"price": {"read": True, "write": True}},
                capability_version="tapsi-1",
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
    coming_soon = next(
        item for item in service.available_channels()["items"]
        if item["channelId"] == "digikala:coming-soon"
    )
    assert coming_soon["available"] is False
    assert coming_soon["implementationState"] == "coming_soon"


def test_one_source_resolves_three_independent_channel_targets_and_preserves_disabled_mapping() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    product = CanonicalProduct(
        id="product-cable",
        name="iPhone Cable",
        sku="CABLE",
        product_type="simple",
        status="active",
    )
    listings = [
        Listing(
            id="listing-wc",
            canonical_product_id=product.id,
            channel_id="woocommerce:primary",
            external_primary_id="51550",
            external_id_type="product_id",
            label="WooCommerce",
            mapping_state="resolved",
            mapping_version=1,
        ),
        Listing(
            id="listing-snap",
            canonical_product_id=product.id,
            channel_id="snappshop:main",
            external_primary_id="1826345203",
            external_id_type="product_number",
            label="SnappShop",
            mapping_state="resolved",
            mapping_version=1,
        ),
        Listing(
            id="listing-tapsi",
            canonical_product_id=product.id,
            channel_id="tapsishop:main",
            external_primary_id="7785746738",
            external_id_type="seller_sku",
            label="TapsiShop",
            mapping_state="resolved",
            mapping_version=1,
        ),
    ]
    caches = [
        ChannelCache(
            id=f"cache-{listing.id}",
            listing_id=listing.id,
            channel_id=listing.channel_id,
            price_raw="1",
            price_currency="IRR",
            price_unit="RIAL",
            stock_quantity=1,
            status="active",
            cache_version=1,
            checksum=f"checksum-{listing.id}",
            connector_version="1",
            freshness="fresh",
            fetch_status="success",
            fetched_at=datetime.utcnow(),
        )
        for listing in listings
    ]
    db.add_all([product, *listings, *caches])
    db.commit()

    sheet = service.create_sheet(
        name="Independent targets",
        columns=[
            {"column_key": "name", "name": "نام محصول", "position": 1},
            {"column_key": "wc-id", "name": "Woo ID", "position": 2},
            {"column_key": "wc-price", "name": "Woo Price", "position": 3},
            {"column_key": "wc-stock", "name": "Woo Stock", "position": 4},
            {"column_key": "snap-price", "name": "قیمت اسنپ", "position": 7},
            {"column_key": "tapsi-price", "name": "Tapsi Price", "position": 10},
            {"column_key": "snap-id", "name": "SNP", "position": 15},
            {"column_key": "tapsi-id", "name": "Seller SKU", "position": 16},
        ],
        user=user,
    )
    sheet = service.append_sheet_rows(
        sheet_id=sheet["id"], expected_version=sheet["version"], count=1, user=user
    )
    row_key = sheet["rows"][0]["rowKey"]
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {"row_key": row_key, "column_key": "name", "value": "کابل آیفون"},
            {"row_key": row_key, "column_key": "wc-id", "value": "51550"},
            {"row_key": row_key, "column_key": "wc-price", "value": "12500000"},
            {"row_key": row_key, "column_key": "wc-stock", "value": "8"},
            {"row_key": row_key, "column_key": "snap-id", "value": "1826345203"},
            {"row_key": row_key, "column_key": "snap-price", "value": "12900000"},
            {"row_key": row_key, "column_key": "tapsi-id", "value": "7785746738"},
            {"row_key": row_key, "column_key": "tapsi-price", "value": "12700000"},
        ],
        user=user,
    )
    source = service.get_source(sheet["sourceId"], user)
    source_fields = [
        {"field": "name", "reference_type": "column_letter", "reference_value": "A", "required": True}
    ]
    channel_mappings = [
        {
            "channel_id": "woocommerce:primary",
            "enabled": True,
            "fields": [
                {"field": "external_id", "reference_type": "column_letter", "reference_value": "B"},
                {"field": "price", "reference_type": "column_letter", "reference_value": "C"},
                {"field": "stock", "reference_type": "column_letter", "reference_value": "D"},
                {"field": "status", "reference_type": "disabled", "reference_value": None},
            ],
        },
        {
            "channel_id": "snappshop:main",
            "enabled": True,
            "fields": [
                {"field": "external_id", "reference_type": "column_letter", "reference_value": "O"},
                {"field": "price", "reference_type": "header_name", "reference_value": "قیمت اسنپ"},
                {"field": "stock", "reference_type": "disabled", "reference_value": None},
                {"field": "status", "reference_type": "disabled", "reference_value": None},
            ],
        },
        {
            "channel_id": "tapsishop:main",
            "enabled": True,
            "fields": [
                {"field": "external_id", "reference_type": "column_id", "reference_value": "tapsi-id"},
                {"field": "price", "reference_type": "column_letter", "reference_value": "J"},
                {"field": "stock", "reference_type": "disabled", "reference_value": None},
                {"field": "status", "reference_type": "disabled", "reference_value": None},
            ],
        },
    ]
    service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=source_fields,
        channel_mappings=channel_mappings,
        value_policy={},
        user=user,
    )
    analysis = asyncio.run(service.snapshot_candidates(source["id"], user))
    targets = {item["channelId"]: item["targets"] for item in analysis["candidates"]}
    assert targets == {
        "woocommerce:primary": {"price": "12500000", "stock": "8"},
        "snappshop:main": {"price": "12900000"},
        "tapsishop:main": {"price": "12700000"},
    }

    updated_source = service.get_source(source["id"], user)
    disabled_revision = service.save_mapping(
        source_id=source["id"],
        expected_source_version=updated_source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=source_fields,
        channel_mappings=[
            mapping | {"enabled": mapping["channel_id"] != "snappshop:main"}
            for mapping in channel_mappings
        ],
        value_policy={},
        user=user,
    )
    disabled_snap = next(
        item for item in disabled_revision["channels"] if item["channelId"] == "snappshop:main"
    )
    assert disabled_snap["enabled"] is False
    assert next(item for item in disabled_snap["fields"] if item["field"] == "price")["referenceValue"] == "قیمت اسنپ"
    disabled_analysis = asyncio.run(service.snapshot_candidates(source["id"], user))
    assert {item["channelId"] for item in disabled_analysis["candidates"]} == {
        "woocommerce:primary",
        "tapsishop:main",
    }


def test_external_source_is_read_once_and_resolves_three_independent_channel_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    product = CanonicalProduct(
        id="product-external-cable",
        name="iPhone Cable",
        sku="CABLE-EXT",
        product_type="simple",
        status="active",
    )
    listing_specs = [
        ("listing-external-wc", "woocommerce:primary", "51550", "product_id"),
        ("listing-external-snap", "snappshop:main", "1826345203", "product_number"),
        ("listing-external-tapsi", "tapsishop:main", "7785746738", "seller_sku"),
    ]
    listings = [
        Listing(
            id=listing_id,
            canonical_product_id=product.id,
            channel_id=channel_id,
            external_primary_id=external_id,
            external_id_type=id_type,
            label=channel_id,
            mapping_state="resolved",
            mapping_version=1,
        )
        for listing_id, channel_id, external_id, id_type in listing_specs
    ]
    db.add_all(
        [
            product,
            *listings,
            *[
                ChannelCache(
                    id=f"cache-{listing.id}",
                    listing_id=listing.id,
                    channel_id=listing.channel_id,
                    price_raw="1",
                    price_currency="IRR",
                    price_unit="RIAL",
                    stock_quantity=1,
                    status="active",
                    cache_version=1,
                    checksum=f"checksum-{listing.id}",
                    connector_version="1",
                    freshness="fresh",
                    fetch_status="success",
                    fetched_at=datetime.utcnow(),
                )
                for listing in listings
            ],
        ]
    )
    db.commit()
    source = service.create_source(
        name="External multi-channel Source",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=2,
        user=user,
    )
    service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=2,
        source_fields=[
            {"field": "name", "reference_type": "column_letter", "reference_value": "A", "required": True}
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "B"},
                    {"field": "price", "reference_type": "column_letter", "reference_value": "C"},
                ],
            },
            {
                "channel_id": "snappshop:main",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "O"},
                    {"field": "price", "reference_type": "header_name", "reference_value": "قیمت اسنپ"},
                ],
            },
            {
                "channel_id": "tapsishop:main",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "P"},
                    {"field": "price", "reference_type": "column_letter", "reference_value": "J"},
                ],
            },
        ],
        value_policy={},
        user=user,
    )
    read_count = 0
    rows = [
        ["نام محصول", "Woo ID", "Woo Price", "Woo Stock", None, None, "قیمت اسنپ", None, None, "Tapsi Price", None, None, None, None, "SNP", "Seller SKU"],
        ["کابل آیفون", "51550", "12500000", "8", None, None, "12900000", None, None, "12700000", None, None, None, None, "1826345203", "7785746738"],
    ]

    async def fake_read_external_source(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal read_count
        read_count += 1
        return SimpleNamespace(
            snapshot=SimpleNamespace(id="source-snapshot-1", version_seq=1, integrity_hash="f" * 64),
            worksheets={"Sheet1": rows},
        )

    monkeypatch.setattr(service, "_read_external_source", fake_read_external_source)
    analysis = asyncio.run(service.snapshot_candidates(source["id"], user))
    assert read_count == 1
    assert {item["channelId"]: item["targets"] for item in analysis["candidates"]} == {
        "woocommerce:primary": {"price": "12500000"},
        "snappshop:main": {"price": "12900000"},
        "tapsishop:main": {"price": "12700000"},
    }


def test_new_source_mapping_revision_invalidates_review_and_pending_apply() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    sheet = service.create_sheet(
        name="Review invalidation",
        columns=[
            {"column_key": "name", "name": "Name", "position": 1},
            {"column_key": "wc-id", "name": "Woo ID", "position": 2},
        ],
        user=user,
    )
    source = service.get_source(sheet["sourceId"], user)
    mapping_fields = [
        {"field": "name", "reference_type": "column_id", "reference_value": "name", "required": True}
    ]
    channel_mappings = [
        {
            "channel_id": "woocommerce:primary",
            "fields": [
                {"field": "external_id", "reference_type": "column_id", "reference_value": "wc-id"}
            ],
        }
    ]
    service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=mapping_fields,
        channel_mappings=channel_mappings,
        value_policy={},
        user=user,
    )
    db.add(
        WorkspaceSnapshot(
            id="snapshot-source-mapping",
            workspace_id="workspace-source-mapping",
            entry_point="source",
            source_type="flowhub_sheet",
            creator_user_id=user.id,
            schema_version="test",
            content_checksum="a" * 64,
            normalization_version="test",
            validation_ruleset_version="test",
            mapping_version=1,
            currency_profile_id="currency-test",
            source_metadata_json={"source_id": source["id"]},
            acquisition_metadata_json={},
        )
    )
    db.add(
        Review(
            id="review-source-mapping",
            workspace_id="workspace-source-mapping",
            snapshot_id="snapshot-source-mapping",
            draft_revision_id="draft-revision-test",
            created_by_user_id=user.id,
            status="ready",
            ruleset_version="test",
            capability_digest="b" * 64,
            currency_digest="c" * 64,
            currency_profile_id="currency-test",
            currency_profile_version=1,
            currency_profile_checksum="d" * 64,
            currency_source_reference="global",
            currency_channel_references_json=[],
            currency_ruleset_version="test",
            mapping_digest="e" * 64,
            checksum="f" * 64,
            summary_json={},
            selection_version=1,
            selection_checksum="1" * 64,
            selected_channel_ids_json=["woocommerce:primary"],
        )
    )
    db.add(
        ApplyJob(
            id="apply-source-mapping",
            workspace_id="workspace-source-mapping",
            snapshot_id="snapshot-source-mapping",
            draft_revision_id="draft-revision-test",
            review_id="review-source-mapping",
            requested_by_user_id=user.id,
            idempotency_key="source-mapping-idempotency",
            logical_operation_key="2" * 64,
            correlation_id="source-mapping-correlation",
            selection_checksum="1" * 64,
            request_json={},
            status="pending",
            operation_checksum="3" * 64,
        )
    )
    db.commit()
    current = service.get_source(source["id"], user)
    service.save_mapping(
        source_id=source["id"],
        expected_source_version=current["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=mapping_fields,
        channel_mappings=channel_mappings,
        value_policy={"blank": "blocked"},
        user=user,
    )
    review = db.get(Review, "review-source-mapping")
    job = db.get(ApplyJob, "apply-source-mapping")
    assert review is not None and review.status == "stale"
    assert review.stale_reason == "source_mapping_revision_changed"
    assert review.selection_checksum is None
    assert job is not None and job.status == "stale"


def test_legacy_global_mapping_is_exposed_only_for_woocommerce_confirmation() -> None:
    db = _session()
    user = _user(db)
    AppConfigService(db).set(
        "nextcloud.source_mapping",
        '{"id":{"enabled":true,"column":"B"},"price":{"enabled":true,"column":"C"},"stock":{"enabled":false,"column":"D"}}',
    )
    service = SourceWorkspaceService(db)
    source = service.create_source(
        name="Legacy Nextcloud",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=2,
        user=user,
    )
    loaded = service.get_source(source["id"], user)
    assert loaded["mapping"] is None
    assert loaded["legacyMapping"]["primaryChannelId"] == "woocommerce:primary"
    assert loaded["legacyMapping"]["requiresConfirmation"] is True
    assert {item["field"] for item in loaded["legacyMapping"]["fields"]} == {
        "external_id",
        "price",
        "stock",
        "status",
    }


def test_channel_added_after_source_creation_can_receive_its_own_mapping() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    sheet = service.create_sheet(
        name="Future channel",
        columns=[
            {"column_key": "name", "name": "Name", "position": 1},
            {"column_key": "market-id", "name": "Marketplace ID", "position": 2},
            {"column_key": "market-price", "name": "Marketplace Price", "position": 3},
        ],
        user=user,
    )
    source = service.get_source(sheet["sourceId"], user)
    db.add(
        WorkspaceChannel(
            id="marketplace:new",
            connector_type="marketplace",
            name="New Marketplace",
            implementation_state="implemented",
            capabilities_json={"price": {"read": True, "write": True}},
            capability_version="market-1",
            enabled=True,
        )
    )
    db.commit()
    mapping = service.save_mapping(
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
                "channel_id": "marketplace:new",
                "fields": [
                    {"field": "external_id", "reference_type": "column_id", "reference_value": "market-id"},
                    {"field": "price", "reference_type": "column_id", "reference_value": "market-price"},
                    {"field": "stock", "reference_type": "disabled", "reference_value": None},
                    {"field": "status", "reference_type": "disabled", "reference_value": None},
                ],
            }
        ],
        value_policy={},
        user=user,
    )
    assert mapping["channels"][0]["channelId"] == "marketplace:new"
    assert mapping["channels"][0]["enabled"] is True
    assert any(
        item["channelId"] == "marketplace:new" and item["available"] is True
        for item in service.available_channels()["items"]
    )


def test_coming_soon_channel_cannot_be_enabled_for_source_processing() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    sheet = service.create_sheet(
        name="Blocked Channel",
        columns=[
            {"column_key": "name", "name": "Name", "position": 1},
            {"column_key": "id", "name": "ID", "position": 2},
        ],
        user=user,
    )
    source = service.get_source(sheet["sourceId"], user)
    try:
        service.save_mapping(
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
                    "channel_id": "digikala:coming-soon",
                    "enabled": True,
                    "fields": [
                        {"field": "external_id", "reference_type": "column_id", "reference_value": "id"}
                    ],
                }
            ],
            value_policy={},
            user=user,
        )
    except Exception as exc:
        assert getattr(exc, "detail", {}).get("code") == "CHANNEL_UNAVAILABLE"
    else:
        raise AssertionError("Coming Soon Channel mapping unexpectedly participated")


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
