"""FLOWHUB_007 - platform component implementation tables

Revision ID: FLOWHUB_007
Revises: FLOWHUB_006
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "FLOWHUB_007"
down_revision = "FLOWHUB_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ip_connector_diagnostics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correlation_id", sa.String(length=120), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_connector_diagnostics_connector_id", "ip_connector_diagnostics", ["connector_id"])

    op.create_table(
        "ip_connector_telemetry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("connector_type", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("transport", sa.String(length=60), nullable=False, server_default="internal"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms_p50", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms_p95", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rate_limit_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refresh_duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_connector_telemetry_connector_id", "ip_connector_telemetry", ["connector_id"])
    op.create_index("ix_ip_connector_telemetry_connector_type", "ip_connector_telemetry", ["connector_type"])

    op.create_table(
        "ip_webhook_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_type", sa.String(length=80), nullable=False),
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rejected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload_summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_webhook_events_connector_id", "ip_webhook_events", ["connector_id"])
    op.create_index("ix_ip_webhook_events_connector_type", "ip_webhook_events", ["connector_type"])

    op.create_table(
        "ip_polling_policies",
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="900"),
        sa.Column("jitter_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("connector_id"),
    )

    op.create_table(
        "logging_entries",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("component", sa.String(length=80), nullable=False),
        sa.Column("module", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("operation", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("user", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("connector", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("exception_summary", sa.Text(), nullable=True),
        sa.Column("structured_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in [
        "timestamp",
        "severity",
        "component",
        "module",
        "operation",
        "category",
        "correlation_id",
        "request_id",
        "user",
        "connector",
        "channel",
        "result",
    ]:
        op.create_index(f"ix_logging_entries_{column}", "logging_entries", [column])

    op.create_table(
        "logging_correlations",
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("correlation_id"),
    )
    op.create_table(
        "logging_request_traces",
        sa.Column("request_id", sa.String(length=120), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False),
        sa.Column("route", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("user", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=80), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_logging_request_traces_correlation_id", "logging_request_traces", ["correlation_id"])
    op.create_table(
        "logging_retention_policies",
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(length=160), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("category"),
    )
    op.create_table(
        "logging_export_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("requested_by", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="json"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("correlation_id", sa.String(length=120), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "logging_redaction_policy_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("logging_redaction_policy_versions")
    op.drop_table("logging_export_events")
    op.drop_table("logging_retention_policies")
    op.drop_table("logging_request_traces")
    op.drop_table("logging_correlations")
    op.drop_table("logging_entries")
    op.drop_table("ip_polling_policies")
    op.drop_table("ip_webhook_events")
    op.drop_table("ip_connector_telemetry")
    op.drop_table("ip_connector_diagnostics")
