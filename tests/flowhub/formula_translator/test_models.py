"""Persistence behavior checks for Formula Translator D2 evidence rows."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.formula_translator.contracts import (
    FormulaTranslationReason,
    FormulaTranslationStatus,
    FORMULA_SHAPE_REGISTRY_VERSION,
)
from app.flowhub.formula_translator.models import (
    FormulaShapeRegistryEntry,
    FormulaTranslationQuarantine,
    FormulaTranslationResult,
)
from app.flowhub.formula_translator.registry import FORMULA_SHAPE_REGISTRY_CHECKSUM
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    user = FlowHubUser(username="translator-user", hashed_password="unused", role="admin")
    session.add(user)
    session.commit()

    try:
        yield session, user
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _registry_row() -> FormulaShapeRegistryEntry:
    return FormulaShapeRegistryEntry(
        shape_id="A1",
        translation_status=FormulaTranslationStatus.TRANSLATED.value,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
        is_price_target=True,
        formula_cell_count=1,
        topology_hint="price_target_candidate",
        notes="fixture",
        record_payload_json={},
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        created_at=utcnow(),
    )


def _result_row(rule_identity: str = "A1:R1") -> FormulaTranslationResult:
    return FormulaTranslationResult(
        id=str(uuid.uuid4()),
        formula_rule_identity=rule_identity,
        formula_shape_id="A1",
        translation_status=FormulaTranslationStatus.TRANSLATED.value,
        reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
        translator_version="formula-translator-schema-v1",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_payload_json={"shape": "A1"},
        translation_fingerprint="a" * 64,
        translation_input_payload_json={"formula": "if", "shape": "A1"},
        created_at=utcnow(),
    )


def test_formula_translator_registries_are_immutable(db):
    session, _user = db
    session.add(_registry_row())
    session.commit()

    row = session.get(FormulaShapeRegistryEntry, "A1")
    row.notes = "mutated"
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()

    session.delete(row)
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()


def test_formula_translation_results_are_immutable(db):
    session, _user = db
    session.add_all((_registry_row(), _result_row()))
    session.commit()

    result = session.query(FormulaTranslationResult).first()
    result.translation_status = FormulaTranslationStatus.REVIEW_REQUIRED.value
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()

    session.delete(result)
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()


def test_formula_translation_quarantine_is_append_only(db):
    session, user = db
    row = _result_row("A1:R2")
    session.add_all((_registry_row(), row))
    session.commit()

    quarantine = FormulaTranslationQuarantine(
        id=str(uuid.uuid4()),
        formula_translation_result_id=row.id,
        quarantine_reason=FormulaTranslationReason.BROKEN_REFERENCE.value,
        evidence_json={"reason": "broken_reference"},
        created_by_user_id=user.id,
        created_at=utcnow(),
    )
    session.add(quarantine)
    session.commit()

    quarantine.evidence_json = {"reason": "changed"}
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()

    session.delete(quarantine)
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()


def test_translation_tables_enforce_closed_enums_and_uniqueness(db):
    session, _user = db
    session.add(_registry_row())
    session.commit()

    base = _result_row("A1:R3")
    session.add(base)
    session.commit()

    duplicate = _result_row("A1:R3")
    with pytest.raises(sa.exc.IntegrityError):
        session.add(duplicate)
        session.commit()
    session.rollback()

    bad_status = _result_row("A1:R4")
    bad_status.translation_status = "impossible"
    with pytest.raises(sa.exc.IntegrityError):
        session.add(bad_status)
        session.commit()
    session.rollback()

    bad_reason = _result_row("A1:R5")
    bad_reason.reason_code = "invalid"
    with pytest.raises(sa.exc.IntegrityError):
        session.add(bad_reason)
        session.commit()
    session.rollback()
