from __future__ import annotations

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_workspace.models import FlowHubSheet, SheetRevision, SourceProfile
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.models import (
    CurrencyProfile,
    UnifiedAuditEntry,
    UnifiedWorkspace,
    WorkspaceSnapshot,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _user(db: Session, *, role: str = "admin", user_id: int = 1) -> FlowHubUser:
    user = FlowHubUser(
        id=user_id,
        username=f"source-{role}-{user_id}",
        hashed_password="x",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _empty_source(
    service: SourceWorkspaceService, user: FlowHubUser, name: str
) -> dict[str, Any]:
    return service.create_source(
        name=name,
        source_kind="flowhub_sheet",
        external_source_id=None,
        worksheet_mode="selected",
        worksheet_name="Sheet1",
        data_start_row=1,
        user=user,
    )


def _workspace_snapshot(
    db: Session,
    *,
    source_id: str,
    user: FlowHubUser,
    workspace_status: str,
) -> None:
    currency = CurrencyProfile(
        id=f"currency-{source_id}",
        scope="global",
        scope_reference=f"source-lifecycle-{source_id}",
        currency="IRR",
        unit="IRR",
        normalization_currency="IRR",
        normalization_unit="IRR",
        conversion_factor=Decimal("1"),
        conversion_rule="identity",
        checksum=("c" * 63) + source_id[-1],
        version=1,
        enabled=True,
    )
    workspace = UnifiedWorkspace(
        id=f"workspace-{source_id}",
        name="Source lifecycle workspace",
        entry_point="source",
        source_type="flowhub_sheet",
        owner_user_id=user.id,
        status=workspace_status,
        version=1,
    )
    snapshot = WorkspaceSnapshot(
        id=f"snapshot-{source_id}",
        workspace_id=workspace.id,
        entry_point="source",
        source_type="flowhub_sheet",
        creator_user_id=user.id,
        schema_version="test-v1",
        content_checksum="a" * 64,
        normalization_version="test-v1",
        validation_ruleset_version="test-v1",
        mapping_version=1,
        currency_profile_id=currency.id,
        source_metadata_json={"source_id": source_id},
        acquisition_metadata_json={"read_once": True},
    )
    db.add_all([currency, workspace, snapshot])
    db.commit()


def test_unused_source_and_empty_internal_sheet_are_deleted_with_immutable_audit() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    source = _empty_source(service, user, "Temporary pricing source")
    sheet_id = str(source["sheetId"])

    impact = service.source_lifecycle(str(source["id"]), user)
    assert impact["action"] == "delete"
    assert impact["protectedHistory"] == {}

    result = service.delete_or_archive_source(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        confirmation_name=str(source["name"]),
        user=user,
    )

    assert result["outcome"] == "deleted"
    assert db.get(SourceProfile, str(source["id"])) is None
    assert db.get(FlowHubSheet, sheet_id) is None
    audit = db.query(UnifiedAuditEntry).filter_by(event_type="source_deleted").one()
    assert audit.metadata_json["sourceId"] == source["id"]
    assert audit.metadata_json["sourceName"] == source["name"]


def test_protected_source_is_archived_and_history_remains_readable_but_not_mutable() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    sheet = service.create_sheet(
        name="Historical pricing source",
        columns=[{"column_key": "name", "name": "Name", "position": 1}],
        user=user,
    )
    source = service.get_source(str(sheet["sourceId"]), user)
    revision_id = str(sheet["revisionId"])

    result = service.delete_or_archive_source(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        confirmation_name=str(source["name"]),
        user=user,
    )

    assert result["outcome"] == "archived"
    archived = service.get_source(str(source["id"]), user)
    assert archived["status"] == "disabled"
    assert db.get(SheetRevision, revision_id) is not None
    assert service.get_sheet(str(sheet["id"]), user, page=1, page_size=200)["revisionId"] == revision_id
    audit = db.query(UnifiedAuditEntry).filter_by(event_type="source_archived").one()
    assert audit.metadata_json["protectedHistory"]["sheetRevisions"] == 1

    with pytest.raises(HTTPException) as mapping_error:
        service.save_mapping(
            source_id=str(source["id"]),
            expected_source_version=int(archived["version"]),
            worksheet_mode="selected",
            worksheet_name="Sheet1",
            data_start_row=1,
            source_fields=[
                {
                    "field": "name",
                    "reference_type": "column_id",
                    "reference_value": "name",
                    "required": True,
                }
            ],
            channel_mappings=[],
            value_policy={},
            user=user,
        )
    assert mapping_error.value.status_code == 409
    assert cast(dict[str, Any], mapping_error.value.detail)["code"] == "SOURCE_ARCHIVED"

    with pytest.raises(HTTPException) as sheet_error:
        service.append_sheet_rows(
            sheet_id=str(sheet["id"]),
            expected_version=int(sheet["version"]),
            count=1,
            user=user,
        )
    assert sheet_error.value.status_code == 409
    assert cast(dict[str, Any], sheet_error.value.detail)["code"] == "SOURCE_ARCHIVED"

    with pytest.raises(HTTPException) as preview_error:
        asyncio.run(service.source_preview(str(source["id"]), user, page=1, page_size=10))
    assert preview_error.value.status_code == 409
    assert cast(dict[str, Any], preview_error.value.detail)["code"] == "SOURCE_ARCHIVED"

    with pytest.raises(HTTPException) as candidate_error:
        asyncio.run(service.snapshot_candidates(str(source["id"]), user))
    assert candidate_error.value.status_code == 409
    assert cast(dict[str, Any], candidate_error.value.detail)["code"] == "SOURCE_ARCHIVED"


def test_active_workspace_blocks_source_deletion_or_archival() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    source = _empty_source(service, user, "Active source")
    _workspace_snapshot(db, source_id=str(source["id"]), user=user, workspace_status="active")

    impact = service.source_lifecycle(str(source["id"]), user)
    assert impact["action"] == "blocked"
    assert impact["blockers"] == {"activeWorkspaces": 1}

    with pytest.raises(HTTPException) as blocked:
        service.delete_or_archive_source(
            source_id=str(source["id"]),
            expected_source_version=int(source["version"]),
            confirmation_name=str(source["name"]),
            user=user,
        )
    assert blocked.value.status_code == 409
    assert cast(dict[str, Any], blocked.value.detail)["code"] == "SOURCE_ACTIVE_WORKSPACE"
    persisted_source = db.get(SourceProfile, str(source["id"]))
    assert persisted_source is not None
    assert persisted_source.status == "active"
    assert db.query(UnifiedAuditEntry).filter(
        UnifiedAuditEntry.event_type.in_(["source_deleted", "source_archived"])
    ).count() == 0


def test_historical_snapshot_causes_archive_without_deleting_history() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    source = _empty_source(service, user, "Historical snapshot source")
    _workspace_snapshot(db, source_id=str(source["id"]), user=user, workspace_status="archived")

    result = service.delete_or_archive_source(
        source_id=str(source["id"]),
        expected_source_version=int(source["version"]),
        confirmation_name=str(source["name"]),
        user=user,
    )

    assert result["outcome"] == "archived"
    assert result["impact"]["protectedHistory"]["workspaceSnapshots"] == 1
    assert db.get(WorkspaceSnapshot, f"snapshot-{source['id']}") is not None


def test_confirmation_name_and_version_are_required_before_lifecycle_change() -> None:
    db = _session()
    user = _user(db)
    service = SourceWorkspaceService(db)
    source = _empty_source(service, user, "Confirmed source name")

    with pytest.raises(HTTPException) as name_error:
        service.delete_or_archive_source(
            source_id=str(source["id"]),
            expected_source_version=int(source["version"]),
            confirmation_name="A different source",
            user=user,
        )
    assert name_error.value.status_code == 409
    assert cast(dict[str, Any], name_error.value.detail)["code"] == "SOURCE_CONFIRMATION_MISMATCH"

    with pytest.raises(HTTPException) as version_error:
        service.delete_or_archive_source(
            source_id=str(source["id"]),
            expected_source_version=999,
            confirmation_name=str(source["name"]),
            user=user,
        )
    assert version_error.value.status_code == 409
    assert cast(dict[str, Any], version_error.value.detail)["code"] == "SOURCE_VERSION_CONFLICT"
    assert db.get(SourceProfile, str(source["id"])) is not None
    assert db.query(UnifiedAuditEntry).count() == 0


def test_source_lifecycle_api_requires_workspace_admin_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from app.flowhub.app import app
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.database import get_db

    monkeypatch.setenv("FLOWHUB_JWT_SECRET", "source-lifecycle-test-secret-at-least-32-bytes")
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    viewer = _user(session, role="viewer", user_id=41)
    source = _empty_source(SourceWorkspaceService(session), viewer, "Viewer source")

    def override_get_db() -> Iterator[Session]:
        request_session = SessionFactory()
        try:
            yield request_session
        finally:
            request_session.close()

    app.dependency_overrides[get_db] = override_get_db
    token = create_access_token(viewer.id, viewer.username, viewer.role)
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.request(
                "DELETE",
                f"/api/v2/sources/{source['id']}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "expected_source_version": source["version"],
                    "confirmation_name": source["name"],
                },
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "WORKSPACE_PERMISSION_DENIED"
    finally:
        app.dependency_overrides.clear()
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()
