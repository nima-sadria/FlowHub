from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.flowhub.api.v2.source_workspace import MappingSaveRequest
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.data_layer.models import (
    DlSourceReadReservation,
    DlSourceSnapshot,
)
from app.flowhub.database import FlowHubBase
from app.flowhub.pricing_matrix.service import PricingMatrixService
from app.flowhub.setup.service import AppConfigService
from app.flowhub.source_acquisition.models import (
    AcquisitionRun,
    SourceObservation,
    SourceObservationDataset,
    SourceObservationWorksheetDataset,
)
from app.flowhub.source_workspace.models import (
    SourceChannelMapping,
    SourceMappingIdentityAssessment,
    SourceProductIdentity,
    SourceProfile,
)
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService
from app.flowhub.unified_workspace.domain import utcnow
from app.flowhub.unified_workspace.models import (
    CanonicalProduct,
    ChannelCache,
    Listing,
    WorkspaceSnapshot,
)
from app.flowhub.unified_workspace.services import UnifiedWorkspaceService


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def owner(db: Session) -> FlowHubUser:
    user = FlowHubUser(
        id=1,
        username="identity-owner",
        hashed_password="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _external_source(
    service: SourceWorkspaceService, owner: FlowHubUser
) -> dict[str, Any]:
    return service.create_source(
        name="Identity workbook",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        user=owner,
    )


def _authority(
    system_identifier: str, display_label: str
) -> dict[str, str]:
    return {
        "type": "external_system",
        "system_identifier": system_identifier,
        "display_label": display_label,
    }


def _nextcloud_settings(
    *,
    url: str = "https://cloud.example.test",
    username: str = "identity-owner",
    spreadsheet_path: str = "/identity.xlsx",
    password: str = "initial-app-password",
) -> dict[str, Any]:
    return {
        "enabled": True,
        "settings": {
            "url": url,
            "username": username,
            "spreadsheet_path": spreadsheet_path,
        },
        "secrets": {"password": password},
    }


def _external_mapping_payload(
    source: dict[str, Any],
    owner: FlowHubUser,
    *,
    authority: dict[str, str] | None = None,
    source_key_column: str = "B",
    woo_identifier_column: str = "C",
    include_disabled_snappshop: bool = False,
) -> dict[str, Any]:
    channels: list[dict[str, Any]] = [
        {
            "channel_id": "woocommerce:primary",
            "enabled": True,
            "fields": [
                {
                    "field": "external_id",
                    "reference_type": "column_letter",
                    "reference_value": woo_identifier_column,
                }
            ],
        }
    ]
    if include_disabled_snappshop:
        channels.append(
            {
                "channel_id": "snappshop:main",
                "enabled": False,
                # SnappShop normally requires identifier, stock, and status.
                # A disabled Channel intentionally remains incomplete.
                "fields": [],
            }
        )
    return {
        "source_id": str(source["id"]),
        "expected_source_version": int(source["version"]),
        "worksheet_mode": "all",
        "worksheet_name": None,
        "data_start_row": 2,
        "source_fields": [
            {
                "field": "name",
                "reference_type": "column_letter",
                "reference_value": "A",
                "required": True,
            },
            {
                "field": "source_key",
                "reference_type": "column_letter",
                "reference_value": source_key_column,
                "required": True,
            },
        ],
        "channel_mappings": channels,
        "value_policy": {},
        "identity_policy_version": 2,
        "identity_authority": authority or _authority("erp", "ERP"),
        "user": owner,
    }


def _forbid_provider_io(
    monkeypatch: pytest.MonkeyPatch, _service: SourceWorkspaceService
) -> dict[str, int]:
    calls = {"workspace_read": 0, "provider_read": 0, "reservation": 0}

    async def unexpected_provider_read(*_args: object, **_kwargs: object) -> None:
        calls["provider_read"] += 1
        raise AssertionError("configuration persistence must not call the provider")

    def unexpected_reservation(*_args: object, **_kwargs: object) -> None:
        calls["reservation"] += 1
        raise AssertionError("configuration persistence must not reserve read quota")

    monkeypatch.setattr(
        SpreadsheetSourceReadService,
        "read_nextcloud_spreadsheet",
        unexpected_provider_read,
    )
    monkeypatch.setattr(
        SpreadsheetSourceReadService,
        "reserve_read_slot",
        unexpected_reservation,
    )
    return calls


