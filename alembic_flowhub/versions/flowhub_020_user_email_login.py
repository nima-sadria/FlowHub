"""Add per-user email identity for email-or-username login.

Revision ID: FLOWHUB_020
Revises: FLOWHUB_019

Existing installations stored the setup owner's email in flowhub_app_config
without linking it to flowhub_users. Backfill the first privileged account so
the email entered during setup immediately becomes a valid login identifier.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_020"
down_revision = "FLOWHUB_019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "flowhub_users",
        sa.Column("email", sa.String(length=320), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE flowhub_users
            SET email = (
                SELECT LOWER(TRIM(value))
                FROM flowhub_app_config
                WHERE key = 'admin.email'
            )
            WHERE id = (
                SELECT id
                FROM flowhub_users
                WHERE role IN ('owner', 'super_admin', 'admin')
                ORDER BY id ASC
                LIMIT 1
            )
            AND email IS NULL
            AND EXISTS (
                SELECT 1
                FROM flowhub_app_config
                WHERE key = 'admin.email'
                  AND value IS NOT NULL
                  AND TRIM(value) <> ''
            )
            """
        )
    )
    op.create_index(
        op.f("ix_flowhub_users_email"),
        "flowhub_users",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_flowhub_users_email"), table_name="flowhub_users")
    op.drop_column("flowhub_users", "email")
