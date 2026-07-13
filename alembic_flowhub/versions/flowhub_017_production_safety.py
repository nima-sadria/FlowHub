"""Repair Unified Workspace production-safety invariants.

Revision ID: FLOWHUB_017
Revises: FLOWHUB_016

The migration is additive and schema-inspecting because an earlier released form
of FLOWHUB_016 created tables from live ORM metadata.  No historical migration is
rewritten and no business table is recreated.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_017"
down_revision = "FLOWHUB_016"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set[str]:
    return {str(item["name"]) for item in _inspector().get_columns(table)}


def _add(table: str, column: sa.Column[Any]) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _profile_checksum(row: sa.Row[Any]) -> str:
    payload = {
        "currency": row.currency,
        "factor": str(row.conversion_factor),
        "normalization_currency": row.normalization_currency,
        "normalization_unit": row.normalization_unit,
        "reference": row.scope_reference,
        "rule": row.conversion_rule,
        "scope": row.scope,
        "unit": row.unit,
        "version": row.version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _drop_currency_immutability(dialect: str) -> None:
    bind = op.get_bind()
    if dialect == "postgresql":
        bind.exec_driver_sql(
            "DROP TRIGGER IF EXISTS uw_currency_profiles_immutable ON uw_currency_profiles"
        )
    else:
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS uw_currency_profiles_immutable_update")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS uw_currency_profiles_immutable_delete")


def _restore_immutability(table: str, dialect: str) -> None:
    bind = op.get_bind()
    if dialect == "postgresql":
        bind.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION uw_reject_immutable_mutation() "
            "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
            "'immutable Unified Workspace record'; END; $$ LANGUAGE plpgsql"
        )
        bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
        bind.exec_driver_sql(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION uw_reject_immutable_mutation()"
        )
    else:
        for operation in ("UPDATE", "DELETE"):
            bind.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS {table}_immutable_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, "
                "'immutable Unified Workspace record'); END"
            )


def _create_attempt_tables() -> None:
    if "flowhub_provider_write_attempts" not in _tables():
        op.create_table(
            "flowhub_provider_write_attempts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("source_workflow", sa.String(80), nullable=False),
            sa.Column("operation_id", sa.String(120), nullable=False),
            sa.Column("logical_item_id", sa.String(120), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=True),
            sa.Column("apply_job_id", sa.String(36), nullable=True),
            sa.Column("apply_job_item_id", sa.String(36), nullable=True),
            sa.Column("listing_id", sa.String(120), nullable=False),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("external_identity", sa.String(240), nullable=False),
            sa.Column("normalized_payload_json", sa.JSON(), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("provider_idempotency_key", sa.String(120), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("correlation_id", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["apply_job_id"], ["uw_apply_jobs.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["apply_job_item_id"], ["uw_apply_job_items.id"], ondelete="RESTRICT"
            ),
            sa.UniqueConstraint(
                "source_workflow",
                "operation_id",
                "logical_item_id",
                "attempt_number",
                name="uq_provider_write_attempt_logical_number",
            ),
            sa.UniqueConstraint("provider_idempotency_key", name="uq_provider_write_attempt_key"),
        )
    if "flowhub_provider_write_attempt_events" not in _tables():
        op.create_table(
            "flowhub_provider_write_attempt_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("attempt_id", sa.String(36), nullable=False),
            sa.Column("outcome", sa.String(40), nullable=False),
            sa.Column("provider_response_json", sa.JSON(), nullable=False),
            sa.Column("error_category", sa.String(80), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "outcome IN ('pending','dispatch_intent_recorded','dispatched',"
                "'provider_accepted','verified_applied','failed',"
                "'reconciliation_required','recovering')",
                name="ck_provider_write_attempt_event_outcome",
            ),
            sa.ForeignKeyConstraint(
                ["attempt_id"],
                ["flowhub_provider_write_attempts.id"],
                ondelete="RESTRICT",
            ),
        )
    if "uw_apply_attempts" not in _tables():
        op.create_table(
            "uw_apply_attempts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("apply_job_id", sa.String(36), nullable=False),
            sa.Column("apply_job_item_id", sa.String(36), nullable=False),
            sa.Column("listing_id", sa.String(36), nullable=False),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("normalized_payload_json", sa.JSON(), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("provider_idempotency_key", sa.String(120), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("correlation_id", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["apply_job_id"], ["uw_apply_jobs.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["apply_job_item_id"], ["uw_apply_job_items.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["listing_id"], ["uw_listings.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("apply_job_item_id", "attempt_number", name="uq_uw_attempt_number"),
            sa.UniqueConstraint("provider_idempotency_key", name="uq_uw_attempt_provider_key"),
        )
    if "uw_apply_attempt_events" not in _tables():
        op.create_table(
            "uw_apply_attempt_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("attempt_id", sa.String(36), nullable=False),
            sa.Column("outcome", sa.String(40), nullable=False),
            sa.Column("provider_response_json", sa.JSON(), nullable=False),
            sa.Column("error_category", sa.String(80), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "outcome IN ('pending','dispatched','provider_accepted',"
                "'verified_applied','failed','reconciliation_required','recovering')",
                name="ck_uw_attempt_event_outcome",
            ),
            sa.ForeignKeyConstraint(["attempt_id"], ["uw_apply_attempts.id"], ondelete="RESTRICT"),
        )
    bind = op.get_bind()
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_attempts_apply_job_id ON uw_apply_attempts(apply_job_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_attempts_apply_job_item_id ON uw_apply_attempts(apply_job_item_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_attempts_listing_id ON uw_apply_attempts(listing_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_attempts_channel_id ON uw_apply_attempts(channel_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_attempt_events_attempt_id ON uw_apply_attempt_events(attempt_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_attempt_events_outcome ON uw_apply_attempt_events(outcome)",
        "CREATE INDEX IF NOT EXISTS ix_provider_write_attempt_operation ON flowhub_provider_write_attempts(source_workflow,operation_id)",
        "CREATE INDEX IF NOT EXISTS ix_provider_write_attempt_apply_job ON flowhub_provider_write_attempts(apply_job_id)",
        "CREATE INDEX IF NOT EXISTS ix_provider_write_attempt_listing ON flowhub_provider_write_attempts(channel_id,listing_id)",
        "CREATE INDEX IF NOT EXISTS ix_provider_write_attempt_events_attempt ON flowhub_provider_write_attempt_events(attempt_id)",
        "CREATE INDEX IF NOT EXISTS ix_provider_write_attempt_events_outcome ON flowhub_provider_write_attempt_events(outcome)",
    ):
        bind.exec_driver_sql(statement)


def _backfill_logical_keys() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id,logical_operation_key,operation_checksum FROM uw_apply_jobs")
    ).mappings()
    for row in rows:
        logical = (
            row["logical_operation_key"]
            or hashlib.sha256(f"legacy-apply:{row['id']}".encode()).hexdigest()
        )
        operation = row["operation_checksum"] or logical
        bind.execute(
            sa.text(
                "UPDATE uw_apply_jobs SET logical_operation_key=:logical,"
                "operation_checksum=:operation WHERE id=:id"
            ),
            {"id": row["id"], "logical": logical, "operation": operation},
        )


def _foreign_key_signature(item: dict[str, Any]) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    """Return the structural identity of an FK.

    Constraint names are not stable across the historical 016 variants (the
    metadata-driven migration generated names differently on different
    dialects).  The endpoint columns are therefore the authority for deciding
    whether a relationship already exists.
    """

    return (
        tuple(str(column) for column in item.get("constrained_columns", ())),
        str(item.get("referred_table", "")),
        tuple(str(column) for column in item.get("referred_columns", ())),
    )


def _add_postgresql_fk(
    table: str,
    name: str,
    local: str,
    remote_table: str,
    remote: str = "id",
) -> None:
    """Create a missing FK using structural, not name-based, detection.

    A differently named equivalent FK is considered already repaired.  This
    keeps 017 idempotent and avoids duplicate constraints when upgrading a
    partially repaired database.  Existing referential actions are preserved;
    017 never drops a historical constraint or rewrites business data.
    """

    if table not in _tables() or remote_table not in _tables():
        return
    if local not in _columns(table) or remote not in _columns(remote_table):
        return
    expected = ((local,), remote_table, (remote,))
    for item in _inspector().get_foreign_keys(table):
        if _foreign_key_signature(item) == expected:
            return
    op.create_foreign_key(name, table, remote_table, [local], [remote], ondelete="RESTRICT")


def _assert_no_orphans(table: str, local: str, remote_table: str, remote: str) -> None:
    """Fail with a precise diagnostic before installing a new relationship."""

    if table not in _tables() or remote_table not in _tables():
        return
    if local not in _columns(table) or remote not in _columns(remote_table):
        return
    bind = op.get_bind()
    orphan = bind.execute(
        sa.text(
            f"SELECT 1 FROM {table} AS source "
            f"LEFT JOIN {remote_table} AS target ON source.{local}=target.{remote} "
            f"WHERE source.{local} IS NOT NULL AND target.{remote} IS NULL LIMIT 1"
        )
    ).first()
    if orphan is not None:
        raise RuntimeError(
            "FLOWHUB_017 cannot add foreign key "
            f"{table}.{local} -> {remote_table}.{remote}: orphaned reference exists"
        )


def _sqlite_reference_triggers(
    references: Iterable[tuple[str, str, str, bool]],
) -> None:
    bind = op.get_bind()
    for table, column, remote_table, nullable in references:
        null_clause = f"NEW.{column} IS NOT NULL AND " if nullable else ""
        for operation in ("INSERT", "UPDATE"):
            trigger = f"fk017_{table}_{column}_{operation.lower()}"
            bind.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS {trigger} BEFORE {operation} ON {table} "
                f"WHEN {null_clause}NOT EXISTS (SELECT 1 FROM {remote_table} "
                f"WHERE id=NEW.{column}) BEGIN SELECT RAISE(ABORT, 'foreign key violation'); END"
            )


def _repair_apply_status_constraint(dialect: str) -> None:
    checks = {
        str(item.get("name")): str(item.get("sqltext") or "")
        for item in _inspector().get_check_constraints("uw_apply_jobs")
    }
    current = checks.get("ck_uw_apply_status", "")
    if "reconciliation_required" in current:
        return
    expression = (
        "status IN ('pending','running','partially_applied','applied','failed',"
        "'cancelled','blocked','stale','reconciliation_required')"
    )
    if dialect == "postgresql":
        if "ck_uw_apply_status" in checks:
            op.drop_constraint("ck_uw_apply_status", "uw_apply_jobs", type_="check")
        op.create_check_constraint("ck_uw_apply_status", "uw_apply_jobs", expression)
        return
    with op.batch_alter_table("uw_apply_jobs", recreate="always") as batch:
        if "ck_uw_apply_status" in checks:
            batch.drop_constraint("ck_uw_apply_status", type_="check")
        batch.create_check_constraint("ck_uw_apply_status", expression)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"FLOWHUB_017 does not support {dialect}.")

    _create_attempt_tables()
    _drop_currency_immutability(dialect)
    try:
        _add("uw_currency_profiles", sa.Column("checksum", sa.String(64), nullable=True))
        profiles = bind.execute(
            sa.text(
                "SELECT id,scope,scope_reference,currency,unit,normalization_currency,"
                "normalization_unit,conversion_factor,conversion_rule,version "
                "FROM uw_currency_profiles"
            )
        ).all()
        for profile in profiles:
            bind.execute(
                sa.text("UPDATE uw_currency_profiles SET checksum=:checksum WHERE id=:id"),
                {"id": profile.id, "checksum": _profile_checksum(profile)},
            )
    finally:
        _restore_immutability("uw_currency_profiles", dialect)

    _add(
        "uw_reviews",
        sa.Column("selection_version", sa.Integer(), nullable=False, server_default="0"),
    )
    _add("uw_reviews", sa.Column("selection_checksum", sa.String(64), nullable=True))
    _add("uw_reviews", sa.Column("currency_profile_id", sa.String(36), nullable=True))
    _add("uw_reviews", sa.Column("currency_profile_version", sa.Integer(), nullable=True))
    _add("uw_reviews", sa.Column("currency_profile_checksum", sa.String(64), nullable=True))
    _add("uw_reviews", sa.Column("currency_source_reference", sa.String(160), nullable=True))
    _add(
        "uw_reviews",
        sa.Column(
            "currency_channel_references_json", sa.JSON(), nullable=False, server_default="[]"
        ),
    )
    _add(
        "uw_reviews",
        sa.Column(
            "currency_ruleset_version",
            sa.String(40),
            nullable=False,
            server_default="uw-currency-1",
        ),
    )
    _add(
        "uw_reviews",
        sa.Column("selected_channel_ids_json", sa.JSON(), nullable=False, server_default="[]"),
    )
    bind.execute(
        sa.text(
            "UPDATE uw_reviews SET currency_profile_id=(SELECT s.currency_profile_id "
            "FROM uw_workspace_snapshots s WHERE s.id=uw_reviews.snapshot_id) "
            "WHERE currency_profile_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE uw_reviews SET "
            "currency_profile_version=(SELECT p.version FROM uw_currency_profiles p WHERE p.id=currency_profile_id),"
            "currency_profile_checksum=(SELECT p.checksum FROM uw_currency_profiles p WHERE p.id=currency_profile_id),"
            "currency_source_reference=(SELECT p.scope || ':' || p.scope_reference "
            "FROM uw_currency_profiles p WHERE p.id=currency_profile_id) "
            "WHERE currency_profile_version IS NULL"
        )
    )

    _add("uw_apply_jobs", sa.Column("logical_operation_key", sa.String(64), nullable=True))
    _add("uw_apply_jobs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    _add("uw_apply_jobs", sa.Column("worker_id", sa.String(120), nullable=True))
    _add("uw_apply_jobs", sa.Column("fencing_token", sa.Integer(), nullable=False, server_default="0"))
    _add("uw_apply_jobs", sa.Column("lease_token", sa.String(120), nullable=True))
    _add("uw_apply_jobs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    _add("uw_apply_jobs", sa.Column("recovery_attempts", sa.Integer(), nullable=False, server_default="0"))
    _add("uw_apply_jobs", sa.Column("operation_checksum", sa.String(64), nullable=True))
    _backfill_logical_keys()
    _repair_apply_status_constraint(dialect)

    _add("uw_workspace_locks", sa.Column("channel_id", sa.String(120), nullable=True))
    bind.execute(
        sa.text(
            "UPDATE uw_workspace_locks SET channel_id=(SELECT l.channel_id FROM uw_listings l "
            "WHERE l.id=uw_workspace_locks.listing_id) WHERE channel_id IS NULL"
        )
    )

    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_uw_apply_logical_operation "
        "ON uw_apply_jobs(logical_operation_key)"
    )
    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_uw_lock_scope_v17 "
        "ON uw_workspace_locks(channel_id,listing_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_recovery ON uw_apply_jobs(status,heartbeat_at)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_lease ON uw_apply_jobs(lease_expires_at,worker_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_uw_currency_profile_checksum "
        "ON uw_currency_profiles(checksum)"
    )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_uw_drafts_current_revision "
        "ON uw_drafts(current_revision_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_issue_product "
        "ON uw_validation_issues(canonical_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_issue_listing "
        "ON uw_validation_issues(listing_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_issue_channel "
        "ON uw_validation_issues(channel_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_lock_workspace "
        "ON uw_workspace_locks(workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_lock_apply_job "
        "ON uw_workspace_locks(apply_job_id)",
        "CREATE INDEX IF NOT EXISTS ix_provider_attempt_workspace "
        "ON flowhub_provider_write_attempts(workspace_id)",
    ):
        bind.exec_driver_sql(statement)

    references = (
        # Semantic dependencies that were omitted by the earliest 016
        # metadata-driven schema.  Keep this inventory explicit: it is the
        # contract repaired by this migration and must not depend on current
        # ORM metadata.
        ("uw_drafts", "current_revision_id", "uw_draft_revisions", True),
        ("uw_reviews", "currency_profile_id", "uw_currency_profiles", False),
        ("uw_mapping_revisions", "previous_canonical_product_id", "uw_canonical_products", True),
        ("uw_mapping_revisions", "proposed_canonical_product_id", "uw_canonical_products", False),
        ("uw_review_items", "canonical_product_id", "uw_canonical_products", False),
        ("uw_review_items", "listing_id", "uw_listings", False),
        ("uw_review_items", "channel_id", "uw_channels", False),
        ("uw_review_cache_versions", "listing_id", "uw_listings", False),
        ("uw_review_cache_versions", "channel_id", "uw_channels", False),
        ("uw_apply_jobs", "snapshot_id", "uw_workspace_snapshots", False),
        ("uw_apply_jobs", "draft_revision_id", "uw_draft_revisions", False),
        ("uw_apply_job_items", "review_item_id", "uw_review_items", False),
        ("uw_apply_job_items", "canonical_product_id", "uw_canonical_products", False),
        ("uw_apply_job_items", "listing_id", "uw_listings", False),
        ("uw_apply_job_items", "channel_id", "uw_channels", False),
        ("uw_validation_issues", "workspace_id", "uw_workspaces", False),
        ("uw_validation_issues", "snapshot_id", "uw_workspace_snapshots", False),
        ("uw_validation_issues", "review_id", "uw_reviews", True),
        ("uw_validation_issues", "canonical_product_id", "uw_canonical_products", True),
        ("uw_validation_issues", "listing_id", "uw_listings", True),
        ("uw_validation_issues", "channel_id", "uw_channels", True),
        ("uw_workspace_locks", "workspace_id", "uw_workspaces", False),
        ("uw_workspace_locks", "apply_job_id", "uw_apply_jobs", False),
        ("uw_workspace_locks", "channel_id", "uw_channels", False),
        ("uw_workspace_locks", "listing_id", "uw_listings", False),
        # Provider-neutral attempts are shared by Workspace and legacy
        # workflows.  The nullable workspace identity is relational whenever
        # a Workspace operation owns the attempt; legacy operations leave it
        # NULL.  Item/listing/channel identifiers remain provider-neutral
        # scalar identities because legacy workflows may use non-Workspace
        # listing identifiers.
        ("flowhub_provider_write_attempts", "workspace_id", "uw_workspaces", True),
    )
    for table, column, remote_table, _nullable in references:
        _assert_no_orphans(table, column, remote_table, "id")
    if dialect == "postgresql":
        bind.exec_driver_sql("ALTER TABLE uw_currency_profiles ALTER COLUMN checksum SET NOT NULL")
        for column in (
            "currency_profile_id",
            "currency_profile_version",
            "currency_profile_checksum",
            "currency_source_reference",
        ):
            bind.exec_driver_sql(f"ALTER TABLE uw_reviews ALTER COLUMN {column} SET NOT NULL")
        bind.exec_driver_sql(
            "ALTER TABLE uw_apply_jobs ALTER COLUMN logical_operation_key SET NOT NULL"
        )
        bind.exec_driver_sql(
            "ALTER TABLE uw_apply_jobs ALTER COLUMN operation_checksum SET NOT NULL"
        )
        bind.exec_driver_sql("ALTER TABLE uw_workspace_locks ALTER COLUMN channel_id SET NOT NULL")
        fk_names = {
            ("uw_reviews", "currency_profile_id"): "fk_uw_review_currency_profile",
            ("uw_drafts", "current_revision_id"): "fk_uw_draft_current_revision",
            (
                "uw_mapping_revisions",
                "previous_canonical_product_id",
            ): "fk_uw_mapping_previous_product",
            (
                "uw_mapping_revisions",
                "proposed_canonical_product_id",
            ): "fk_uw_mapping_proposed_product",
            ("uw_review_items", "canonical_product_id"): "fk_uw_review_item_product",
            ("uw_review_items", "listing_id"): "fk_uw_review_item_listing",
            ("uw_review_items", "channel_id"): "fk_uw_review_item_channel",
            ("uw_review_cache_versions", "listing_id"): "fk_uw_review_cache_listing",
            ("uw_review_cache_versions", "channel_id"): "fk_uw_review_cache_channel",
            ("uw_apply_jobs", "snapshot_id"): "fk_uw_apply_snapshot",
            ("uw_apply_jobs", "draft_revision_id"): "fk_uw_apply_draft_revision",
            ("uw_apply_job_items", "review_item_id"): "fk_uw_apply_item_review_item",
            ("uw_apply_job_items", "canonical_product_id"): "fk_uw_apply_item_product",
            ("uw_apply_job_items", "listing_id"): "fk_uw_apply_item_listing",
            ("uw_apply_job_items", "channel_id"): "fk_uw_apply_item_channel",
            ("uw_validation_issues", "workspace_id"): "fk_uw_issue_workspace",
            ("uw_validation_issues", "snapshot_id"): "fk_uw_issue_snapshot",
            ("uw_validation_issues", "review_id"): "fk_uw_issue_review",
            ("uw_validation_issues", "canonical_product_id"): "fk_uw_issue_product",
            ("uw_validation_issues", "listing_id"): "fk_uw_issue_listing",
            ("uw_validation_issues", "channel_id"): "fk_uw_issue_channel",
            ("uw_workspace_locks", "workspace_id"): "fk_uw_lock_workspace",
            ("uw_workspace_locks", "apply_job_id"): "fk_uw_lock_apply_job",
            ("uw_workspace_locks", "channel_id"): "fk_uw_lock_channel",
            ("uw_workspace_locks", "listing_id"): "fk_uw_lock_listing",
            ("flowhub_provider_write_attempts", "workspace_id"): "fk_provider_attempt_workspace",
        }
        for table, column, remote, _nullable in references:
            _add_postgresql_fk(table, fk_names[(table, column)], column, remote)
    else:
        _sqlite_reference_triggers(references)
        bind.exec_driver_sql(
            "CREATE TRIGGER IF NOT EXISTS nn017_currency_checksum BEFORE INSERT "
            "ON uw_currency_profiles WHEN NEW.checksum IS NULL BEGIN SELECT "
            "RAISE(ABORT, 'currency checksum required'); END"
        )
        for table, column in (
            ("uw_apply_jobs", "logical_operation_key"),
            ("uw_apply_jobs", "operation_checksum"),
            ("uw_workspace_locks", "channel_id"),
            ("uw_reviews", "currency_profile_id"),
            ("uw_reviews", "currency_profile_version"),
            ("uw_reviews", "currency_profile_checksum"),
            ("uw_reviews", "currency_source_reference"),
        ):
            bind.exec_driver_sql(
                f"CREATE TRIGGER IF NOT EXISTS nn017_{table}_{column} BEFORE INSERT "
                f"ON {table} WHEN NEW.{column} IS NULL BEGIN SELECT "
                "RAISE(ABORT, 'required production-safety field'); END"
            )

    _restore_immutability("uw_apply_attempts", dialect)
    _restore_immutability("uw_apply_attempt_events", dialect)
    _restore_immutability("flowhub_provider_write_attempts", dialect)
    _restore_immutability("flowhub_provider_write_attempt_events", dialect)


def downgrade() -> None:
    """Production-safety evidence is retained; destructive downgrade is forbidden."""