def _persist_external_observation_dataset(
    db: Session,
    *,
    source_id: str,
    worksheets: dict[str, list[list[str]]],
    resource_scope: str = "webdav:/identity.xlsx",
) -> SourceObservationDataset:
    now = utcnow()
    run_id = str(uuid.uuid4())
    observation_id = str(uuid.uuid4())
    run = AcquisitionRun(
        id=run_id,
        source_id=source_id,
        resource_scope=resource_scope,
        trigger_kind="manual",
        actor_user_id=None,
        request_fingerprint="r" * 64,
        correlation_id=run_id,
        root_run_id=run_id,
        attempt_number=1,
        status="succeeded",
        result="observed",
        queued_at=now,
        started_at=now,
        terminal_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(run)
    db.commit()
    observation = SourceObservation(
        id=observation_id,
        acquisition_run_id=run.id,
        source_id=source_id,
        resource_scope=resource_scope,
        resource_identity="/identity.xlsx",
        resource_identity_hash="i" * 64,
        observation_version=1,
        observed_at=now,
        provenance_json={"provider": "test-local-evidence"},
        checksum="o" * 64,
        created_at=now,
    )
    snapshot = DlSourceSnapshot(
        connector_id="nextcloud:primary",
        file_path="/identity.xlsx",
        etag="identity-v1",
        parsed_row_count=sum(len(rows) for rows in worksheets.values()),
        duplicate_count=0,
        invalid_row_count=0,
        integrity_hash="w" * 64,
        sheet_names=list(worksheets),
        version_seq=1,
        snapshotted_at=now,
    )
    db.add_all([observation, snapshot])
    db.commit()
    binding_fingerprint = (
        SpreadsheetSourceReadService(db).configured_binding_fingerprint()
    )
    assert binding_fingerprint is not None
    dataset = SourceObservationDataset(
        id=str(uuid.uuid4()),
        observation_id=observation.id,
        source_id=source_id,
        resource_scope=resource_scope,
        binding_fingerprint=binding_fingerprint,
        parser_version="test-parser-v1",
        formula_evaluation_version="provider-evaluated-v1",
        source_snapshot_id=snapshot.id,
        source_snapshot_version=1,
        workbook_checksum="w" * 64,
        row_count=sum(len(rows) for rows in worksheets.values()),
        worksheet_count=len(worksheets),
        created_at=now,
    )
    db.add(dataset)
    db.flush()
    for order, (worksheet_name, rows) in enumerate(worksheets.items(), start=1):
        db.add(
            SourceObservationWorksheetDataset(
                id=str(uuid.uuid4()),
                dataset_id=dataset.id,
                worksheet_name=worksheet_name,
                worksheet_order=order,
                rows_json=rows,
                row_count=len(rows),
                checksum=(str(order) * 64)[:64],
                created_at=now,
            )
        )
    db.commit()
    return dataset


def _flowhub_sheet(
    service: SourceWorkspaceService,
    owner: FlowHubUser,
    rows: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    sheet = service.create_sheet(
        name="Local identity evidence",
        columns=[
            {"column_key": "product-name", "name": "Product Name", "position": 1},
            {"column_key": "source-key", "name": "Source Key", "position": 2},
            {"column_key": "woo-id", "name": "Woo ID", "position": 3},
        ],
        user=owner,
    )
    sheet = service.append_sheet_rows(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        count=len(rows),
        user=owner,
    )
    changes: list[dict[str, Any]] = []
    for sheet_row, values in zip(sheet["rows"], rows, strict=True):
        for column_key, value in values.items():
            changes.append(
                {
                    "row_key": sheet_row["rowKey"],
                    "column_key": column_key,
                    "value": value,
                }
            )
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=changes,
        user=owner,
    )
    return sheet, service.get_source(sheet["sourceId"], owner)


def _save_sheet_mapping(
    service: SourceWorkspaceService,
    owner: FlowHubUser,
    source: dict[str, Any],
    *,
    authority: dict[str, str] | None = None,
) -> dict[str, Any]:
    return service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=[
            {
                "field": "name",
                "reference_type": "column_id",
                "reference_value": "product-name",
                "required": True,
            },
            {
                "field": "source_key",
                "reference_type": "column_id",
                "reference_value": "source-key",
                "required": True,
            },
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "enabled": True,
                "fields": [
                    {
                        "field": "external_id",
                        "reference_type": "column_id",
                        "reference_value": "woo-id",
                    }
                ],
            }
        ],
        value_policy={},
        identity_policy_version=2,
        identity_authority=authority or _authority("internal-erp", "Internal ERP"),
        user=owner,
    )


