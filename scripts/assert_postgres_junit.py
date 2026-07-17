"""Fail CI when the PostgreSQL safety manifest is empty, skipped, or incomplete."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REQUIRED_016_TESTS = (
    "test_postgresql_immutability_and_foreign_keys",
    "test_postgresql_upgrade_from_015_preserves_sentinel",
    "test_postgresql_global_lock_uniqueness_under_concurrency",
)
REQUIRED_017_TESTS = (
    "test_flowhub_017_is_additive_frozen_and_forward_only",
    "test_flowhub_017_backfills_profiles_preserves_sentinel_and_enforces_immutability",
    "test_flowhub_017_repairs_legacy_016",
    "test_flowhub_017_repairs_legacy_business_reference_inventory",
    "test_flowhub_017_fails_with_precise_orphan_diagnostic",
)
REQUIRED_ORDER_TESTS = (
    "test_concurrent_acquisition_has_one_winner_and_loser_cannot_advance",
    "test_different_channels_acquire_concurrently",
)
REQUIRED_CRASH_TESTS = (
    "test_hard_process_provider_commit_recovers_without_duplicate_write",
    "test_hard_process_before_dispatch_is_recoverable_without_provider_write",
)
REQUIRED_018_TESTS = (
    "test_postgresql_018_fresh_schema_foreign_keys_and_immutability",
    "test_postgresql_017_to_018_preserves_v12_sentinel",
)
REQUIRED_019_TESTS = (
    "test_flowhub_019_is_explicit_additive_and_forward_only",
    "test_flowhub_019_offline_sql_contains_complete_trigger_ddl",
    "test_runtime_sqlite_engine_enables_declared_foreign_keys",
    "test_sqlite_018_to_019_preserves_mapping_and_enforces_rule_immutability",
    "test_sqlite_migrated_schema_allows_service_to_finalize_scan",
    "test_sqlite_019_tables_match_source_workspace_metadata",
    "test_postgresql_019_foreign_keys_immutability_and_018_preservation",
)
REQUIRED_WORKSPACE_PERSISTENCE_TESTS = (
    "test_postgresql_manual_workspace_persists_snapshot_before_draft",
    "test_postgresql_catalog_workspace_persists_snapshot_before_draft",
    "test_postgresql_workspace_creation_rolls_back_after_snapshot_flush_failure",
    "test_postgresql_repeated_workspace_creation_keeps_snapshot_references_unique",
)


def main() -> int:
    report = Path(sys.argv[1] if len(sys.argv) > 1 else "postgres-junit.xml")
    group = sys.argv[2] if len(sys.argv) > 2 else "migration"
    required_tests = {
        "016": REQUIRED_016_TESTS,
        "016-immutability": REQUIRED_016_TESTS[:1],
        "016-upgrade": REQUIRED_016_TESTS[1:2],
        "016-lock": REQUIRED_016_TESTS[2:],
        "017": REQUIRED_017_TESTS,
        "018": REQUIRED_018_TESTS,
        "019": REQUIRED_019_TESTS,
        "workspace-persistence": REQUIRED_WORKSPACE_PERSISTENCE_TESTS,
        "orders": REQUIRED_ORDER_TESTS,
        "crash": REQUIRED_CRASH_TESTS,
    }.get(group, REQUIRED_017_TESTS)
    root = ET.parse(report).getroot()
    cases = list(root.iter("testcase"))
    skipped = [case for case in cases if case.find("skipped") is not None]
    failed = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
    names = "\n".join(f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}" for case in cases)
    missing = [needle for needle in required_tests if needle not in names]
    print(f"postgres_manifest tests={len(cases)} passed={len(cases)-len(skipped)-len(failed)} failed={len(failed)} skipped={len(skipped)}")
    if not cases:
        print("ERROR: PostgreSQL safety manifest collected zero tests")
        return 1
    if skipped:
        print("ERROR: PostgreSQL safety tests were skipped:")
        for case in skipped:
            print(f"  {case.attrib.get('classname')}::{case.attrib.get('name')}")
        return 1
    if missing:
        print("ERROR: mandatory PostgreSQL tests were not executed:")
        for item in missing:
            print(f"  {item}")
        return 1
    if failed:
        print("ERROR: PostgreSQL safety tests failed")
        for case in failed:
            detail = (case.findtext("failure") or case.findtext("error") or "").strip()
            message = f"{case.attrib.get('classname')}::{case.attrib.get('name')}: {detail}".replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=PostgreSQL test failure::{message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
