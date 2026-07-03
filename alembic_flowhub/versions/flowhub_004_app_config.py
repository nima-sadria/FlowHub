"""FLOWHUB_004 - create flowhub_app_config table

Runtime configuration key-value store for all settings collected by the
Setup Wizard. Bootstrap-only values (database URL, secrets) remain in
.env; everything else (server profile, integration credentials,
timezone, currency) is stored here and editable from the Settings UI.

Revision ID: FLOWHUB_004
Revises: FLOWHUB_003
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "FLOWHUB_004"
down_revision = "FLOWHUB_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flowhub_app_config",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(length=150), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    # If flowhub_users already has rows (pre-BU4 upgrade), mark setup as complete
    # so existing installations are not forced through the wizard again.
    op.execute(
        """
        INSERT INTO flowhub_app_config (key, value, updated_by)
        SELECT
            'setup.completed',
            CASE WHEN (SELECT COUNT(*) FROM flowhub_users) > 0 THEN 'true' ELSE 'false' END,
            'migration'
        """
    )


def downgrade() -> None:
    op.drop_table("flowhub_app_config")
