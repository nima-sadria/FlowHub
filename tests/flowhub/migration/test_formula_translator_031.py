"""Focused migration checks for Formula Translator persistence schema (D2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.flowhub.formula_translator.registry import FORMULA_SHAPE_REGISTRY
from app.flowhub.formula_translator.registry import (
    FORMULA_SHAPE_REGISTRY_CHECKSUM,
    FORMULA_SHAPE_REGISTRY_VERSION,
)

ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _upgrade_to_031(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> sa.Engine:
    database_url = f"sqlite:///{(tmp_path / 'formula-translator-031.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), "FLOWHUB_031")
    return sa.create_engine(database_url)


def test_flowhub_031_is_forward_only_and_builds_formula_translator_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (ROOT / "alembic_flowhub/versions/flowhub_031_formula_translator.py").read_text()
    assert 'revision = "FLOWHUB_031"' in source
    assert 'down_revision = "FLOWHUB_030"' in source
    assert "forward-only" in source

    engine = _upgrade_to_031(tmp_path, monkeypatch)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "ft_formula_shape_registry",
            "ft_formula_translation_results",
            "ft_formula_translation_quarantine",
        } <= tables

        constraints = {
            table_name: {constraint["name"] for constraint in inspector.get_check_constraints(table_name)}
            for table_name in (
                "ft_formula_shape_registry",
                "ft_formula_translation_results",
                "ft_formula_translation_quarantine",
            )
        }
        assert "ck_ft_shape_registry_translation_status" in constraints["ft_formula_shape_registry"]
        assert "ck_ft_shape_registry_reason_code" in constraints["ft_formula_shape_registry"]
        assert "ck_ft_translation_status" in constraints["ft_formula_translation_results"]
        assert "ck_ft_translation_reason_code" in constraints["ft_formula_translation_results"]
        assert "ck_ft_quarantine_reason_code" in constraints["ft_formula_translation_quarantine"]

        registry_rows = {}
        with engine.connect() as connection:
            query = sa.text(
                "SELECT shape_id, translation_status, default_reason_code, "
                "is_price_target, formula_cell_count, topology_hint, notes, "
                "registry_version, registry_checksum "
                "FROM ft_formula_shape_registry"
            )
            for row in connection.execute(query).mappings():
                registry_rows[row["shape_id"]] = row
        assert len(registry_rows) == 13

        status_counts = {}
        with engine.connect() as connection:
            counts_query = sa.text(
                "SELECT translation_status, COUNT(1) AS count "
                "FROM ft_formula_shape_registry "
                "GROUP BY translation_status"
            )
            for row in connection.execute(counts_query).mappings():
                status_counts[row["translation_status"]] = int(row["count"])

        assert status_counts == {
            "translated": 7,
            "review_required": 1,
            "unsupported": 1,
            "quarantined": 4,
        }

        expected = {
            shape.shape_id: {
                "translation_status": shape.translation_status.value,
                "default_reason_code": shape.default_reason_code.value,
                "is_price_target": shape.is_price_target,
                "formula_cell_count": shape.formula_cell_count,
                "topology_hint": shape.topology_hint,
                "notes": shape.notes,
                "registry_version": FORMULA_SHAPE_REGISTRY_VERSION,
                "registry_checksum": FORMULA_SHAPE_REGISTRY_CHECKSUM,
            }
            for shape in FORMULA_SHAPE_REGISTRY
        }

        assert set(registry_rows.keys()) == set(expected.keys())
        for shape_id, expected_row in expected.items():
            actual = registry_rows[shape_id]
            for key, expected_value in expected_row.items():
                assert actual[key] == expected_value
    finally:
        engine.dispose()


def test_formula_translator_migration_downgrade_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_to_031(tmp_path, monkeypatch)
    try:
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_030")
    finally:
        engine.dispose()
