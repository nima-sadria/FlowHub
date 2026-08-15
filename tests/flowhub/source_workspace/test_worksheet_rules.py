from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
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


def _local_workbook(worksheets: dict[str, list[list[object]]]) -> dict[str, object]:
    dataset = SimpleNamespace(
        id="dataset-local-test",
        observation_id="observation-local-test",
        source_snapshot_id="snapshot-local-test",
        source_snapshot_version=1,
        workbook_checksum="f" * 64,
        formula_evaluation_version="provider-evaluated-v1",
    )
    return {
        "kind": "source_observation",
        "sourceRevisionId": dataset.observation_id,
        "sheetRevision": None,
        "dataset": dataset,
        "worksheets": worksheets,
        "evidence": {
            "kind": "source_observation",
            "sourceRevisionId": dataset.observation_id,
            "datasetId": dataset.id,
            "snapshotId": dataset.source_snapshot_id,
            "snapshotVersion": dataset.source_snapshot_version,
            "label": "Snapshot local test",
            "validatedAt": None,
        },
    }


_TEST_IDENTITY_AUTHORITY = {
    "type": "internal",
    "system_identifier": "worksheet-test-fixture",
    "display_label": "Worksheet test fixture",
}


def _required_source_key(
    fields: list[dict[str, Any]],
    channel_mappings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if any(
        field.get("field") == "source_key"
        and field.get("reference_type") != "disabled"
        for field in fields
    ):
        return [dict(field) for field in fields]
    channel_identifier = next(
        (
            field
            for channel in channel_mappings or []
            if channel.get("enabled", True)
            for field in channel.get("fields") or []
            if field.get("field") == "external_id"
            and field.get("reference_type") != "disabled"
        ),
        None,
    )
    name = next(
        (
            field
            for field in fields
            if field.get("field") == "name"
            and field.get("reference_type") != "disabled"
        ),
        None,
    )
    authority_field = channel_identifier or name
    if authority_field is None:
        return [dict(field) for field in fields]
    return [
        *[dict(field) for field in fields],
        {
            "field": "source_key",
            "reference_type": authority_field["reference_type"],
            "reference_value": authority_field.get("reference_value"),
            "required": True,
        },
    ]


def _save_v2_mapping(
    service: SourceWorkspaceService, **payload: Any
) -> dict[str, Any]:
    payload["source_fields"] = _required_source_key(
        payload["source_fields"], payload.get("channel_mappings") or []
    )
    payload["worksheet_rules"] = [
        {
            **rule,
            "source_fields": (
                _required_source_key(
                    rule.get("source_fields") or [],
                    rule.get("channel_mappings") or [],
                )
                if rule.get("enabled", True)
                else list(rule.get("source_fields") or [])
            ),
        }
        for rule in payload.get("worksheet_rules") or []
    ]
    payload["identity_policy_version"] = 2
    payload["identity_authority"] = _TEST_IDENTITY_AUTHORITY
    return service.save_mapping(**payload)


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
                fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        ]
    )


