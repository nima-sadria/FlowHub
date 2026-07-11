from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_docs_reference_current_migration_head_and_runner() -> None:
    release_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    migration_status = (ROOT / "docs" / "MIGRATION_STATUS.md").read_text(encoding="utf-8")
    order_sync = (ROOT / "docs" / "architecture" / "ORDER_SYNCHRONIZATION.md").read_text(encoding="utf-8")

    assert "FLOWHUB_015" in release_notes
    assert "FLOWHUB_013`" not in release_notes
    assert "FlowHub 1.0.0 migration head is **`FLOWHUB_015`**" in migration_status
    assert "python -m app.flowhub.orders.runner" in order_sync
    assert "source=__channel_lease__" in order_sync


def test_static_icon_index_is_tracked_asset_manifest_with_existing_svgs() -> None:
    index = ROOT / "static" / "icons" / "index.ts"
    assert index.exists()
    content = index.read_text(encoding="utf-8")
    referenced = set(re.findall(r'"./([^"]+\.svg)\?react"', content))
    assert referenced
    missing = [name for name in sorted(referenced) if not (ROOT / "static" / "icons" / name).exists()]
    assert missing == []
