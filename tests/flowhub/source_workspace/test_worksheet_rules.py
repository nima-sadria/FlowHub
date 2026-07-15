from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.api.v2.source_workspace import (
    MappingSaveRequest,
    SourcePreviewResponse,
    save_source_mapping,
)
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_workspace.models import (
    SourceChannelFieldMapping,
    SourceChannelMapping,
    SourceFieldMapping,
    SourceMappingRevision,
)
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.domain import checksum
from app.flowhub.unified_workspace.models import (
    CanonicalProduct,
    ChannelCache,
    Listing,
    WorkspaceChannel,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _user_and_channels(db: Session) -> FlowHubUser:
    user = FlowHubUser(
        id=1, username="owner", hashed_password="x", role="admin", is_active=True
    )
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
        ]
    )
    db.commit()
    return user


def _external_source(service: SourceWorkspaceService, user: FlowHubUser) -> dict[str, object]:
    return service.create_source(
        name="Workbook",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=1,
        user=user,
    )


def _add_listing(
    db: Session,
    *,
    product_id: str,
    product_name: str,
    listing_id: str,
    channel_id: str,
    external_id: str,
) -> None:
    product = CanonicalProduct(
        id=product_id,
        name=product_name,
        sku=product_id,
        product_type="simple",
        status="active",
    )
    listing = Listing(
        id=listing_id,
        canonical_product_id=product_id,
        channel_id=channel_id,
        external_primary_id=external_id,
        external_id_type="provider_id",
        label=product_name,
        mapping_state="resolved",
        mapping_version=1,
    )
    db.add_all(
        [
            product,
            listing,
            ChannelCache(
                id=f"cache-{listing_id}",
                listing_id=listing_id,
                channel_id=channel_id,
                price_raw="1",
                price_currency="IRR",
                price_unit="RIAL",
                stock_quantity=1,
                status="active",
                cache_version=1,
                checksum=checksum({"listing": listing_id}),
                connector_version="1",
                freshness="fresh",
                fetch_status="success",
                fetched_at=datetime.utcnow(),
            ),
        ]
    )


