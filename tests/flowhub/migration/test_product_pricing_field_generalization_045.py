"""Real-PostgreSQL safety checks for the Product Pricing field-generalization migration."""

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
def test_postgresql_044_to_045_preserves_price_rows_and_allows_stock_status_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FLOWHUB_045 is additive/nullability-widening only: existing Price
    operation items survive unchanged (field defaults to 'price'), and the
    numeric columns become nullable so a Stock Status item (which has no
    numeric value at all) can be inserted using the new text columns.
    """
    url = _postgres_url()
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        command.upgrade(_config(), "FLOWHUB_044")
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_product_price_operations "
                    "(id, product_id, sku, product_name, status, version_token, created_by, "
                    "summary_json, created_at) "
                    "VALUES ('op-045', 'product-045', 'SKU-045', 'Pre-migration product', "
                    "'dry_run_ready', 'v1', 'tester', '{}'::jsonb, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_product_price_operation_items "
                    "(operation_id, channel_id, connector_type, channel_product_id, sku, "
                    "current_value, proposed_value, currency, unit, outbound_value, outbound_unit, "
                    "stale_token, status, validation_state, result_json) "
                    "VALUES ('op-045', 'woocommerce:primary', 'woocommerce', '501', 'SKU-045', "
                    "100, 120, 'EUR', 'EUR', 120, 'store currency', 'token-045', 'pending', "
                    "'valid', '{}'::jsonb)"
                )
            )

        command.upgrade(_config(), "FLOWHUB_045")
        # Migrations are forward-only but every upgrade is safe to re-run
        # through Alembic's normal already-at-head convention.
        command.upgrade(_config(), "FLOWHUB_045")

        with engine.connect() as connection:
            price_row = connection.execute(
                sa.text(
                    "SELECT field, current_value, proposed_value "
                    "FROM flowhub_product_price_operation_items WHERE operation_id = 'op-045'"
                )
            ).one()
            assert price_row.field == "price"
            assert price_row.current_value == 100
            assert price_row.proposed_value == 120

        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_product_price_operation_items "
                    "(operation_id, channel_id, connector_type, channel_product_id, sku, field, "
                    "current_status_value, proposed_status_value, currency, unit, outbound_unit, "
                    "stale_token, status, validation_state, result_json) "
                    "VALUES ('op-045', 'woocommerce:primary', 'woocommerce', '501', 'SKU-045', "
                    "'status', 'instock', 'outofstock', '', '', '', 'token-045-status', 'pending', "
                    "'valid', '{}'::jsonb)"
                )
            )

        with engine.connect() as connection:
            status_row = connection.execute(
                sa.text(
                    "SELECT current_value, proposed_value, current_status_value, proposed_status_value "
                    "FROM flowhub_product_price_operation_items WHERE field = 'status'"
                )
            ).one()
            assert status_row.current_value is None
            assert status_row.proposed_value is None
            assert status_row.current_status_value == "instock"
            assert status_row.proposed_status_value == "outofstock"
    finally:
        engine.dispose()