def _add_cached_listing(
    db: Session,
    *,
    product_id: str,
    listing_id: str,
    external_id: str,
) -> None:
    db.add_all(
        [
            CanonicalProduct(
                id=product_id,
                name=f"Product {product_id}",
                sku=f"SKU-{product_id}",
                product_type="simple",
                status="active",
            ),
            Listing(
                id=listing_id,
                canonical_product_id=product_id,
                channel_id="woocommerce:primary",
                external_primary_id=external_id,
                external_id_type="product_id",
                label=f"Woo {external_id}",
                mapping_state="resolved",
                mapping_version=1,
            ),
            ChannelCache(
                id=f"cache-{listing_id}",
                listing_id=listing_id,
                channel_id="woocommerce:primary",
                price_raw="100",
                price_currency="IRR",
                price_unit="RIAL",
                stock_quantity=1,
                status="active",
                cache_version=1,
                checksum=f"checksum-{listing_id}",
                connector_version="test-v1",
                freshness="fresh",
                fetch_status="success",
                fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        ]
    )
    db.commit()


def test_external_v2_mapping_save_without_local_data_is_pending_and_zero_remote_io(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    calls = _forbid_provider_io(monkeypatch, service)

    saved = service.save_mapping(
        **_external_mapping_payload(source, owner, authority=_authority("erp", "ERP"))
    )

    assert saved["identityAuthority"] == {
        "type": "external_system",
        "systemIdentifier": "erp",
        "displayLabel": "ERP",
    }
    assert saved["identityValidation"]["status"] == "pending"
    assert saved["identityValidation"]["evidence"]["kind"] == "none"
    assert saved["mappingReadiness"] == "identity_validation_pending"
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_data_quality_without_local_data_reports_actionable_pending_and_zero_remote_io(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    calls = _forbid_provider_io(monkeypatch, service)
    saved = service.save_mapping(**_external_mapping_payload(source, owner))
    assert saved["identityValidation"]["status"] == "pending"

    scan = asyncio.run(
        service.scan_data_quality(user=owner, source_id=source["id"])
    )
    report = service.data_quality(
        user=owner,
        source_id=source["id"],
        channel_id=None,
        worksheet=None,
        category=None,
        severity=None,
        product=None,
        mapping_state=None,
        page=1,
        page_size=100,
    )

    assert scan["summary"]["state"] == "issues_found"
    assert report["total"] == 1
    issue = report["items"][0]
    assert issue["code"] == "SOURCE_IDENTITY_VALIDATION_PENDING"
    assert issue["category"] == "identity_validation_pending"
    assert issue["severity"] == "blocked"
    assert issue["recommendedAction"] == (
        "Use Read Source explicitly, then run the Data Quality check again."
    )
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_external_v2_mapping_validates_from_local_observation_with_zero_remote_io(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    AppConfigService(db).set(
        "nextcloud.spreadsheet_path", "/identity.xlsx", updated_by="identity-test"
    )
    AppConfigService(db).set(
        "nextcloud.url", "https://cloud.example.test", updated_by="identity-test"
    )
    AppConfigService(db).set(
        "nextcloud.username", "identity-owner", updated_by="identity-test"
    )
    dataset = _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "UGREEN": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
                ["Cable", "erp-102", "502"],
                ["", "", ""],
            ]
        },
    )
    calls = _forbid_provider_io(monkeypatch, service)

    saved = service.save_mapping(
        **_external_mapping_payload(source, owner, authority=_authority("erp", "ERP"))
    )

    validation = saved["identityValidation"]
    assert validation["status"] == "pass"
    assert validation["participatingRowCount"] == 2
    assert validation["validKeyCount"] == 2
    assert validation["missingKeyCount"] == 0
    assert validation["duplicateKeyCount"] == 0
    assert validation["evidence"]["kind"] == "source_observation"
    assert validation["evidence"]["sourceRevisionId"] == dataset.observation_id
    assert validation["evidence"]["datasetId"] == dataset.id
    assert validation["evidence"]["snapshotId"] == dataset.source_snapshot_id
    assert validation["evidence"]["snapshotVersion"] == 1
    assert saved["mappingReadiness"] == "ready"
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_reconfigured_nextcloud_binding_with_same_path_makes_old_dataset_pending(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    config = AppConfigService(db)
    config.set(
        "nextcloud.spreadsheet_path", "/identity.xlsx", updated_by="identity-test"
    )
    config.set(
        "nextcloud.url", "https://first-cloud.example.test", updated_by="identity-test"
    )
    config.set("nextcloud.username", "first-owner", updated_by="identity-test")
    dataset = _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "UGREEN": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
            ]
        },
    )
    initial = service.save_mapping(**_external_mapping_payload(source, owner))
    assert initial["identityValidation"]["status"] == "pass"
    assert initial["identityValidation"]["evidence"]["datasetId"] == dataset.id

    # The workbook path is unchanged, but the endpoint/account identity is a
    # different provider binding. Evidence captured for the former binding
    # must not validate a new Mapping revision.
    config.set(
        "nextcloud.url", "https://second-cloud.example.test", updated_by="identity-test"
    )
    config.set("nextcloud.username", "second-owner", updated_by="identity-test")
    calls = _forbid_provider_io(monkeypatch, service)
    current = service.get_source(source["id"], owner)

    saved = service.save_mapping(
        **_external_mapping_payload(current, owner, authority=_authority("erp", "ERP"))
    )

    assert saved["identityValidation"]["status"] == "pending"
    assert saved["identityValidation"]["evidence"]["kind"] == "none"
    assert saved["mappingReadiness"] == "identity_validation_pending"
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


@pytest.mark.parametrize(
    ("changed_setting", "replacement"),
    [
        ("url", "https://replacement-cloud.example.test"),
        ("username", "replacement-owner"),
        ("spreadsheet_path", "/replacement.xlsx"),
    ],
)
def test_commerce_resource_binding_change_fences_linked_source_and_local_evidence(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
    changed_setting: str,
    replacement: str,
) -> None:
    commerce = CommerceHubService(db)
    commerce.update_source_settings(
        "nextcloud:primary",
        _nextcloud_settings(),
        user=owner,
    )
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    dataset = _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "UGREEN": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
            ]
        },
    )
    saved = service.save_mapping(**_external_mapping_payload(source, owner))
    assert saved["mappingReadiness"] == "ready"
    profile = db.get(SourceProfile, source["id"])
    assert profile is not None
    previous_version = profile.version
    calls = _forbid_provider_io(monkeypatch, service)
    updated_settings = _nextcloud_settings()
    updated_settings["settings"][changed_setting] = replacement

    commerce.update_source_settings(
        "nextcloud:primary",
        updated_settings,
        user=owner,
    )

    db.expire_all()
    profile = db.get(SourceProfile, source["id"])
    assert profile is not None
    assert profile.version == previous_version + 1
    current = service.get_source(source["id"], owner)
    assert current["version"] == previous_version + 1
    assert current["mapping"]["mappingReadiness"] == "identity_validation_pending"
    assert current["mapping"]["identityValidation"]["status"] == "pending"
    assert current["mapping"]["identityValidation"]["evidence"]["kind"] == "none"
    assert db.get(SourceObservationDataset, dataset.id) is not None
    assert (
        SpreadsheetSourceReadService(db).configured_binding_fingerprint()
        != dataset.binding_fingerprint
    )
    with pytest.raises(HTTPException) as exc_info:
        service.lock_source_for_workspace(
            source_id=source["id"],
            expected_source_version=previous_version,
            user=owner,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "SOURCE_VERSION_CONFLICT"
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_commerce_password_rotation_preserves_linked_source_and_local_evidence(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commerce = CommerceHubService(db)
    commerce.update_source_settings(
        "nextcloud:primary",
        _nextcloud_settings(),
        user=owner,
    )
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    dataset = _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "UGREEN": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
            ]
        },
    )
    saved = service.save_mapping(**_external_mapping_payload(source, owner))
    assert saved["mappingReadiness"] == "ready"
    profile = db.get(SourceProfile, source["id"])
    assert profile is not None
    previous_version = profile.version
    calls = _forbid_provider_io(monkeypatch, service)

    commerce.update_source_settings(
        "nextcloud:primary",
        {"secrets": {"password": "rotated-app-password"}},
        user=owner,
    )

    db.expire_all()
    profile = db.get(SourceProfile, source["id"])
    assert profile is not None
    assert profile.version == previous_version
    current = service.get_source(source["id"], owner)
    assert current["version"] == previous_version
    assert current["mapping"]["mappingReadiness"] == "ready"
    assert current["mapping"]["identityValidation"]["status"] == "pass"
    assert current["mapping"]["identityValidation"]["evidence"]["datasetId"] == (
        dataset.id
    )
    assert (
        SpreadsheetSourceReadService(db).configured_binding_fingerprint()
        == dataset.binding_fingerprint
    )
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_mapping_for_worksheet_absent_from_old_dataset_saves_as_pending(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    config = AppConfigService(db)
    config.set(
        "nextcloud.spreadsheet_path", "/identity.xlsx", updated_by="identity-test"
    )
    config.set(
        "nextcloud.url", "https://cloud.example.test", updated_by="identity-test"
    )
    config.set("nextcloud.username", "identity-owner", updated_by="identity-test")
    _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "OLD": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
            ]
        },
    )
    calls = _forbid_provider_io(monkeypatch, service)
    payload = _external_mapping_payload(source, owner)
    payload.update(
        worksheet_mode="selected",
        worksheet_name="NEW",
        selected_worksheet_names=["NEW"],
    )

    saved = service.save_mapping(**payload)

    assert saved["worksheetMode"] == "selected"
    assert saved["selectedWorksheetNames"] == ["NEW"]
    assert saved["identityValidation"]["status"] == "pending"
    assert saved["mappingReadiness"] == "identity_validation_pending"
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert service.get_source(source["id"], owner)["mapping"]["id"] == saved["id"]