def test_per_worksheet_rules_use_different_layouts_ignore_sheet_and_read_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _add_listing(
        db,
        product_id="product-wc",
        product_name="Cable WC",
        listing_id="listing-wc",
        channel_id="woocommerce:primary",
        external_id="51550",
    )
    _add_listing(
        db,
        product_id="product-snap",
        product_name="Cable Snap",
        listing_id="listing-snap",
        channel_id="snappshop:main",
        external_id="1826345203",
    )
    db.commit()
    saved = service.save_mapping(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=1,
        source_fields=[],
        channel_mappings=[],
        value_policy={},
        worksheet_rule_mode="per_worksheet",
        duplicate_product_policy="block",
        worksheet_rules=[
            {
                "worksheet_name": "فروش مستقیم",
                "enabled": True,
                "data_start_row": 2,
                "source_fields": [
                    {"field": "name", "reference_type": "header_name", "reference_value": "نام"}
                ],
                "channel_mappings": [
                    {
                        "channel_id": "woocommerce:primary",
                        "fields": [
                            {"field": "external_id", "reference_type": "header_name", "reference_value": "شناسه وو"},
                            {"field": "price", "reference_type": "header_name", "reference_value": "قیمت وو"},
                        ],
                    }
                ],
            },
            {
                "worksheet_name": "بازار",
                "enabled": True,
                "data_start_row": 3,
                "source_fields": [
                    {"field": "name", "reference_type": "column_letter", "reference_value": "B"}
                ],
                "channel_mappings": [
                    {
                        "channel_id": "snappshop:main",
                        "fields": [
                            {"field": "external_id", "reference_type": "column_letter", "reference_value": "D"},
                            {"field": "price", "reference_type": "column_letter", "reference_value": "A"},
                            {"field": "stock", "reference_type": "disabled", "reference_value": None},
                            {"field": "status", "reference_type": "disabled", "reference_value": None},
                        ],
                    }
                ],
                "value_policy": {"blank": "no_change"},
            },
            {
                "worksheet_name": "یادداشت‌ها",
                "enabled": False,
                "data_start_row": 1,
                "source_fields": [],
                "channel_mappings": [],
            },
        ],
        user=user,
    )
    assert saved["worksheetRuleMode"] == "per_worksheet"
    assert {item["worksheetName"] for item in saved["worksheetRules"]} == {
        "فروش مستقیم",
        "بازار",
        "یادداشت‌ها",
    }

    read_count = 0
    worksheets = {
        "فروش مستقیم": [["نام", "شناسه وو", "قیمت وو"], ["Cable WC", "51550", "12500000"]],
        "بازار": [["گزارش"], ["قیمت", "نام", "unused", "SNP"], ["12900000", "Cable Snap", None, "1826345203"]],
        "یادداشت‌ها": [["Cable ignored", "999", "999"]],
    }

    async def fake_read(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal read_count
        read_count += 1
        return SimpleNamespace(
            snapshot=SimpleNamespace(id="snapshot", version_seq=1, integrity_hash="f" * 64),
            worksheets=worksheets,
        )

    monkeypatch.setattr(service, "_read_external_source", fake_read)
    result = asyncio.run(service.snapshot_candidates(str(source["id"]), user))
    assert read_count == 1
    assert {item["channelId"]: item["targets"] for item in result["candidates"]} == {
        "woocommerce:primary": {"price": "12500000"},
        "snappshop:main": {"price": "12900000"},
    }
    assert all("یادداشت‌ها" not in item["sourceRowKey"] for item in result["candidates"])


def test_shared_rules_apply_to_all_worksheets_and_discovery_reads_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    service.save_mapping(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        source_fields=[{"field": "name", "reference_type": "column_letter", "reference_value": "A"}],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "B"},
                    {"field": "price", "reference_type": "column_letter", "reference_value": "C"},
                ],
            }
        ],
        value_policy={},
        user=user,
    )
    acquired = {
        "تهران": [["Name", "ID", "Price"], ["Mouse", "1", "100"]],
        "شیراز": [["Name", "ID", "Price"], ["Keyboard", "2", "200"]],
    }
    read_count = 0

    async def fake_read(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal read_count
        read_count += 1
        return SimpleNamespace(
            snapshot=SimpleNamespace(id="snapshot-discovery", version_seq=3),
            worksheets=acquired,
        )

    monkeypatch.setattr(service, "_read_external_source", fake_read)
    discovery = asyncio.run(service.list_source_worksheets(str(source["id"]), user))
    assert read_count == 1
    assert discovery["items"] == [
        {"name": "تهران", "rowCount": 2},
        {"name": "شیراز", "rowCount": 2},
    ]
    mapping = service.sources.latest_mapping(str(source["id"]))
    assert mapping is not None
    records = service._mapped_external_records(acquired, mapping)
    assert {(item["worksheetName"], item["sourceProduct"]["name"]) for item in records if item["recognized"]} == {
        ("تهران", "Mouse"),
        ("شیراز", "Keyboard"),
    }


def test_shared_rule_api_selects_two_worksheets_ignores_third_and_reads_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _add_listing(
        db,
        product_id="product-tehran",
        product_name="Tehran mouse",
        listing_id="listing-tehran",
        channel_id="woocommerce:primary",
        external_id="wc-tehran",
    )
    _add_listing(
        db,
        product_id="product-shiraz",
        product_name="Shiraz keyboard",
        listing_id="listing-shiraz",
        channel_id="woocommerce:primary",
        external_id="wc-shiraz",
    )
    db.commit()

    body = MappingSaveRequest.model_validate(
        {
            "expected_source_version": source["version"],
            "worksheet_mode": "selected",
            "worksheet_name": None,
            "selected_worksheet_names": ["تهران", "شیراز"],
            "data_start_row": 2,
            "source_fields": [
                {
                    "field": "name",
                    "reference_type": "column_letter",
                    "reference_value": "A",
                }
            ],
            "channel_mappings": [
                {
                    "channel_id": "woocommerce:primary",
                    "fields": [
                        {
                            "field": "external_id",
                            "reference_type": "column_letter",
                            "reference_value": "B",
                        },
                        {
                            "field": "price",
                            "reference_type": "column_letter",
                            "reference_value": "C",
                        },
                    ],
                }
            ],
            "value_policy": {},
            "worksheet_rule_mode": "shared",
        }
    )
    saved = save_source_mapping(str(source["id"]), body, user, service)

    assert set(saved["selectedWorksheetNames"]) == {"تهران", "شیراز"}
    assert {rule["worksheetName"] for rule in saved["worksheetRules"]} == {
        "تهران",
        "شیراز",
    }
    assert len({str(rule["sourceFields"]) for rule in saved["worksheetRules"]}) == 1
    assert len({str(rule["channels"]) for rule in saved["worksheetRules"]}) == 1

    workbook = {
        "تهران": [["Name", "ID", "Price"], ["Tehran mouse", "wc-tehran", "100"]],
        "شیراز": [["Name", "ID", "Price"], ["Shiraz keyboard", "wc-shiraz", "200"]],
        "یادداشت‌ها": [["Name", "ID", "Price"], ["Ignored", "wc-ignored", "999"]],
    }
    read_count = 0

    async def fake_read(*_args: object, **_kwargs: object) -> SimpleNamespace:
        nonlocal read_count
        read_count += 1
        return SimpleNamespace(
            snapshot=SimpleNamespace(
                id="snapshot-shared-selection",
                version_seq=1,
                integrity_hash="e" * 64,
            ),
            worksheets=workbook,
        )

    monkeypatch.setattr(service, "_read_external_source", fake_read)
    result = asyncio.run(service.snapshot_candidates(str(source["id"]), user))

    assert read_count == 1
    assert {item["sourceProduct"]["name"] for item in result["candidates"]} == {
        "Tehran mouse",
        "Shiraz keyboard",
    }
    assert all("یادداشت‌ها" not in item["sourceRowKey"] for item in result["candidates"])


def test_source_preview_business_summary_uses_distinct_product_and_attention_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    service.save_mapping(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        source_fields=[
            {"field": "name", "reference_type": "column_letter", "reference_value": "A"}
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {
                        "field": "external_id",
                        "reference_type": "column_letter",
                        "reference_value": "B",
                    },
                    {
                        "field": "price",
                        "reference_type": "column_letter",
                        "reference_value": "C",
                    },
                ],
            }
        ],
        value_policy={},
        user=user,
    )
    workbook = {
        "Pricing": [
            ["Name", "ID", "Price"],
            ["Cable", "wc-1", "100"],
            ["Cable", "wc-2", "200"],
            [None, "wc-3", "300"],
            ["Decorative row", None, None],
        ]
    }

    async def fake_read(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            snapshot=SimpleNamespace(id="preview-snapshot", version_seq=1),
            worksheets=workbook,
        )

    monkeypatch.setattr(service, "_read_external_source", fake_read)
    preview = asyncio.run(
        service.source_preview(str(source["id"]), user, page=1, page_size=100)
    )

    assert preview["recognized"] == 2
    assert preview["businessSummary"] == {
        "productsFound": 1,
        "productsReady": 1,
        "priceChanges": None,
        "stockChanges": None,
        "unchanged": None,
        "needsAttention": 1,
        "channelsReady": 1,
        "channelsNotConfigured": 1,
    }


