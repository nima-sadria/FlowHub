"""PostgreSQL regression coverage for Workspace Snapshot/Draft persistence.

These tests intentionally use ``autoflush=False`` to match the production
request session.  PostgreSQL enforces the foreign keys that originally exposed
the missing dependency ordering between ``uw_workspace_snapshots`` and
``uw_drafts``.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("FLOWHUB_JWT_SECRET", "workspace-postgres-test-secret-32-bytes")

# Importing the application registers every model used by the API before the
# isolated PostgreSQL schema is created.
from app.flowhub.app import app
from app.flowhub.auth.jwt_service import create_access_token
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.data_layer.models import DlProductCache
from app.flowhub.database import FlowHubBase, get_db
from app.flowhub.setup.models import FlowHubAppConfig
from app.flowhub.unified_workspace.models import (
    Draft,
    DraftRevision,
    SnapshotRow,
    UnifiedWorkspace,
    WorkspaceSnapshot,
)
from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

pytestmark = pytest.mark.postgres


@dataclass(frozen=True)
class PostgresApi:
    client: TestClient
    sessions: sessionmaker[Session]
    headers: dict[str, str]


@pytest.fixture(scope="module")  # type: ignore[untyped-decorator]
def postgres_engine() -> Generator[Engine, None, None]:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"workspace_snapshot_order_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        database_name = str(connection.execute(sa.text("SELECT current_database()")).scalar_one())
        if "test" not in database_name.lower():
            pytest.fail(
                "FLOWHUB_TEST_POSTGRES_URL must target an isolated database "
                "whose name contains 'test'"
            )
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


@pytest.fixture()  # type: ignore[untyped-decorator]
def postgres_api(postgres_engine: Engine) -> Generator[PostgresApi, None, None]:
    table_names = ", ".join(
        f'"{table.name}"' for table in FlowHubBase.metadata.sorted_tables
    )
    with postgres_engine.begin() as connection:
        connection.execute(
            sa.text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
        )

    sessions = sessionmaker(
        bind=postgres_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    username = f"workspace_pg_{uuid.uuid4().hex}"
    with sessions() as db:
        user = FlowHubUser(
            username=username,
            hashed_password="isolated-postgres-test-only",
            role="admin",
        )
        db.add_all(
            [
                user,
                FlowHubAppConfig(
                    key="server.currency",
                    value="EUR",
                    updated_by="postgres-test",
                ),
                FlowHubAppConfig(
                    key="server.currency_unit",
                    value="EUR",
                    updated_by="postgres-test",
                ),
                DlProductCache(
                    connector_id="woocommerce:primary",
                    product_id="101",
                    external_id=101,
                    sku="PG-SKU-101",
                    name="PostgreSQL Snapshot Product",
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
                    record_hash="postgres-workspace-cache-101",
                ),
            ]
        )
        db.commit()
        db.refresh(user)
        headers = {
            "Authorization": (
                f"Bearer {create_access_token(user.id, user.username, user.role)}"
            )
        }

    def override_get_db() -> Generator[Session, None, None]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield PostgresApi(client=client, sessions=sessions, headers=headers)
    finally:
        app.dependency_overrides.clear()


def _manual_request(
    api: PostgresApi,
    *,
    name: str,
    catalog: bool = False,
) -> dict[str, object]:
    body: dict[str, object] = {"name": name}
    if catalog:
        body["catalog_scope"] = {}
    else:
        body["selections"] = [
            {"connector_id": "woocommerce:primary", "product_id": "101"}
        ]
    response = api.client.post(
        "/api/v2/unified-workspaces/manual",
        headers=api.headers,
        json=body,
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def _inserted_table(statement: str) -> str | None:
    match = re.match(
        r'\s*INSERT\s+INTO\s+"?([a-zA-Z0-9_]+)"?',
        statement,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def test_postgresql_manual_workspace_persists_snapshot_before_draft(
    postgres_engine: Engine,
    postgres_api: PostgresApi,
) -> None:
    inserted_tables: list[str] = []

    def capture_insert(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        table = _inserted_table(statement)
        if table is not None:
            inserted_tables.append(table)

    sa.event.listen(postgres_engine, "before_cursor_execute", capture_insert)
    try:
        workspace = _manual_request(
            postgres_api,
            name="PostgreSQL manual workspace",
        )
    finally:
        sa.event.remove(postgres_engine, "before_cursor_execute", capture_insert)

    workspace_id = str(workspace["id"])
    snapshot_id = str(workspace["snapshot"]["id"])  # type: ignore[index]
    draft_id = str(workspace["draft"]["id"])  # type: ignore[index]
    with postgres_api.sessions() as db:
        snapshot = db.get(WorkspaceSnapshot, snapshot_id)
        draft = db.get(Draft, draft_id)
        assert db.get(UnifiedWorkspace, workspace_id) is not None
        assert snapshot is not None
        assert snapshot.workspace_id == workspace_id
        assert draft is not None
        assert draft.workspace_id == workspace_id
        assert draft.snapshot_id == snapshot_id
        assert (
            db.query(SnapshotRow)
            .filter(SnapshotRow.snapshot_id == snapshot_id)
            .count()
            == 1
        )

    assert inserted_tables.index("uw_workspaces") < inserted_tables.index(
        "uw_workspace_snapshots"
    )
    assert inserted_tables.index("uw_workspace_snapshots") < inserted_tables.index(
        "uw_snapshot_rows"
    )
    assert inserted_tables.index("uw_snapshot_rows") < inserted_tables.index(
        "uw_drafts"
    )


def test_postgresql_catalog_workspace_persists_snapshot_before_draft(
    postgres_api: PostgresApi,
) -> None:
    workspace = _manual_request(
        postgres_api,
        name="PostgreSQL Products catalog workspace",
        catalog=True,
    )
    snapshot_id = str(workspace["snapshot"]["id"])  # type: ignore[index]
    draft_id = str(workspace["draft"]["id"])  # type: ignore[index]

    with postgres_api.sessions() as db:
        draft = db.get(Draft, draft_id)
        assert db.get(WorkspaceSnapshot, snapshot_id) is not None
        assert draft is not None
        assert draft.snapshot_id == snapshot_id

    grid_response = postgres_api.client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grouped-grid"
        "?page=1&pageSize=100&view=all",
        headers=postgres_api.headers,
    )
    assert grid_response.status_code == 200, grid_response.text
    children = grid_response.json()["items"][0]["children"]
    assert children[0]["fields"]["price"]["readOnly"] is False


def test_postgresql_workspace_creation_rolls_back_after_snapshot_flush_failure(
    postgres_api: PostgresApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_after_snapshot_flush(
        service: UnifiedWorkspaceService,
        *,
        snapshot: WorkspaceSnapshot,
        rows: object,
        draft: Draft,
    ) -> None:
        del rows, draft
        service.db.add(snapshot)
        service.db.flush()
        assert service.db.get(WorkspaceSnapshot, snapshot.id) is not None
        raise RuntimeError("forced failure after snapshot flush")

    monkeypatch.setattr(
        UnifiedWorkspaceService,
        "_persist_snapshot_foundation",
        fail_after_snapshot_flush,
    )
    response = postgres_api.client.post(
        "/api/v2/unified-workspaces/manual",
        headers=postgres_api.headers,
        json={
            "name": "Atomic rollback workspace",
            "selections": [
                {"connector_id": "woocommerce:primary", "product_id": "101"}
            ],
        },
    )
    assert response.status_code == 500

    with postgres_api.sessions() as db:
        assert db.query(UnifiedWorkspace).count() == 0
        assert db.query(WorkspaceSnapshot).count() == 0
        assert db.query(SnapshotRow).count() == 0
        assert db.query(Draft).count() == 0


def test_postgresql_repeated_workspace_creation_keeps_snapshot_references_unique(
    postgres_api: PostgresApi,
) -> None:
    created = [
        _manual_request(postgres_api, name=f"Repeated workspace {index}")
        for index in range(3)
    ]
    workspace_ids = {str(item["id"]) for item in created}
    snapshot_ids = {
        str(item["snapshot"]["id"])  # type: ignore[index]
        for item in created
    }
    draft_ids = {
        str(item["draft"]["id"])  # type: ignore[index]
        for item in created
    }
    assert len(workspace_ids) == len(snapshot_ids) == len(draft_ids) == 3

    with postgres_api.sessions() as db:
        drafts = db.query(Draft).filter(Draft.id.in_(draft_ids)).all()
        assert len(drafts) == 3
        assert {item.workspace_id for item in drafts} == workspace_ids
        assert {item.snapshot_id for item in drafts} == snapshot_ids
        for draft in drafts:
            snapshot = db.get(WorkspaceSnapshot, draft.snapshot_id)
            assert snapshot is not None
            assert snapshot.workspace_id == draft.workspace_id


def test_postgresql_initial_draft_revision_preserves_snapshot_reference(
    postgres_api: PostgresApi,
) -> None:
    workspace = _manual_request(
        postgres_api,
        name="PostgreSQL revision workspace",
    )
    workspace_id = str(workspace["id"])
    snapshot_id = str(workspace["snapshot"]["id"])  # type: ignore[index]
    draft_id = str(workspace["draft"]["id"])  # type: ignore[index]
    grid_response = postgres_api.client.get(
        f"/api/v2/unified-workspaces/{workspace_id}/grid",
        headers=postgres_api.headers,
    )
    assert grid_response.status_code == 200, grid_response.text
    row = grid_response.json()["items"][0]

    revision_response = postgres_api.client.post(
        f"/api/v2/unified-workspaces/{workspace_id}/draft/revisions",
        headers=postgres_api.headers,
        json={
            "expected_version": 0,
            "metadata": {"source": "postgres-snapshot-order-regression"},
            "changes": [
                {
                    "canonical_product_id": row["canonicalProductId"],
                    "listing_id": row["listingId"],
                    "channel_id": row["channelId"],
                    "field": "price",
                    "target_value": "125",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert revision_response.status_code == 201, revision_response.text
    revision_id = revision_response.json()["id"]

    with postgres_api.sessions() as db:
        draft = db.get(Draft, draft_id)
        revision = db.get(DraftRevision, revision_id)
        assert draft is not None
        assert draft.current_revision_id == revision_id
        assert draft.snapshot_id == snapshot_id
        assert revision is not None
        assert revision.draft_id == draft_id
        assert revision.workspace_id == workspace_id
        assert revision.snapshot_id == snapshot_id
        assert db.get(WorkspaceSnapshot, revision.snapshot_id) is not None
