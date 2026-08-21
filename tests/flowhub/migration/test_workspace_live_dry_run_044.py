"""Real-PostgreSQL safety checks for the Phase-B Dry Run migration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _postgres_url() -> str:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    parsed = sa.engine.make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or "test" not in (
        parsed.database or ""
    ).lower():
        pytest.fail("FLOWHUB_TEST_POSTGRES_URL must reference a local disposable test database")
    return url


@pytest.mark.postgres
def test_postgresql_043_to_044_creates_durable_live_dry_run_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FLOWHUB_044 is additive, repeatable, FK-backed and scope-immutable.

    The upgrade starts from the real FLOWHUB_043 schema.  A pre-existing
    sentinel is deliberately kept through the upgrade; migration does not
    backfill or reinterpret historical cache-only manifests as verified Dry
    Runs.
    """
    url = _postgres_url()
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        command.upgrade(_config(), "FLOWHUB_043")
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_users "
                    "(id, username, hashed_password, role, is_active, created_at) "
                    "VALUES (991, 'flowhub-044-history', 'unused', 'admin', true, CURRENT_TIMESTAMP)"
                )
            )

        command.upgrade(_config(), "FLOWHUB_044")
        # FlowHub migrations are forward-only but every upgrade is safe to
        # re-run through Alembic's normal already-at-head convention.
        command.upgrade(_config(), "FLOWHUB_044")

        inspector = sa.inspect(engine)
        assert {"uw_dry_runs", "uw_dry_run_scopes"}.issubset(
            set(inspector.get_table_names())
        )
        dry_run_fks = {item["referred_table"] for item in inspector.get_foreign_keys("uw_dry_runs")}
        scope_fks = {item["referred_table"] for item in inspector.get_foreign_keys("uw_dry_run_scopes")}
        manifest_fks = inspector.get_foreign_keys("uw_apply_manifests")
        assert {"uw_workspaces", "uw_workspace_snapshots", "uw_reviews", "flowhub_users"}.issubset(dry_run_fks)
        assert {"uw_dry_runs", "uw_review_items", "uw_listings", "uw_channels"}.issubset(scope_fks)
        assert any(
            item["name"] == "fk_uw_apply_manifests_dry_run"
            and item["referred_table"] == "uw_dry_runs"
            for item in manifest_fks
        )
        # Seed only durable evidence test rows.  FKs are temporarily disabled
        # solely for insertion because this migration test deliberately starts
        # at schema revision 043 rather than constructing an entire Workspace.
        # They are re-enabled before each assertion below.
        with engine.begin() as connection:
            connection.execute(sa.text("ALTER TABLE uw_dry_run_scopes DISABLE TRIGGER ALL"))
            connection.execute(
                sa.text(
                    "INSERT INTO uw_dry_run_scopes "
                    "(id, dry_run_id, review_item_id, listing_id, channel_id, disposition, "
                    "reason_code, expected_before_json, observed_live_json, live_fingerprint) "
                    "VALUES ('scope-044', 'missing-dry-run', 'missing-item', 'missing-listing', "
                    "'missing-channel', 'write', NULL, '{}'::jsonb, '{}'::jsonb, NULL)"
                )
            )
            connection.execute(sa.text("ALTER TABLE uw_dry_run_scopes ENABLE TRIGGER ALL"))
            connection.execute(sa.text("ALTER TABLE uw_apply_manifests DISABLE TRIGGER ALL"))
            connection.execute(
                sa.text(
                    "INSERT INTO uw_apply_manifests "
                    "(id, workspace_id, snapshot_id, draft_revision_id, review_id, selection_version, "
                    "selection_checksum, manifest_checksum, operation_count, channel_ids_json, "
                    "created_by_user_id, created_at) "
                    "VALUES ('historic-043-manifest', 'missing-workspace', 'missing-snapshot', "
                    "'missing-revision', 'missing-review', 1, repeat('a', 64), repeat('b', 64), "
                    "0, '[]'::jsonb, 991, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(sa.text("ALTER TABLE uw_apply_manifests ENABLE TRIGGER ALL"))

        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    sa.text("UPDATE uw_dry_run_scopes SET disposition = 'blocked' WHERE id = 'scope-044'")
                )
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as connection:
                connection.execute(sa.text("DELETE FROM uw_dry_run_scopes WHERE id = 'scope-044'"))
        # Disable only the historical-manifest immutability trigger.  The
        # newly added internal PostgreSQL FK trigger remains enabled and must
        # reject an invalid Dry Run reference.
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as connection:
                connection.execute(sa.text("ALTER TABLE uw_apply_manifests DISABLE TRIGGER USER"))
                connection.execute(
                    sa.text(
                        "UPDATE uw_apply_manifests SET dry_run_id = 'missing-dry-run' "
                        "WHERE id = 'historic-043-manifest'"
                    )
                )
        with engine.begin() as connection:
            connection.execute(sa.text("ALTER TABLE uw_apply_manifests ENABLE TRIGGER USER"))

        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT username FROM flowhub_users WHERE id = 991")
            ).scalar_one() == "flowhub-044-history"
            trigger_names = set(
                connection.execute(
                    sa.text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE tgrelid = 'uw_dry_run_scopes'::regclass AND NOT tgisinternal"
                    )
                ).scalars()
            )
            assert "uw_dry_run_scopes_immutable" in trigger_names
            assert connection.execute(
                sa.text(
                    "SELECT dry_run_id FROM uw_apply_manifests "
                    "WHERE id = 'historic-043-manifest'"
                )
            ).scalar_one() is None
    finally:
        engine.dispose()
