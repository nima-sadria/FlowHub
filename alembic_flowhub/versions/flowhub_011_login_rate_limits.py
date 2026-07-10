"""Add database-backed login rate-limit state.

Revision ID: FLOWHUB_011
Revises: FLOWHUB_010
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_011"
down_revision = "FLOWHUB_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "flowhub_login_rate_limits" not in tables:
        op.create_table(
            "flowhub_login_rate_limits",
            sa.Column("ip_address", sa.String(length=45), nullable=False),
            sa.Column("window_started_at", sa.DateTime(), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("ip_address"),
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "flowhub_login_rate_limits" in tables:
        op.drop_table("flowhub_login_rate_limits")
