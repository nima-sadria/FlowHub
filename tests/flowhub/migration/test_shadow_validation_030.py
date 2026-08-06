"""Focused migration checks for Shadow Validation persistence (C2)."""

from __future__ import annotations

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


def _upgrade_to_030(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sa.Engine:
    database_url = f"sqlite:///{(tmp_path / 'shadow-validation-030.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), "FLOWHUB_030")
    return sa.create_engine(database_url)


def test_flowhub_030_is_forward_only_and_builds_shadow_validation_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (ROOT / "alembic_flowhub/versions/flowhub_030_shadow_validation.py").read_text()
    assert 'revision = "FLOWHUB_030"' in source
    assert 'down_revision = "FLOWHUB_029"' in source
    assert "forward-only" in source

    engine = _upgrade_to_030(tmp_path, monkeypatch)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "sv_validation_windows",
            "sv_validation_window_heads",
            "sv_validation_window_events",
            "sv_shape_comparison_contracts",
            "sv_legacy_formula_captures",
            "sv_shadow_comparisons",
            "sv_validation_readiness_decisions",
        } <= tables

        check_constraints = {
            table_name: {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}
            for table_name in tables
            if table_name.startswith("sv_")
        }
        assert "ck_sv_window_event_reason" in check_constraints["sv_validation_window_events"]
        assert "ck_sv_window_event_head" in check_constraints["sv_validation_window_events"]
        assert "ck_sv_comparison_confidence" in check_constraints["sv_shadow_comparisons"]
        assert "ck_sv_comparison_reason_code" in check_constraints["sv_shadow_comparisons"]
        assert "ck_sv_readiness_state" in check_constraints["sv_validation_readiness_decisions"]
        assert "ck_sv_readiness_reason_code" in check_constraints["sv_validation_readiness_decisions"]
        assert "ck_sv_window_head_version" in check_constraints["sv_validation_window_heads"]

        indexes = {
            table_name: {index["name"] for index in inspector.get_indexes(table_name)}
            for table_name in tables
            if table_name.startswith("sv_")
        }
        assert "ix_sv_validation_windows_channel_id" in indexes["sv_validation_windows"]
        assert "ix_sv_window_event_validation_window_id" in indexes["sv_validation_window_events"]
        assert "ix_sv_shadow_comparisons_channel" in indexes["sv_shadow_comparisons"]
    finally:
        engine.dispose()


def test_shadow_validation_head_versioned_downgrade_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_to_030(tmp_path, monkeypatch)
    try:
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_029")
    finally:
        engine.dispose()
