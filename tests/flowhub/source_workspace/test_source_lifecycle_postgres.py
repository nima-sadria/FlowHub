from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.source_acquisition.models import (
    AcquisitionRun,
    SourceObservation,
    SourceObservationVersionHead,
)
from app.flowhub.source_workspace.models import FlowHubSheet, SourceProfile
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.domain import utcnow
from app.flowhub.unified_workspace.models import CurrencyProfile, UnifiedAuditEntry


def test_postgresql_unused_source_is_physically_removed(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine, expire_on_commit=False) as db:
        user = FlowHubUser(
            id=2,
            username="source-lifecycle-postgres-unused",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        service = SourceWorkspaceService(db)
        source = service.create_source(
            name="PostgreSQL unused Source",
            source_kind="flowhub_sheet",
            external_source_id=None,
            worksheet_mode="selected",
            worksheet_name="Prices",
            data_start_row=2,
            user=user,
        )
        sheet_id = str(source["sheetId"])

        result = service.permanently_delete_source(
            source_id=str(source["id"]),
            expected_source_version=int(source["version"]),
            confirmation_name=str(source["name"]),
            confirm_permanent_delete=True,
            confirm_history_policy=True,
            user=user,
        )

        assert result["tombstone"] is False
        assert db.get(SourceProfile, str(source["id"])) is None
        assert db.get(FlowHubSheet, sheet_id) is None
        audits = db.query(UnifiedAuditEntry).filter_by(event_type="source_deleted").all()
        audit = next(
            entry for entry in audits if entry.metadata_json["sourceId"] == source["id"]
        )
        assert audit.metadata_json["tombstone"] is False


def test_postgresql_delete_failure_rolls_back_all_source_changes(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(postgres_engine, expire_on_commit=False) as db:
        user = FlowHubUser(
            id=3,
            username="source-lifecycle-postgres-rollback",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        service = SourceWorkspaceService(db)
        source = service.create_source(
            name="PostgreSQL rollback Source",
            source_kind="external",
            external_source_id="nextcloud:postgres-rollback",
            worksheet_mode="all",
            worksheet_name=None,
            data_start_row=1,
            user=user,
        )
        connector = IntegrationConnectorInstance(
            id="nextcloud:postgres-rollback",
            connector_type="nextcloud",
            name="PostgreSQL rollback Source",
            enabled=True,
            read_only=True,
            status="healthy",
        )
        db.add(connector)
        db.commit()

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated PostgreSQL delete failure")

        monkeypatch.setattr(service, "_delete_operational_source_state", fail)
        with pytest.raises(RuntimeError, match="simulated PostgreSQL delete failure"):
            service.permanently_delete_source(
                source_id=str(source["id"]),
                expected_source_version=int(source["version"]),
                confirmation_name=str(source["name"]),
                confirm_permanent_delete=True,
                confirm_history_policy=True,
                user=user,
            )
        db.rollback()

        persisted_source = db.get(SourceProfile, str(source["id"]))
        assert persisted_source is not None
        assert persisted_source.status == "active"
        assert db.get(IntegrationConnectorInstance, connector.id) is not None


@pytest.fixture(scope="module")  # type: ignore[untyped-decorator]
def postgres_engine() -> Generator[Engine, None, None]:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"source_lifecycle_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        database_name = str(
            connection.execute(sa.text("SELECT current_database()"))
            .scalar_one()
        ).lower()
        if "test" not in database_name:
            pytest.fail("FLOWHUB_TEST_POSTGRES_URL must target an isolated test database")
        connection.execute(sa.schema.CreateSchema(schema))

    engine = sa.create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_pre_ping=True,
    )
    FlowHubBase.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        admin_engine.dispose()


def test_postgresql_archives_source_history_and_disables_only_bound_connector(
    postgres_engine: Engine,
) -> None:
    now = utcnow()
    with Session(postgres_engine, expire_on_commit=False) as db:
        user = FlowHubUser(
            id=1,
            username="source-lifecycle-postgres-owner",
            hashed_password="x",
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        service = SourceWorkspaceService(db)
        source = service.create_source(
            name="PostgreSQL observed Source",
            source_kind="external",
            external_source_id="nextcloud:postgres-history",
            worksheet_mode="selected",
            worksheet_name="Prices",
            data_start_row=2,
            currency="IRR",
            currency_unit="RIAL",
            user=user,
        )
        unrelated_source = service.create_source(
            name="Unrelated PostgreSQL Source",
            source_kind="external",
            external_source_id="nextcloud:postgres-unrelated",
            worksheet_mode="all",
            worksheet_name=None,
            data_start_row=1,
            user=user,
        )
        target_connector = IntegrationConnectorInstance(
            id="nextcloud:postgres-history",
            connector_type="nextcloud",
            name="PostgreSQL observed Source",
            enabled=True,
            read_only=True,
            status="healthy",
        )
        unrelated_connector = IntegrationConnectorInstance(
            id="nextcloud:postgres-unrelated",
            connector_type="nextcloud",
            name="Unrelated PostgreSQL Source",
            enabled=True,
            read_only=True,
            status="healthy",
        )
        run_id = str(uuid.uuid4())
        observation_id = str(uuid.uuid4())
        run = AcquisitionRun(
            id=run_id,
            source_id=str(source["id"]),
            resource_scope="source",
            trigger_kind="manual",
            request_fingerprint="f" * 64,
            correlation_id=run_id,
            root_run_id=run_id,
            attempt_number=1,
            status="succeeded",
            result="observed",
            queued_at=now,
            terminal_at=now,
            created_at=now,
            updated_at=now,
        )
        observation = SourceObservation(
            id=observation_id,
            acquisition_run_id=run_id,
            source_id=str(source["id"]),
            resource_scope="source",
            resource_identity="/pricing.xlsx",
            resource_identity_hash="r" * 64,
            observation_version=1,
            observed_at=now,
            provenance_json={"provider": "test"},
            checksum="o" * 64,
            created_at=now,
        )
        head = SourceObservationVersionHead(
            source_id=str(source["id"]),
            resource_scope="source",
            next_version=2,
            updated_at=now,
        )
        db.add_all([target_connector, unrelated_connector, run, observation, head])
        db.commit()

        impact = service.source_lifecycle(str(source["id"]), user)
        assert impact["action"] == "archive"
        assert impact["protectedHistory"]["acquisitionRuns"] == 1
        assert impact["protectedHistory"]["sourceObservations"] == 1
        assert impact["protectedHistory"]["currencyProfiles"] == 1

        result = service.permanently_delete_source(
            source_id=str(source["id"]),
            expected_source_version=int(source["version"]),
            confirmation_name=str(source["name"]),
            confirm_permanent_delete=True,
            confirm_history_policy=True,
            user=user,
        )
        db.expire_all()

        assert result["outcome"] == "deleted"
        assert result["tombstone"] is True
        archived_source = db.get(SourceProfile, str(source["id"]))
        assert archived_source.status == "deleted"
        assert archived_source.deleted_at is not None
        assert db.get(SourceProfile, str(unrelated_source["id"])).status == "active"
        assert db.get(IntegrationConnectorInstance, target_connector.id) is None
        assert db.get(IntegrationConnectorInstance, unrelated_connector.id).enabled is True
        assert db.get(AcquisitionRun, run_id) is not None
        assert db.get(SourceObservation, observation_id) is not None
        assert db.query(CurrencyProfile).filter_by(
            scope="source", scope_reference=str(source["id"])
        ).count() == 1
        audits = db.query(UnifiedAuditEntry).filter_by(event_type="source_deleted").all()
        audit = next(
            entry for entry in audits if entry.metadata_json["sourceId"] == source["id"]
        )
        assert audit.metadata_json["sourceId"] == source["id"]
        assert audit.metadata_json["tombstone"] is True
