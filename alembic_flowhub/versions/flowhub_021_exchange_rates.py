"""Add provider-independent exchange-rate storage and per-user selections."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_021"
down_revision = "FLOWHUB_020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fh_exchange_rate_providers",
        sa.Column("provider_id", sa.String(80), primary_key=True),
        sa.Column("provider_type", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_key_secret_reference", sa.String(255), nullable=True),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.Column("request_timeout", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("refreshes_per_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("daily_request_limit", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("reserved_request_count", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("status", sa.String(30), nullable=False, server_default="disabled"),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("request_count_date", sa.Date(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refresh_lock_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "fh_exchange_rate_definitions",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("provider_id", sa.String(80), sa.ForeignKey("fh_exchange_rate_providers.provider_id"), nullable=False),
        sa.Column("external_symbol", sa.String(80), nullable=False),
        sa.Column("canonical_code", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("display_name_fa", sa.String(180), nullable=False),
        sa.Column("classification", sa.String(80), nullable=False),
        sa.Column("side", sa.String(20), nullable=True),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("provider_id", "external_symbol", name="uq_fh_rate_provider_symbol"),
    )
    op.create_index("ix_fh_exchange_rate_definitions_provider_id", "fh_exchange_rate_definitions", ["provider_id"])
    op.create_table(
        "fh_exchange_rate_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("external_symbol", sa.String(80), nullable=False),
        sa.Column("canonical_code", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("display_name_fa", sa.String(180), nullable=False),
        sa.Column("value", sa.Numeric(28, 8), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("change", sa.Numeric(28, 8), nullable=True),
        sa.Column("provider_timestamp", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("raw_reference", sa.String(255), nullable=True),
        sa.UniqueConstraint("provider_id", "external_symbol", "provider_timestamp", name="uq_fh_rate_snapshot_version"),
    )
    op.create_index("ix_fh_exchange_rate_snapshots_provider_id", "fh_exchange_rate_snapshots", ["provider_id"])
    op.create_index("ix_fh_exchange_rate_snapshots_external_symbol", "fh_exchange_rate_snapshots", ["external_symbol"])
    op.create_index("ix_fh_exchange_rate_snapshots_fetched_at", "fh_exchange_rate_snapshots", ["fetched_at"])
    op.create_table(
        "fh_exchange_rate_selections",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("flowhub_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("external_symbol", sa.String(80), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "provider_id", "external_symbol", name="uq_fh_rate_selection_item"),
    )
    op.create_table(
        "fh_exchange_rate_fetch_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("diagnostics_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_fh_exchange_rate_fetch_runs_provider_id", "fh_exchange_rate_fetch_runs", ["provider_id"])
    op.execute(sa.text("INSERT INTO fh_exchange_rate_providers (provider_id, provider_type, display_name, enabled, api_key_secret_reference, base_url, request_timeout, refreshes_per_day, daily_request_limit, reserved_request_count, status, request_count, updated_at) VALUES ('navasan', 'navasan', 'Navasan', 0, 'exchange_rates.navasan.api_key', 'https://api.navasan.tech', 10, 1, 120, 10, 'disabled', 0, CURRENT_TIMESTAMP)"))
    definitions = [
        ("usd_sell", "USD_TEHRAN_SELL", "USD Tehran Sell", "فروش دلار تهران", "market", "sell"),
        ("usd_buy", "USD_TEHRAN_BUY", "USD Tehran Buy", "خرید دلار تهران", "market", "buy"),
        ("aed_sell", "AED_DUBAI_SELL", "AED Dubai Sell", "فروش درهم دبی", "market", "sell"),
        ("eur", "EUR_MARKET", "EUR Market", "یورو بازار", "market", None),
        ("gbp", "GBP_MARKET", "GBP Market", "پوند بازار", "market", None),
        ("cad", "CAD_MARKET", "CAD Market", "دلار کانادا", "market", None),
        ("aud", "AUD_MARKET", "AUD Market", "دلار استرالیا", "market", None),
        ("try", "TRY_MARKET", "TRY Market", "لیر ترکیه", "market", None),
        ("sekkeh", "GOLD_COIN_IMAMI", "Imami Coin", "سکه امامی", "gold", None),
        ("18ayar", "GOLD_18K", "18K Gold", "طلای ۱۸ عیار", "gold", None),
        ("usdt", "USDT", "USDT", "تتر", "crypto", None),
        ("btc", "BTC", "Bitcoin", "بیت‌کوین", "crypto", None),
        ("eth", "ETH", "Ethereum", "اتریوم", "crypto", None),
    ]
    for symbol, canonical, name, name_fa, classification, side in definitions:
        op.execute(sa.text("INSERT INTO fh_exchange_rate_definitions (id, provider_id, external_symbol, canonical_code, display_name, display_name_fa, classification, side, unit, active) VALUES (:id, 'navasan', :symbol, :canonical, :name, :name_fa, :classification, :side, 'IRR', 1)").bindparams(id=f"navasan:{symbol}", symbol=symbol, canonical=canonical, name=name, name_fa=name_fa, classification=classification, side=side))


def downgrade() -> None:
    op.drop_index("ix_fh_exchange_rate_fetch_runs_provider_id", table_name="fh_exchange_rate_fetch_runs")
    op.drop_table("fh_exchange_rate_fetch_runs")
    op.drop_table("fh_exchange_rate_selections")
    op.drop_index("ix_fh_exchange_rate_snapshots_fetched_at", table_name="fh_exchange_rate_snapshots")
    op.drop_index("ix_fh_exchange_rate_snapshots_external_symbol", table_name="fh_exchange_rate_snapshots")
    op.drop_index("ix_fh_exchange_rate_snapshots_provider_id", table_name="fh_exchange_rate_snapshots")
    op.drop_table("fh_exchange_rate_snapshots")
    op.drop_index("ix_fh_exchange_rate_definitions_provider_id", table_name="fh_exchange_rate_definitions")
    op.drop_table("fh_exchange_rate_definitions")
    op.drop_table("fh_exchange_rate_providers")
