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
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.domain import utcnow
from app.flowhub.unified_workspace.models import CurrencyProfile, UnifiedAuditEntry


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

        result = service.delete_or_archive_source(
            source_id=str(source["id"]),
            expected_source_version=int(source["version"]),
            confirmation_name=str(source["name"]),
            user=user,
        )
        db.expire_all()

        assert result["outcome"] == "archived"
        assert db.get(SourceProfile, str(source["id"])).status == "disabled"
        assert db.get(SourceProfile, str(unrelated_source["id"])).status == "active"
        assert db.get(IntegrationConnectorInstance, target_connector.id).enabled is False
        assert db.get(IntegrationConnectorInstance, unrelated_connector.id).enabled is True
        assert db.get(AcquisitionRun, run_id) is not None
        assert db.get(SourceObservation, observation_id) is not None
        assert db.query(CurrencyProfile).filter_by(
            scope="source", scope_reference=str(source["id"])
        ).count() == 1
        audit = db.query(UnifiedAuditEntry).filter_by(event_type="source_archived").one()
        assert audit.metadata_json["sourceId"] == source["id"]
        assert audit.metadata_json["connectorDisabled"] is True