def test_snapshot_candidates_replays_exact_local_dataset_with_zero_provider_io(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)
    config = AppConfigService(db)
    config.set(
        "nextcloud.spreadsheet_path", "/identity.xlsx", updated_by="identity-test"
    )
    config.set(
        "nextcloud.url", "https://cloud.example.test", updated_by="identity-test"
    )
    config.set("nextcloud.username", "identity-owner", updated_by="identity-test")
    dataset = _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "UGREEN": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
            ]
        },
    )
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    saved = service.save_mapping(**_external_mapping_payload(source, owner))
    assert saved["identityValidation"]["evidence"]["datasetId"] == dataset.id
    calls = _forbid_provider_io(monkeypatch, service)

    analysis = asyncio.run(service.snapshot_candidates(source["id"], owner))

    assert len(analysis["candidates"]) == 1
    assert analysis["candidates"][0]["canonicalProductId"] == "canonical-1"
    assert analysis["mapping"]["identityValidation"]["evidence"]["datasetId"] == dataset.id
    assert analysis["sheetRevision"]["id"] == (
        f"external:{dataset.source_snapshot_id}:{dataset.source_snapshot_version}"
    )
    assert analysis["sheetRevision"]["version"] == dataset.source_snapshot_version
    assert analysis["sheetRevision"]["checksum"] == dataset.workbook_checksum
    assert analysis["sheetRevision"]["formulaEngineVersion"] == (
        dataset.formula_evaluation_version
    )
    assert analysis["sheetRevision"]["observationId"] == dataset.observation_id
    assert analysis["sheetRevision"]["datasetId"] == dataset.id
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_open_workspace_replays_local_dataset_and_accepts_identity_binding_atomically(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_service = SourceWorkspaceService(db)
    source = _external_source(source_service, owner)
    config = AppConfigService(db)
    config.set(
        "nextcloud.spreadsheet_path", "/identity.xlsx", updated_by="identity-test"
    )
    config.set(
        "nextcloud.url", "https://cloud.example.test", updated_by="identity-test"
    )
    config.set("nextcloud.username", "identity-owner", updated_by="identity-test")
    dataset = _persist_external_observation_dataset(
        db,
        source_id=source["id"],
        worksheets={
            "UGREEN": [
                ["Product", "ERP Code", "Woo ID"],
                ["Cable", "erp-101", "501"],
            ]
        },
    )
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    source_service.save_mapping(**_external_mapping_payload(source, owner))
    PricingMatrixService(db).declare_unit(
        scope="source",
        scope_reference=source["id"],
        currency="EUR",
        unit="EUR",
        user=owner,
    )
    calls = _forbid_provider_io(monkeypatch, source_service)

    workspace = asyncio.run(
        UnifiedWorkspaceService(db).create_source_workspace(
            name="Local evidence workspace",
            source_id=source["id"],
            user=owner,
            correlation_id=str(uuid.uuid4()),
        )
    )

    assert workspace["id"]
    snapshot = db.query(WorkspaceSnapshot).one()
    assert snapshot.source_metadata_json["sheet_revision_id"] == (
        f"external:{dataset.source_snapshot_id}:{dataset.source_snapshot_version}"
    )
    assert snapshot.source_metadata_json["identity_validation"]["evidence"][
        "datasetId"
    ] == dataset.id
    binding = db.query(SourceProductIdentity).one()
    assert binding.normalized_source_key == "erp-101"
    assert binding.canonical_product_id == "canonical-1"
    assert binding.first_source_revision_kind == "source_observation"
    assert binding.first_source_revision_id == dataset.observation_id
    assert binding.first_dataset_id == dataset.id
    assert binding.first_sheet_revision_id is None
    refreshed_mapping = source_service.get_source(source["id"], owner)["mapping"]
    assert refreshed_mapping["mappingReadiness"] == "ready"
    assert refreshed_mapping["identityValidation"]["status"] == "pass"
    assert refreshed_mapping["identityValidation"]["evidence"]["datasetId"] == (
        dataset.id
    )
    assert snapshot.source_metadata_json["source_product_identity_bindings"] == [
        {
            "id": binding.id,
            "sourceKeyHash": binding.source_key_hash,
            "normalizationVersion": binding.normalization_version,
            "canonicalProductId": "canonical-1",
            "firstSourceRevisionKind": "source_observation",
            "firstSourceRevisionId": dataset.observation_id,
            "datasetId": dataset.id,
            "sheetRevisionId": None,
        }
    ]
    assert snapshot.source_metadata_json["identity_validation"][
        "bindingContextFingerprint"
    ] == refreshed_mapping["identityValidation"]["bindingContextFingerprint"]
    assert snapshot.acquisition_metadata_json["provider_io_performed"] is False
    assert snapshot.acquisition_metadata_json["validation_source"] == "local_dataset"
    assert "acquired_at" not in snapshot.acquisition_metadata_json
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0


def test_listing_identity_change_makes_mapping_pending_then_locally_blocked(
    db: Session,
    owner: FlowHubUser,
) -> None:
    source_service = SourceWorkspaceService(db)
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    _add_cached_listing(
        db,
        product_id="canonical-2",
        listing_id="listing-502",
        external_id="502",
    )
    _, source = _flowhub_sheet(
        source_service,
        owner,
        [{"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"}],
    )
    saved = _save_sheet_mapping(source_service, owner, source)
    PricingMatrixService(db).declare_unit(
        scope="source",
        scope_reference=source["id"],
        currency="EUR",
        unit="EUR",
        user=owner,
    )
    asyncio.run(
        UnifiedWorkspaceService(db).create_source_workspace(
            name="Initial identity binding",
            source_id=source["id"],
            user=owner,
            correlation_id=str(uuid.uuid4()),
        )
    )
    binding = db.query(SourceProductIdentity).one()
    assert binding.canonical_product_id == "canonical-1"
    assert source_service.get_source(source["id"], owner)["mapping"][
        "mappingReadiness"
    ] == "ready"

    listing = db.get(Listing, "listing-501")
    assert listing is not None
    listing.canonical_product_id = "canonical-2"
    listing.mapping_version += 1
    db.commit()

    stale = source_service.get_source(source["id"], owner)["mapping"]
    assert stale["id"] == saved["id"]
    assert stale["mappingReadiness"] == "identity_validation_pending"
    assert stale["identityValidation"]["status"] == "pending"

    validation = source_service.validate_saved_mapping_identity(source["id"], owner)
    assert validation["status"] == "blocked"
    assert validation["bindingConflictCount"] == 1
    assert validation["bindingConflicts"][0]["boundCanonicalProductId"] == (
        "canonical-1"
    )
    assert validation["bindingConflicts"][0]["conflictingCanonicalProductIds"] == [
        "canonical-2"
    ]
    assert source_service.get_source(source["id"], owner)["mapping"][
        "mappingReadiness"
    ] == "identity_validation_blocked"
    assert db.query(SourceProductIdentity).one().canonical_product_id == "canonical-1"


def test_stale_listing_evidence_binding_stage_is_atomic(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    _, source = _flowhub_sheet(
        service,
        owner,
        [{"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"}],
    )
    _save_sheet_mapping(service, owner, source)
    analysis = asyncio.run(service.snapshot_candidates(source["id"], owner))
    assert len(analysis["identityBindingProposals"]) == 1
    assert analysis["identityBindingProposals"][0]["listingEvidence"] == [
        {
            "listingId": "listing-501",
            "canonicalProductId": "canonical-1",
            "mappingVersion": 1,
        }
    ]

    listing = db.get(Listing, "listing-501")
    assert listing is not None
    listing.mapping_version = 2
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.stage_source_product_identity_bindings(
            source_id=source["id"],
            mapping_revision_id=analysis["mapping"]["id"],
            source_revision_kind="flowhub_sheet_revision",
            source_revision_id=analysis["sheetRevision"]["id"],
            dataset_id=None,
            sheet_revision_id=analysis["sheetRevision"]["id"],
            proposals=analysis["identityBindingProposals"],
            user=owner,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "SOURCE_LISTING_IDENTITY_CHANGED"
    assert db.query(SourceProductIdentity).count() == 0


@pytest.mark.parametrize("stale_change", ["disabled", "remapped"])
def test_binding_proposal_rechecks_all_resolved_same_product_listings(
    db: Session,
    owner: FlowHubUser,
    stale_change: str,
) -> None:
    service = SourceWorkspaceService(db)
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-woo-501",
        external_id="501",
    )
    db.add_all(
        [
            CanonicalProduct(
                id="canonical-2",
                name="Replacement product",
                sku="SKU-REPLACEMENT",
                product_type="simple",
                status="active",
            ),
            Listing(
                id="listing-snapp-701",
                canonical_product_id="canonical-1",
                channel_id="snappshop:main",
                external_primary_id="701",
                external_id_type="product_id",
                label="Snapp 701",
                mapping_state="resolved",
                mapping_version=1,
                enabled=True,
            ),
        ]
    )
    db.commit()
    sheet = service.create_sheet(
        name="Multi-listing identity evidence",
        columns=[
            {"column_key": "product-name", "name": "Product Name", "position": 1},
            {"column_key": "source-key", "name": "Source Key", "position": 2},
            {"column_key": "woo-id", "name": "Woo ID", "position": 3},
            {"column_key": "snapp-id", "name": "Snapp ID", "position": 4},
            {"column_key": "snapp-stock", "name": "Snapp Stock", "position": 5},
            {"column_key": "snapp-status", "name": "Snapp Status", "position": 6},
        ],
        user=owner,
    )
    sheet = service.append_sheet_rows(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        count=1,
        user=owner,
    )
    row_key = sheet["rows"][0]["rowKey"]
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {"row_key": row_key, "column_key": "product-name", "value": "Cable"},
            {"row_key": row_key, "column_key": "source-key", "value": "erp-101"},
            {"row_key": row_key, "column_key": "woo-id", "value": "501"},
            {"row_key": row_key, "column_key": "snapp-id", "value": "701"},
            {"row_key": row_key, "column_key": "snapp-stock", "value": "5"},
            {
                "row_key": row_key,
                "column_key": "snapp-status",
                "value": "instock",
            },
        ],
        user=owner,
    )
    source = service.get_source(sheet["sourceId"], owner)
    service.save_mapping(
        source_id=source["id"],
        expected_source_version=source["version"],
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        source_fields=[
            {
                "field": "name",
                "reference_type": "column_id",
                "reference_value": "product-name",
                "required": True,
            },
            {
                "field": "source_key",
                "reference_type": "column_id",
                "reference_value": "source-key",
                "required": True,
            },
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "enabled": True,
                "fields": [
                    {
                        "field": "external_id",
                        "reference_type": "column_id",
                        "reference_value": "woo-id",
                    }
                ],
            },
            {
                "channel_id": "snappshop:main",
                "enabled": True,
                "fields": [
                    {
                        "field": "external_id",
                        "reference_type": "column_id",
                        "reference_value": "snapp-id",
                    },
                    {
                        "field": "stock",
                        "reference_type": "column_id",
                        "reference_value": "snapp-stock",
                    },
                    {
                        "field": "status",
                        "reference_type": "column_id",
                        "reference_value": "snapp-status",
                    },
                ],
            },
        ],
        value_policy={},
        identity_policy_version=2,
        identity_authority=_authority("erp", "ERP"),
        user=owner,
    )

    analysis = asyncio.run(service.snapshot_candidates(source["id"], owner))

    assert len(analysis["candidates"]) == 1
    assert any(
        issue["code"] == "LISTING_CACHE_UNAVAILABLE"
        and issue["technicalDetails"]["listing_id"] == "listing-snapp-701"
        for issue in analysis["issues"]
    )
    assert len(analysis["identityBindingProposals"]) == 1
    proposal = analysis["identityBindingProposals"][0]
    assert proposal["canonicalProductId"] == "canonical-1"
    assert proposal["listingEvidence"] == [
        {
            "listingId": "listing-snapp-701",
            "canonicalProductId": "canonical-1",
            "mappingVersion": 1,
        },
        {
            "listingId": "listing-woo-501",
            "canonicalProductId": "canonical-1",
            "mappingVersion": 1,
        },
    ]

    snapp_listing = db.get(Listing, "listing-snapp-701")
    assert snapp_listing is not None
    if stale_change == "disabled":
        snapp_listing.enabled = False
    else:
        snapp_listing.canonical_product_id = "canonical-2"
        snapp_listing.mapping_version = 2
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        service.stage_source_product_identity_bindings(
            source_id=source["id"],
            mapping_revision_id=analysis["mapping"]["id"],
            source_revision_kind="flowhub_sheet_revision",
            source_revision_id=analysis["sheetRevision"]["id"],
            dataset_id=None,
            sheet_revision_id=analysis["sheetRevision"]["id"],
            proposals=analysis["identityBindingProposals"],
            user=owner,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "SOURCE_LISTING_IDENTITY_CHANGED"
    assert db.query(SourceProductIdentity).count() == 0


@pytest.mark.parametrize(
    ("enabled", "mapping_state"),
    [(False, "resolved"), (True, "unresolved")],
)
def test_listing_not_ready_yields_explicit_issue_and_no_identity_proposal(
    db: Session,
    owner: FlowHubUser,
    enabled: bool,
    mapping_state: str,
) -> None:
    service = SourceWorkspaceService(db)
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    listing = db.get(Listing, "listing-501")
    assert listing is not None
    listing.enabled = enabled
    listing.mapping_state = mapping_state
    db.commit()
    _, source = _flowhub_sheet(
        service,
        owner,
        [{"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"}],
    )
    _save_sheet_mapping(service, owner, source)

    analysis = asyncio.run(service.snapshot_candidates(source["id"], owner))

    assert analysis["candidates"] == []
    assert analysis["identityBindingProposals"] == []
    issue = next(
        item
        for item in analysis["issues"]
        if item["code"] == "LISTING_IDENTITY_NOT_RESOLVED"
    )
    assert issue["technicalDetails"] == {
        "listing_id": "listing-501",
        "mapping_state": mapping_state,
        "enabled": enabled,
    }
    assert db.query(SourceProductIdentity).count() == 0


def test_source_key_case_variants_form_one_duplicate_group(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    _, source = _flowhub_sheet(
        service,
        owner,
        [
            {"product-name": "Cable A", "source-key": "ABC", "woo-id": "501"},
            {"product-name": "Cable B", "source-key": "abc", "woo-id": "502"},
        ],
    )

    saved = _save_sheet_mapping(service, owner, source)

    validation = saved["identityValidation"]
    assert validation["status"] == "blocked"
    assert validation["duplicateKeyCount"] == 1
    assert validation["duplicateRowCount"] == 2
    assert validation["duplicateGroups"] == [
        {
            "keyValue": "ABC",
            "rows": [
                {"worksheetName": "Sheet1", "rowNumber": 1},
                {"worksheetName": "Sheet1", "rowNumber": 2},
            ],
        }
    ]


def test_flowhub_sheet_identity_passes_with_duplicate_names_and_unique_keys(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    _, source = _flowhub_sheet(
        service,
        owner,
        [
            {"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"},
            {"product-name": "Cable", "source-key": "erp-102", "woo-id": "502"},
        ],
    )

    saved = _save_sheet_mapping(service, owner, source)

    validation = saved["identityValidation"]
    assert validation["status"] == "pass"
    assert validation["participatingRowCount"] == 2
    assert validation["validKeyCount"] == 2
    assert validation["missingKeyCount"] == 0
    assert validation["duplicateKeyCount"] == 0
    assert validation["duplicateRowCount"] == 0
    assert validation["evidence"]["kind"] == "flowhub_sheet_revision"
    assert saved["mappingReadiness"] == "ready"
    assert db.query(SourceMappingIdentityAssessment).count() == 1


def test_local_identity_validation_reports_missing_and_duplicate_rows_and_blocks_activation(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    _, source = _flowhub_sheet(
        service,
        owner,
        [
            {"product-name": "Cable A", "source-key": "duplicate-7", "woo-id": "501"},
            {"product-name": "Cable B", "source-key": "duplicate-7", "woo-id": "502"},
            {"product-name": "Cable C", "source-key": "", "woo-id": "503"},
        ],
    )

    saved = _save_sheet_mapping(service, owner, source)

    validation = saved["identityValidation"]
    assert validation["status"] == "blocked"
    assert validation["participatingRowCount"] == 3
    assert validation["validKeyCount"] == 0
    assert validation["missingKeyCount"] == 1
    assert validation["duplicateKeyCount"] == 1
    assert validation["duplicateRowCount"] == 2
    assert validation["missingRows"] == [
        {"worksheetName": "Sheet1", "rowNumber": 3}
    ]
    assert validation["duplicateGroups"] == [
        {
            "keyValue": "duplicate-7",
            "rows": [
                {"worksheetName": "Sheet1", "rowNumber": 1},
                {"worksheetName": "Sheet1", "rowNumber": 2},
            ],
        }
    ]
    assert validation["mappingReferences"] == [
        {
            "field": "source_key",
            "worksheetName": "Sheet1",
            "referenceType": "column_id",
            "referenceValue": "source-key",
        }
    ]
    assert saved["mappingReadiness"] == "identity_validation_blocked"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.snapshot_candidates(source["id"], owner))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "SOURCE_IDENTITY_VALIDATION_BLOCKED"
    assert exc_info.value.detail["details"]["identityValidation"]["status"] == "blocked"
    assert db.query(WorkspaceSnapshot).count() == 0


def test_same_column_can_be_source_key_and_woocommerce_product_identifier(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)

    saved = service.save_mapping(
        **_external_mapping_payload(
            source,
            owner,
            authority=_authority("woocommerce", "WooCommerce / Website"),
            source_key_column="B",
            woo_identifier_column="B",
        )
    )

    source_key = next(
        item for item in saved["sourceFields"] if item["field"] == "source_key"
    )
    woo_identifier = next(
        item
        for item in saved["channels"][0]["fields"]
        if item["field"] == "external_id"
    )
    assert source_key["referenceValue"] == "B"
    assert woo_identifier["referenceValue"] == "B"


def test_public_mapping_save_contract_rejects_identity_policy_v1() -> None:
    payload = {
        "expected_source_version": 1,
        "worksheet_mode": "all",
        "worksheet_name": None,
        "data_start_row": 2,
        "source_fields": [
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
        ],
        "channel_mappings": [],
        "identity_policy_version": 1,
        "identity_authority": _authority("erp", "ERP"),
    }

    with pytest.raises(ValidationError) as exc_info:
        MappingSaveRequest.model_validate(payload)

    assert any(
        error["loc"] == ("identity_policy_version",)
        for error in exc_info.value.errors()
    )


def test_historical_identity_policy_v1_mapping_cannot_activate(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    _, source = _flowhub_sheet(
        service,
        owner,
        [{"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"}],
    )
    saved = _save_sheet_mapping(service, owner, source)
    db.execute(
        text(
            "UPDATE sc_source_mapping_revisions "
            "SET identity_policy_version = 1, identity_authority_json = '{}' "
            "WHERE id = :mapping_id"
        ),
        {"mapping_id": saved["id"]},
    )
    db.commit()
    db.expire_all()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.snapshot_candidates(source["id"], owner))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "SOURCE_IDENTITY_POLICY_UPGRADE_REQUIRED"
    assert db.query(WorkspaceSnapshot).count() == 0

    db.execute(
        text(
            "UPDATE sc_source_mapping_revisions "
            "SET identity_policy_version = 2 WHERE id = :mapping_id"
        ),
        {"mapping_id": saved["id"]},
    )
    db.commit()
    db.expire_all()

    refreshed = service.get_source(source["id"], owner)
    assert refreshed["mappingReadiness"] == "identity_validation_pending"
    with pytest.raises(HTTPException) as authority_exc_info:
        asyncio.run(service.snapshot_candidates(source["id"], owner))
    assert authority_exc_info.value.status_code == 422
    assert authority_exc_info.value.detail["code"] == (
        "SOURCE_IDENTITY_AUTHORITY_REQUIRED"
    )
    assert db.query(WorkspaceSnapshot).count() == 0


def test_disabled_incomplete_channel_is_ignored_by_required_mapping_validation(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)

    saved = service.save_mapping(
        **_external_mapping_payload(
            source,
            owner,
            include_disabled_snappshop=True,
        )
    )

    snappshop = next(
        channel
        for channel in saved["channels"]
        if channel["channelId"] == "snappshop:main"
    )
    assert snappshop["enabled"] is False
    assert snappshop["fields"] == []
    assert saved["identityValidation"]["status"] == "pending"


@pytest.mark.parametrize(
    ("system_identifier", "display_label"),
    [("snappshop", "SnappShop"), ("erp", "ERP / Accounting")],
)
def test_identity_authority_is_metadata_and_does_not_enable_its_channel(
    db: Session,
    owner: FlowHubUser,
    system_identifier: str,
    display_label: str,
) -> None:
    service = SourceWorkspaceService(db)
    source = _external_source(service, owner)

    saved = service.save_mapping(
        **_external_mapping_payload(
            source,
            owner,
            authority=_authority(system_identifier, display_label),
            include_disabled_snappshop=True,
        )
    )

    assert saved["identityAuthority"]["systemIdentifier"] == system_identifier
    enabled_mapping_ids = {
        channel["channelId"]
        for channel in saved["channels"]
        if channel["enabled"]
    }
    assert enabled_mapping_ids == {"woocommerce:primary"}
    persisted_enabled_ids = {
        item.channel_id
        for item in db.query(SourceChannelMapping)
        .filter(
            SourceChannelMapping.mapping_revision_id == saved["id"],
            SourceChannelMapping.enabled.is_(True),
        )
        .all()
    }
    assert persisted_enabled_ids == {"woocommerce:primary"}


def test_explicit_saved_identity_validation_replays_latest_sheet_revision_without_provider_io(
    db: Session,
    owner: FlowHubUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SourceWorkspaceService(db)
    sheet, source = _flowhub_sheet(
        service,
        owner,
        [{"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"}],
    )
    saved = _save_sheet_mapping(service, owner, source)
    assert saved["identityValidation"]["status"] == "pass"

    # A new immutable Sheet revision makes the previous assessment stale. The
    # explicit validation action must replay that revision locally.
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {
                "row_key": sheet["rows"][0]["rowKey"],
                "column_key": "product-name",
                "value": "Cable renamed",
            }
        ],
        user=owner,
    )
    assert service.get_source(source["id"], owner)["mapping"]["mappingReadiness"] == (
        "identity_validation_pending"
    )
    calls = _forbid_provider_io(monkeypatch, service)

    validation = service.validate_saved_mapping_identity(source["id"], owner)

    assert validation["status"] == "pass"
    assert validation["evidence"]["kind"] == "flowhub_sheet_revision"
    assert validation["evidence"]["sourceRevisionId"] == sheet["revisionId"]
    assert calls == {"workspace_read": 0, "provider_read": 0, "reservation": 0}
    assert db.query(DlSourceReadReservation).count() == 0
    refreshed = service.get_source(source["id"], owner)["mapping"]
    assert refreshed["mappingReadiness"] == "ready"
    assert db.query(SourceMappingIdentityAssessment).count() == 2


def test_source_product_identity_binding_is_reused_and_conflicting_listing_is_blocked(
    db: Session,
    owner: FlowHubUser,
) -> None:
    service = SourceWorkspaceService(db)
    _add_cached_listing(
        db,
        product_id="canonical-1",
        listing_id="listing-501",
        external_id="501",
    )
    _add_cached_listing(
        db,
        product_id="canonical-2",
        listing_id="listing-502",
        external_id="502",
    )
    sheet, source = _flowhub_sheet(
        service,
        owner,
        [{"product-name": "Cable", "source-key": "erp-101", "woo-id": "501"}],
    )
    saved = _save_sheet_mapping(service, owner, source)
    assert saved["mappingReadiness"] == "ready"

    first = asyncio.run(service.snapshot_candidates(source["id"], owner))
    assert len(first["candidates"]) == 1
    assert first["candidates"][0]["canonicalProductId"] == "canonical-1"
    assert first["issues"] == []
    # Candidate analysis is read-only with respect to durable identity. The
    # proposal is accepted atomically only by Workspace activation; seed that
    # already-accepted history here to exercise subsequent validation.
    assert db.query(SourceProductIdentity).count() == 0
    assert len(first["identityBindingProposals"]) == 1
    proposal = first["identityBindingProposals"][0]
    binding = SourceProductIdentity(
        id=str(uuid.uuid4()),
        source_id=source["id"],
        source_key_hash=proposal["sourceKeyHash"],
        normalized_source_key=proposal["normalizedSourceKey"],
        normalization_version=proposal["normalizationVersion"],
        canonical_product_id=proposal["canonicalProductId"],
        first_mapping_revision_id=saved["id"],
        first_source_revision_kind="flowhub_sheet_revision",
        first_source_revision_id=first["sheetRevision"]["id"],
        first_dataset_id=None,
        first_sheet_revision_id=first["sheetRevision"]["id"],
        identity_authority_json=saved["identityAuthority"],
        created_at=utcnow(),
    )
    db.add(binding)
    db.commit()
    binding_id = binding.id
    assert binding.normalized_source_key == "erp-101"
    assert binding.canonical_product_id == "canonical-1"
    assert binding.identity_authority_json["systemIdentifier"] == "internal-erp"

    # A later Source revision with the same stable key and Listing must reuse
    # the immutable binding rather than minting another product identity.
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {
                "row_key": sheet["rows"][0]["rowKey"],
                "column_key": "product-name",
                "value": "Cable renamed",
            }
        ],
        user=owner,
    )
    second = asyncio.run(service.snapshot_candidates(source["id"], owner))
    assert len(second["candidates"]) == 1
    assert second["issues"] == []
    assert db.query(SourceProductIdentity).count() == 1
    assert db.query(SourceProductIdentity).one().id == binding_id

    # Repointing the Channel identifier to a Listing under another Canonical
    # Product does not silently rebind the durable Source Product Key.
    sheet = service.patch_sheet_revision(
        sheet_id=sheet["id"],
        expected_version=sheet["version"],
        changes=[
            {
                "row_key": sheet["rows"][0]["rowKey"],
                "column_key": "woo-id",
                "value": "502",
            }
        ],
        user=owner,
    )
    validation = service.validate_saved_mapping_identity(source["id"], owner)
    assert validation["status"] == "blocked"
    assert validation["validKeyCount"] == 0
    assert validation["bindingConflictCount"] == 1
    assert validation["bindingConflicts"] == [
        {
            "keyValue": "erp-101",
            "rows": [{"worksheetName": "Sheet1", "rowNumber": 1}],
            "boundCanonicalProductId": "canonical-1",
            "conflictingCanonicalProductIds": ["canonical-2"],
        }
    ]
    assert service.get_source(source["id"], owner)["mapping"]["mappingReadiness"] == (
        "identity_validation_blocked"
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.snapshot_candidates(source["id"], owner))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "SOURCE_IDENTITY_VALIDATION_BLOCKED"
    assert exc_info.value.detail["details"]["identityValidation"][
        "bindingConflictCount"
    ] == 1
    assert db.query(SourceProductIdentity).count() == 1
    assert db.query(SourceProductIdentity).one().canonical_product_id == "canonical-1"
