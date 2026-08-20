from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.source_workspace.service import SourceWorkspaceService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _user(db: Session) -> FlowHubUser:
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


def _connector(db: Session, connector_id: str, *, enabled: bool = True) -> None:
    db.add(
        IntegrationConnectorInstance(
            id=connector_id,
            connector_type="nextcloud",
            name=connector_id,
            enabled=enabled,
            read_only=True,
            status="configured" if enabled else "disabled",
        )
    )
    db.commit()


def _create(service: SourceWorkspaceService, user: FlowHubUser, external_id: str) -> dict:
    return service.create_source(
        name="Nextcloud Source",
        source_kind="external",
        external_source_id=external_id,
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        user=user,
    )


def test_generic_nextcloud_identity_binds_to_the_one_exact_active_connector() -> None:
    db = _session()
    user = _user(db)
    _connector(db, "nextcloud:replacement")

    result = _create(SourceWorkspaceService(db), user, "nextcloud")

    assert result["externalSourceId"] == "nextcloud:replacement"


def test_legacy_primary_does_not_resurrect_when_replacement_is_active() -> None:
    db = _session()
    user = _user(db)
    _connector(db, "nextcloud:primary", enabled=False)
    _connector(db, "nextcloud:replacement")

    result = _create(SourceWorkspaceService(db), user, "nextcloud:primary")

    assert result["externalSourceId"] == "nextcloud:replacement"
    assert db.get(IntegrationConnectorInstance, "nextcloud:primary").enabled is False


def test_multiple_active_nextcloud_connectors_require_explicit_rebind() -> None:
    db = _session()
    user = _user(db)
    _connector(db, "nextcloud:a")
    _connector(db, "nextcloud:b")

    with pytest.raises(HTTPException) as error:
        _create(SourceWorkspaceService(db), user, "nextcloud")

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SOURCE_CONNECTOR_REBIND_REQUIRED"
    assert error.value.detail["candidate_source_ids"] == ["nextcloud:a", "nextcloud:b"]


def test_commerce_projection_hides_only_unmanaged_retired_primary() -> None:
    db = _session()
    user = _user(db)
    _connector(db, "nextcloud:primary", enabled=False)
    _connector(db, "nextcloud:replacement")

    listed = CommerceHubService(db).list_sources()
    assert "nextcloud:replacement" in {item["id"] for item in listed["items"]}
    assert "nextcloud:primary" not in {item["id"] for item in listed["items"]}

    db.add(
        SourceProfile(
            id="historical-source",
            name="Historical Nextcloud",
            source_kind="external",
            external_source_id="nextcloud:primary",
            worksheet_mode="all",
            worksheet_name=None,
            data_start_row=2,
            status="archived",
            version=1,
            owner_user_id=user.id,
        )
    )
    db.commit()

    listed = CommerceHubService(db).list_sources()
    assert {"nextcloud:primary", "nextcloud:replacement"}.issubset(
        {item["id"] for item in listed["items"]}
    )