def test_source_preview_marks_a_recognized_row_with_an_issue_as_attention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    service.save_mapping(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        source_fields=[
            {"field": "name", "reference_type": "column_letter", "reference_value": "A"}
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
                "worksheet_name": "Missing marketplace sheet",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "B"},
                    {"field": "price", "reference_type": "column_letter", "reference_value": "C"},
                ],
            },
        ],
        value_policy={},
        user=user,
    )

    async def fake_read(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            snapshot=SimpleNamespace(id="preview-snapshot", version_seq=1),
            worksheets={"Pricing": [["Name", "ID", "Price"], ["Cable", "wc-1", "100"]]},
        )

    monkeypatch.setattr(service, "_read_external_source", fake_read)
    preview = asyncio.run(
        service.source_preview(str(source["id"]), user, page=1, page_size=100)
    )
    response = SourcePreviewResponse.model_validate(preview)

    assert response.businessSummary.productsFound == 1
    assert response.businessSummary.productsReady == 0
    assert response.businessSummary.needsAttention == 1
    assert len(response.items) == 1
    assert response.items[0].worksheetName == "Pricing"
    assert response.items[0].recognized is True
    assert response.items[0].hasIssues is True
    assert response.items[0].ready is False


def test_cross_worksheet_duplicates_block_unless_last_sheet_wins_is_explicit() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    common = {
        "worksheet_mode": "all",
        "worksheet_name": None,
        "data_start_row": 2,
        "source_fields": [{"field": "name", "reference_type": "column_letter", "reference_value": "A"}],
        "channel_mappings": [
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {"field": "external_id", "reference_type": "column_letter", "reference_value": "B"},
                    {"field": "price", "reference_type": "column_letter", "reference_value": "C"},
                ],
            }
        ],
        "value_policy": {},
    }
    service.save_mapping(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        duplicate_product_policy="block",
        user=user,
        **common,
    )
    workbook = {
        "First": [["Name", "ID", "Price"], ["Cable", "1", "100"]],
        "Second": [["Name", "ID", "Price"], ["Cable", "2", "200"]],
    }
    mapping = service.sources.latest_mapping(str(source["id"]))
    assert mapping is not None
    blocked = service._mapped_external_records(workbook, mapping)
    assert not any(item["recognized"] for item in blocked)
    assert sum(
        issue["category"] == "duplicate_source_product"
        for item in blocked
        for issue in item["issues"]
    ) == 2

    current = service.get_source(str(source["id"]), user)
    service.save_mapping(
        source_id=str(source["id"]),
        expected_source_version=int(current["version"]),
        duplicate_product_policy="last_sheet_wins",
        user=user,
        **common,
    )
    mapping = service.sources.latest_mapping(str(source["id"]))
    assert mapping is not None
    resolved = service._mapped_external_records(workbook, mapping)
    recognized = [item for item in resolved if item["recognized"]]
    assert len(recognized) == 1
    assert recognized[0]["worksheetName"] == "Second"


def test_flowhub_018_mapping_without_rule_set_remains_shared_compatible() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    revision = SourceMappingRevision(
        id="legacy-mapping",
        source_id=str(source["id"]),
        version=1,
        checksum="a" * 64,
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        value_policy_json={},
        created_by_user_id=user.id,
    )
    source_field = SourceFieldMapping(
        id="legacy-name",
        mapping_revision_id=revision.id,
        field="name",
        reference_type="column_letter",
        reference_value="A",
        required=True,
    )
    channel = SourceChannelMapping(
        id="legacy-channel",
        mapping_revision_id=revision.id,
        channel_id="woocommerce:primary",
        worksheet_name=None,
        enabled=True,
    )
    db.add_all([revision, source_field, channel])
    db.flush()
    db.add(
        SourceChannelFieldMapping(
            id="legacy-external",
            channel_mapping_id=channel.id,
            field="external_id",
            reference_type="column_letter",
            reference_value="B",
        )
    )
    db.commit()
    shape = service._mapping_shape(revision)
    assert shape is not None
    assert shape["worksheetRuleMode"] == "shared"
    records = service._mapped_external_records(
        {"One": [["Name", "ID"], ["Legacy Product", "42"]]}, revision
    )
    assert records[0]["recognized"] is True
