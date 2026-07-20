from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_docs_reference_current_migration_head_and_runner() -> None:
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    migration_status = (ROOT / "docs" / "MIGRATION_STATUS.md").read_text(encoding="utf-8")
    order_sync = (ROOT / "docs" / "architecture" / "ORDER_SYNCHRONIZATION.md").read_text(encoding="utf-8")

    assert "FLOWHUB_019" in release_notes
    assert "FLOWHUB_013`" not in release_notes
    assert "The current FlowHub migration head is **`FLOWHUB_019`**" in migration_status
    assert "python -m app.flowhub.orders.runner" in order_sync
    assert "source=__channel_lease__" in order_sync


def test_postgres_lease_test_path_and_current_capability_docs() -> None:
    compose = (ROOT / "docker-compose.test.yml").read_text(encoding="utf-8")
    order_sync = (ROOT / "docs" / "architecture" / "ORDER_SYNCHRONIZATION.md").read_text(encoding="utf-8")
    integrations = (ROOT / "docs" / "architecture" / "BU5_INTEGRATIONS.md").read_text(encoding="utf-8")
    data_layer = (ROOT / "docs" / "architecture" / "DATA_LAYER_ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "postgres-test:" in compose
    assert "FLOWHUB_TEST_POSTGRES_URL" in order_sync
    assert "-m postgres" in order_sync
    assert "SnappShop and TapsiShop product writes are implemented" in integrations
    assert "Marketplace Order Synchronization Boundary" in data_layer


def test_security_and_integration_docs_match_atomic_marketplace_runtime() -> None:
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    integration = (ROOT / "docs" / "architecture" / "INTEGRATION_PLATFORM.md").read_text(encoding="utf-8")
    order_sync = (ROOT / "docs" / "architecture" / "ORDER_SYNCHRONIZATION.md").read_text(encoding="utf-8")

    assert "additional marketplace writes remain disabled or deferred" not in security
    assert "planned read-only Channel placeholders" not in integration
    assert "Marketplace order synchronization is scheduled" in integration
    assert "one receipt is the atomic unit" in order_sync
    assert "acknowledgement occurs only after" in order_sync


def test_static_icon_index_is_tracked_asset_manifest_with_existing_svgs() -> None:
    index = ROOT / "static" / "icons" / "index.ts"
    assert index.exists()
    content = index.read_text(encoding="utf-8")
    referenced = set(re.findall(r'"./([^"]+\.svg)\?react"', content))
    assert referenced
    missing = [name for name in sorted(referenced) if not (ROOT / "static" / "icons" / name).exists()]
    assert missing == []