def test_per_worksheet_rules_replay_local_evidence_with_different_layouts(
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
    saved = _save_v2_mapping(
        service,
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
                            {"field": "stock", "reference_type": "column_letter", "reference_value": "E"},
                            {"field": "status", "reference_type": "column_letter", "reference_value": "F"},
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

    worksheets = {
        "فروش مستقیم": [["نام", "شناسه وو", "قیمت وو"], ["Cable WC", "51550", "12500000"]],
        "بازار": [["گزارش"], ["قیمت", "نام", "unused", "SNP", "Stock", "Status"], ["12900000", "Cable Snap", None, "1826345203", "4", "instock"]],
        "یادداشت‌ها": [["Cable ignored", "999", "999"]],
    }

    monkeypatch.setattr(
        service,
        "_latest_local_validation_data",
        lambda _source: _local_workbook(worksheets),
    )
    result = asyncio.run(service.snapshot_candidates(str(source["id"]), user))
    assert {item["channelId"]: item["targets"] for item in result["candidates"]} == {
        "woocommerce:primary": {"price": "12500000"},
        "snappshop:main": {"price": "12900000", "stock": "4", "status": "instock"},
    }
    assert all("یادداشت‌ها" not in item["sourceRowKey"] for item in result["candidates"])


def test_shared_rules_apply_to_all_worksheets_and_local_discovery_never_acquires() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _save_v2_mapping(
        service,
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
    discovery = asyncio.run(service.list_source_worksheets(str(source["id"]), user))
    assert discovery["items"] == []
    assert discovery["worksheetDiscovery"]["metadataSource"] == "unavailable"
    mapping = service.sources.latest_mapping(str(source["id"]))
    assert mapping is not None
    records = service._mapped_external_records(acquired, mapping)
    assert {(item["worksheetName"], item["sourceProduct"]["name"]) for item in records if item["recognized"]} == {
        ("تهران", "Mouse"),
        ("شیراز", "Keyboard"),
    }


def test_shared_rule_api_replays_selected_worksheets_from_local_evidence(
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
                },
                {
                    "field": "source_key",
                    "reference_type": "column_letter",
                    "reference_value": "B",
                    "required": True,
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
            "identity_policy_version": 2,
            "identity_authority": _TEST_IDENTITY_AUTHORITY,
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
    monkeypatch.setattr(
        service,
        "_latest_local_validation_data",
        lambda _source: _local_workbook(workbook),
    )
    result = asyncio.run(service.snapshot_candidates(str(source["id"]), user))

    assert {item["sourceProduct"]["name"] for item in result["candidates"]} == {
        "Tehran mouse",
        "Shiraz keyboard",
    }
    assert all("یادداشت‌ها" not in item["sourceRowKey"] for item in result["candidates"])


def test_source_preview_business_summary_uses_source_keys_not_duplicate_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _save_v2_mapping(
        service,
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

    monkeypatch.setattr(
        service,
        "_latest_local_validation_data",
        lambda _source: _local_workbook(workbook),
    )
    preview = asyncio.run(
        service.source_preview(str(source["id"]), user, page=1, page_size=100)
    )

    assert preview["recognized"] == 2
    assert preview["businessSummary"] == {
        "productsFound": 2,
        "productsReady": 2,
        "priceChanges": None,
        "stockChanges": None,
        "unchanged": None,
        "needsAttention": 2,
        "channelsReady": 1,
        "channelsNotConfigured": 3,
    }


def test_source_preview_marks_a_recognized_row_with_an_issue_as_attention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _save_v2_mapping(
        service,
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
                    {"field": "stock", "reference_type": "column_letter", "reference_value": "D"},
                    {"field": "status", "reference_type": "column_letter", "reference_value": "E"},
                ],
            },
        ],
        value_policy={},
        user=user,
    )

    monkeypatch.setattr(
        service,
        "_latest_local_validation_data",
        lambda _source: _local_workbook(
            {"Pricing": [["Name", "ID", "Price"], ["Cable", "wc-1", "100"]]}
        ),
    )
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


def test_unsaved_mapping_preview_resolves_rows_without_persisting_or_invalidating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    source_version = int(source["version"])

    local_rows = {
        "Pricing": [
            ["Name", "Woo ID", "Woo Price", "Snapp ID", "Snapp Price", "Snapp Stock", "Snapp Status"],
            ["Cable", "wc-1", "100", "snap-1", "125", "9", "instock"],
        ]
    }
    monkeypatch.setattr(
        service,
        "_latest_local_validation_data",
        lambda _source: _local_workbook(local_rows),
    )
    preview = asyncio.run(
        service.preview_unsaved_mapping(
            source_id=str(source["id"]),
            expected_source_version=source_version,
            worksheet_mode="all",
            worksheet_name=None,
            data_start_row=2,
            source_fields=[
                {
                    "field": "name",
                    "reference_type": "column_letter",
                    "reference_value": "A",
                },
                {
                    "field": "source_key",
                    "reference_type": "column_letter",
                    "reference_value": "B",
                    "required": True,
                }
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
                },
                {
                    "channel_id": "snappshop:main",
                    "fields": [
                        {
                            "field": "external_id",
                            "reference_type": "column_letter",
                            "reference_value": "D",
                        },
                        {
                            "field": "price",
                            "reference_type": "column_letter",
                            "reference_value": "E",
                        },
                        {
                            "field": "stock",
                            "reference_type": "column_letter",
                            "reference_value": "F",
                        },
                        {
                            "field": "status",
                            "reference_type": "column_letter",
                            "reference_value": "G",
                        },
                    ],
                },
            ],
            value_policy={},
            identity_policy_version=2,
            identity_authority=_TEST_IDENTITY_AUTHORITY,
            user=user,
        )
    )

    assert preview["mappingRevisionId"] is None
    assert preview["items"][0]["channels"] == [
        {
            "channelId": "snappshop:main",
            "fields": {"external_id": "snap-1", "price": "125", "stock": "9", "status": "instock"},
        },
        {
            "channelId": "woocommerce:primary",
            "fields": {"external_id": "wc-1", "price": "100"},
        },
    ]
    assert db.query(SourceMappingRevision).count() == 0
    db.expire_all()
    persisted_source = service.sources.get(str(source["id"]))
    assert persisted_source is not None
    assert persisted_source.version == source_version


def test_cross_worksheet_duplicate_names_are_allowed_with_unique_v2_keys() -> None:
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
    _save_v2_mapping(
        service,
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
    blocked_policy_records = service._mapped_external_records(workbook, mapping)
    assert sum(item["recognized"] for item in blocked_policy_records) == 2
    assert not [
        issue
        for item in blocked_policy_records
        for issue in item["issues"]
        if issue["category"] == "duplicate_source_product_key"
    ]

    current = service.get_source(str(source["id"]), user)
    _save_v2_mapping(
        service,
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
    assert len(recognized) == 2
    assert {item["worksheetName"] for item in recognized} == {"First", "Second"}


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


def test_backend_rejects_single_participant_with_per_worksheet_strategy() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    with pytest.raises(HTTPException) as error:
        _save_v2_mapping(
            service,
            source_id=str(source["id"]), expected_source_version=int(source["version"]),
            worksheet_mode="selected", worksheet_name="Retail", selected_worksheet_names=["Retail"],
            data_start_row=2, source_fields=[], channel_mappings=[], value_policy={},
            worksheet_rule_mode="per_worksheet", worksheet_rules=[], user=user,
        )
    assert error.value.detail["code"] == "WORKSHEET_STRATEGY_INVALID"


def test_backend_rejects_scope_rule_mismatch() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    rules = [{
        "worksheet_name": name, "enabled": True, "data_start_row": 2,
        "source_fields": [{"field": "name", "reference_type": "column_letter", "reference_value": "A"}],
        "channel_mappings": [{"channel_id": "woocommerce:primary", "fields": [{"field": "external_id", "reference_type": "column_letter", "reference_value": "B"}]}],
    } for name in ("Retail", "Stale")]
    with pytest.raises(HTTPException) as error:
        _save_v2_mapping(
            service,
            source_id=str(source["id"]), expected_source_version=int(source["version"]),
            worksheet_mode="selected", worksheet_name=None, selected_worksheet_names=["Retail", "Marketplace"],
            data_start_row=2, source_fields=[], channel_mappings=[], value_policy={},
            worksheet_rule_mode="per_worksheet", worksheet_rules=rules, user=user,
        )
    assert error.value.detail["code"] == "WORKSHEET_SCOPE_RULE_MISMATCH"


def test_source_product_key_is_authoritative_and_names_may_repeat() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _save_v2_mapping(
        service,
        source_id=str(source["id"]), expected_source_version=int(source["version"]),
        worksheet_mode="all", worksheet_name=None, data_start_row=2,
        source_fields=[
            {"field": "name", "reference_type": "column_letter", "reference_value": "A", "required": True},
            {"field": "source_key", "reference_type": "column_letter", "reference_value": "B", "required": True},
        ],
        channel_mappings=[{"channel_id": "woocommerce:primary", "fields": [{"field": "external_id", "reference_type": "column_letter", "reference_value": "C"}]}],
        value_policy={}, user=user,
    )
    mapping = service.sources.latest_mapping(str(source["id"]))
    assert mapping is not None
    unique = service._mapped_external_records({
        "Retail": [["Name", "Key", "ID"], ["Mouse", "key-1", "wc-1"]],
        "Marketplace": [["Name", "Key", "ID"], ["Mouse", "key-2", "wc-2"]],
    }, mapping)
    assert not [issue for row in unique for issue in row["issues"] if issue["category"] == "duplicate_source_product_key"]
    duplicate = service._mapped_external_records({
        "Retail": [["Name", "Key", "ID"], ["Mouse", "same-key", "wc-1"]],
        "Marketplace": [["Name", "Key", "ID"], ["Keyboard", "same-key", "wc-2"]],
    }, mapping)
    conflicts = [issue for row in duplicate for issue in row["issues"] if issue["category"] == "duplicate_source_product_key"]
    assert len(conflicts) == 2
    assert conflicts[0]["details"]["conflictingRows"] == ["Retail!2", "Marketplace!2"]
    blank = service._mapped_external_records({"Retail": [["Name", "Key", "ID"], ["Mouse", "", "wc-1"]]}, mapping)
    assert blank[0]["issues"][0]["category"] == "missing_source_product_key"


def test_cost_only_row_participates_in_identity_validation_but_blank_row_is_ignored() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    _save_v2_mapping(
        service,
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        source_fields=[
            {
                "field": "name",
                "reference_type": "column_letter",
                "reference_value": "A",
                "required": True,
            },
            {
                "field": "source_key",
                "reference_type": "column_letter",
                "reference_value": "B",
                "required": True,
            },
            {
                "field": "cost",
                "reference_type": "column_letter",
                "reference_value": "D",
                "required": False,
            },
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {
                        "field": "external_id",
                        "reference_type": "column_letter",
                        "reference_value": "C",
                    }
                ],
            }
        ],
        value_policy={},
        user=user,
    )
    mapping = service.sources.latest_mapping(str(source["id"]))
    assert mapping is not None

    records = service._mapped_external_records(
        {
            "Retail": [
                ["Name", "Key", "ID", "Cost"],
                ["", "", "", "125000"],
                ["", "", "", ""],
            ]
        },
        mapping,
    )

    assert len(records) == 2
    assert records[0]["recognized"] is False
    assert {issue["category"] for issue in records[0]["issues"]} == {
        "missing_source_identity",
        "missing_source_product_key",
    }
    assert records[1]["recognized"] is False
    assert records[1]["issues"] == []
    identity = service._identity_preview_summary(
        records,
        mapping=mapping,
        validation_source={"kind": "source_observation"},
    )
    assert identity["status"] == "blocked"
    assert identity["participatingRowCount"] == 1
    assert identity["missingKeyCount"] == 1
    assert identity["missingRows"] == [
        {"worksheetName": "Retail", "rowNumber": 2}
    ]


def test_woocommerce_product_id_can_be_both_source_key_and_listing_identifier() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    payload = {
        "source_id": str(source["id"]),
        "expected_source_version": int(source["version"]),
        "worksheet_mode": "all",
        "worksheet_name": None,
        "data_start_row": 2,
        # The owner treats the website/WooCommerce ID as FlowHub's stable
        # identity. Product names deliberately repeat and remain valid.
        "source_fields": [
            {"field": "name", "reference_type": "column_letter", "reference_value": "B", "required": True},
            {"field": "source_key", "reference_type": "column_letter", "reference_value": "A", "required": True},
        ],
        "channel_mappings": [{
            "channel_id": "woocommerce:primary",
            "fields": [{"field": "external_id", "reference_type": "column_letter", "reference_value": "A"}],
        }],
        "value_policy": {},
        "identity_policy_version": 2,
        "identity_authority": {
            "type": "external_system",
            "system_identifier": "woocommerce",
            "display_label": "WooCommerce / Website",
        },
        "user": user,
    }

    preview = asyncio.run(service.preview_unsaved_mapping(**payload))
    assert preview["identityValidation"]["status"] == "pending"
    assert preview["identityValidation"]["evidence"]["kind"] == "none"

    saved = service.save_mapping(**payload)
    source_key = next(field for field in saved["sourceFields"] if field["field"] == "source_key")
    woo_id = next(field for field in saved["channels"][0]["fields"] if field["field"] == "external_id")
    assert source_key["referenceValue"] == woo_id["referenceValue"] == "A"
    assert saved["identityAuthority"]["systemIdentifier"] == "woocommerce"
    assert saved["mappingReadiness"] == "identity_validation_pending"


def test_v2_mapping_save_does_not_require_or_trigger_remote_preview() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    payload = {
        "source_id": str(source["id"]),
        "expected_source_version": int(source["version"]),
        "worksheet_mode": "all",
        "worksheet_name": None,
        "data_start_row": 2,
        "source_fields": [
            {"field": "name", "reference_type": "column_letter", "reference_value": "A", "required": True},
            {"field": "source_key", "reference_type": "column_letter", "reference_value": "B", "required": True},
        ],
        "channel_mappings": [{
            "channel_id": "woocommerce:primary",
            "fields": [{"field": "external_id", "reference_type": "column_letter", "reference_value": "C"}],
        }],
        "value_policy": {},
        "identity_policy_version": 2,
        "identity_authority": {
            "type": "external_system",
            "system_identifier": "erp",
            "display_label": "ERP",
        },
        "user": user,
    }

    saved = service.save_mapping(**payload)
    source_key = next(field for field in saved["sourceFields"] if field["field"] == "source_key")
    assert source_key["required"] is True
    assert saved["identityValidation"]["status"] == "pending"


def test_v2_local_preview_without_dataset_is_pending_not_blocked_or_remote() -> None:
    db = _session()
    user = _user_and_channels(db)
    service = SourceWorkspaceService(db)
    source = _external_source(service, user)
    payload = {
        "source_id": str(source["id"]),
        "expected_source_version": int(source["version"]),
        "worksheet_mode": "all",
        "worksheet_name": None,
        "data_start_row": 2,
        "source_fields": [
            {"field": "name", "reference_type": "column_letter", "reference_value": "A", "required": True},
            {"field": "source_key", "reference_type": "column_letter", "reference_value": "B", "required": True},
        ],
        "channel_mappings": [{
            "channel_id": "woocommerce:primary",
            "fields": [{"field": "external_id", "reference_type": "column_letter", "reference_value": "C"}],
        }],
        "value_policy": {},
        "identity_policy_version": 2,
        "identity_authority": {
            "type": "external_system",
            "system_identifier": "snappshop",
            "display_label": "SnappShop",
        },
        "user": user,
    }

    preview = asyncio.run(service.preview_unsaved_mapping(**payload))
    assert preview["identityValidation"]["status"] == "pending"
    assert preview["identityValidation"]["validKeyCount"] is None
    saved = service.save_mapping(**payload)
    assert saved["identityValidation"]["status"] == "pending"
