"""Focused coverage for per-Channel pricing-engine authority."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.pricing_authority.contracts import PricingAuthority, PricingOrigin
from app.flowhub.pricing_authority.errors import PricingAuthorityConflict, PricingAuthorityError
from app.flowhub.pricing_authority.models import (
    ChannelPricingAuthorityEvent,
    ChannelPricingAuthorityHead,
    PricingAuthorityWriteRejection,
)
from app.flowhub.pricing_authority.service import ChannelPricingAuthorityService
from app.flowhub.unified_workspace.domain import ImmutableRecordError
from app.flowhub.unified_workspace.models import WorkspaceChannel
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: F401
from app.flowhub.write_pipeline.workspace_contracts import WorkspaceWriteIntent


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = FlowHubUser(username=f"authority_{uuid.uuid4().hex}", hashed_password="unused", role="admin")
    session.add_all(
        (
            user,
            WorkspaceChannel(
                id="woocommerce:primary",
                connector_type="woocommerce",
                name="Primary",
                implementation_state="ready",
                capabilities_json={},
                capability_version="test-v1",
                enabled=True,
            ),
            WorkspaceChannel(
                id="snappshop:primary",
                connector_type="snappshop",
                name="Secondary",
                implementation_state="ready",
                capabilities_json={},
                capability_version="test-v1",
                enabled=True,
            ),
        )
    )
    session.commit()
    try:
        yield session, user
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _to_matrix(service: ChannelPricingAuthorityService, user: FlowHubUser, channel_id: str):
    legacy = service.snapshot(channel_id)
    locked = service.transition(
        channel_id=channel_id,
        new_authority=PricingAuthority.MIGRATION_LOCKED,
        expected_head_version=legacy.head_version,
        reason="Cutover preparation",
        user=user,
    )
    return service.transition(
        channel_id=channel_id,
        new_authority=PricingAuthority.PRICING_MATRIX,
        expected_head_version=locked.head_version,
        reason="Cutover complete",
        user=user,
    )


def _intent(*, origin: PricingOrigin, authority: PricingAuthority, event_id: str, head_version: int):
    return WorkspaceWriteIntent(
        apply_job_id="job-1",
        apply_item_ids=("item-1",),
        workspace_id="workspace-1",
        snapshot_id="snapshot-1",
        draft_revision_id="draft-1",
        review_id="review-1",
        selection_checksum="a" * 64,
        listing_id="listing-1",
        channel_id="woocommerce:primary",
        external_primary_id="1",
        sku="SKU-1",
        product_type="simple",
        parent_external_id=None,
        current_price=100.0,
        current_stock=None,
        current_status=None,
        target_price=110.0,
        target_stock=None,
        target_status=None,
        currency="EUR",
        unit="EUR",
        mapping_version=1,
        cache_version=1,
        cache_checksum="b" * 64,
        capability_version="test-v1",
        currency_digest="c" * 64,
        idempotency_key="key-1",
        payload_hash="d" * 64,
        pricing_origin=origin,
        expected_pricing_authority=authority,
        pricing_authority_event_id=event_id,
        pricing_authority_head_version=head_version,
    )
def test_seeded_authority_is_legacy_and_event_is_append_only(db):
    session, _user = db
    service = ChannelPricingAuthorityService(session)

    snapshot = service.snapshot("woocommerce:primary")
    event = session.get(ChannelPricingAuthorityEvent, snapshot.event_id)
    assert snapshot.authority is PricingAuthority.LEGACY_FORMULA_ENGINE
    assert snapshot.head_version == 0
    assert event is not None
    assert event.previous_authority is None
    assert event.new_authority == PricingAuthority.LEGACY_FORMULA_ENGINE.value

    event.reason = "mutated"
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()


def test_transition_requires_order_and_uses_head_cas(db):
    session, user = db
    service = ChannelPricingAuthorityService(session)
    legacy = service.snapshot("woocommerce:primary")

    with pytest.raises(PricingAuthorityError, match="pricing_authority_transition_invalid"):
        service.transition(
            channel_id=legacy.channel_id,
            new_authority=PricingAuthority.PRICING_MATRIX,
            expected_head_version=legacy.head_version,
            reason="Unsafe direct cutover",
            user=user,
        )

    locked = service.transition(
        channel_id=legacy.channel_id,
        new_authority=PricingAuthority.MIGRATION_LOCKED,
        expected_head_version=legacy.head_version,
        reason="Freeze writes",
        user=user,
    )
    assert locked.head_version == 1
    with pytest.raises(PricingAuthorityConflict):
        service.transition(
            channel_id=legacy.channel_id,
            new_authority=PricingAuthority.PRICING_MATRIX,
            expected_head_version=legacy.head_version,
            reason="Stale operator",
            user=user,
        )
    matrix = service.transition(
        channel_id=legacy.channel_id,
        new_authority=PricingAuthority.PRICING_MATRIX,
        expected_head_version=locked.head_version,
        reason="Enable Matrix",
        user=user,
    )
    assert matrix.head_version == 2
    assert session.query(ChannelPricingAuthorityEvent).filter_by(channel_id=legacy.channel_id).count() == 3


@pytest.mark.parametrize(
    ("authority", "origin", "code"),
    [
        (PricingAuthority.LEGACY_FORMULA_ENGINE, PricingOrigin.PRICING_MATRIX, "pricing_origin_not_authorized"),
        (PricingAuthority.MIGRATION_LOCKED, PricingOrigin.LEGACY_FORMULA_ENGINE, "pricing_authority_locked"),
        (PricingAuthority.MIGRATION_LOCKED, PricingOrigin.PRICING_MATRIX, "pricing_authority_locked"),
        (PricingAuthority.PRICING_MATRIX, PricingOrigin.LEGACY_FORMULA_ENGINE, "pricing_origin_not_authorized"),
    ],
)
def test_authority_rejects_non_authoritative_origin(db, authority, origin, code):
    session, user = db
    service = ChannelPricingAuthorityService(session)
    if authority is PricingAuthority.MIGRATION_LOCKED:
        current = service.snapshot("woocommerce:primary")
        snapshot = service.transition(
            channel_id=current.channel_id,
            new_authority=authority,
            expected_head_version=current.head_version,
            reason="Freeze writes",
            user=user,
        )
    elif authority is PricingAuthority.PRICING_MATRIX:
        snapshot = _to_matrix(service, user, "woocommerce:primary")
    else:
        snapshot = service.snapshot("woocommerce:primary")

    with pytest.raises(PricingAuthorityError, match=code):
        service.assert_write_authorized(
            channel_id=snapshot.channel_id,
            origin=origin,
            expected_event_id=snapshot.event_id,
            expected_head_version=snapshot.head_version,
        )


def test_authority_change_after_review_pin_is_rejected_and_audited(db):
    session, user = db
    service = ChannelPricingAuthorityService(session)
    matrix = _to_matrix(service, user, "woocommerce:primary")
    locked = service.transition(
        channel_id=matrix.channel_id,
        new_authority=PricingAuthority.MIGRATION_LOCKED,
        expected_head_version=matrix.head_version,
        reason="Emergency lock",
        user=user,
    )

    with pytest.raises(PricingAuthorityError, match="pricing_authority_conflict"):
        service.assert_write_authorized(
            channel_id=matrix.channel_id,
            origin=PricingOrigin.PRICING_MATRIX,
            expected_event_id=matrix.event_id,
            expected_head_version=matrix.head_version,
        )
    service.record_write_rejection(
        channel_id=matrix.channel_id,
        listing_id="listing-1",
        operation_id="apply-1",
        origin=PricingOrigin.PRICING_MATRIX,
        expected_event_id=matrix.event_id,
        expected_head_version=matrix.head_version,
        reason_code="pricing_authority_conflict",
        correlation_id="test",
    )
    session.commit()
    audit = session.query(PricingAuthorityWriteRejection).one()
    assert audit.current_authority == PricingAuthority.MIGRATION_LOCKED.value
    assert audit.current_head_version == locked.head_version


def test_channel_authority_is_isolated(db):
    session, user = db
    service = ChannelPricingAuthorityService(session)
    matrix = _to_matrix(service, user, "woocommerce:primary")
    other = service.snapshot("snappshop:primary")
    assert matrix.authority is PricingAuthority.PRICING_MATRIX
    assert other.authority is PricingAuthority.LEGACY_FORMULA_ENGINE


def test_persisted_write_intent_round_trips_authority_pin():
    intent = _intent(
        origin=PricingOrigin.PRICING_MATRIX,
        authority=PricingAuthority.PRICING_MATRIX,
        event_id="event-1",
        head_version=2,
    )
    restored = WorkspaceWriteIntent.from_persisted_payload(intent.normalized_payload())
    assert restored.pricing_origin is PricingOrigin.PRICING_MATRIX
    assert restored.expected_pricing_authority is PricingAuthority.PRICING_MATRIX
    assert restored.pricing_authority_event_id == "event-1"
    assert restored.pricing_authority_head_version == 2


@pytest.mark.asyncio
async def test_final_dispatch_boundary_blocks_stale_matrix_writer_and_records_audit(db, monkeypatch):
    session, user = db
    from app.flowhub.write_pipeline.service import WritePipelineService
    from app.flowhub.write_pipeline.workspace_contracts import (
        WorkspaceWriteBatchCommand,
        WorkspaceWriteResult,
        WriteOutcome,
    )

    service = ChannelPricingAuthorityService(session)
    matrix = _to_matrix(service, user, "woocommerce:primary")
    service.transition(
        channel_id=matrix.channel_id,
        new_authority=PricingAuthority.MIGRATION_LOCKED,
        expected_head_version=matrix.head_version,
        reason="Lock after review",
        user=user,
    )
    calls: list[str] = []

    class FakeConnector:
        def capabilities(self):
            return SimpleNamespace(channel_id="woocommerce:primary")

        async def apply_updates(self, updates, *, requested_by):
            calls.extend(update.listing_id for update in updates)
            return [
                WorkspaceWriteResult(
                    listing_id=update.listing_id,
                    outcome=WriteOutcome.VERIFIED_APPLIED,
                    provider_accepted=True,
                )
                for update in updates
            ]

        async def verify_updates(self, updates, *, requested_by):
            return []

    class FakeFactory:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, channel_id):
            assert channel_id == "woocommerce:primary"
            return FakeConnector()

        get_product_pricing = get

    class FakeRateLimitService:
        def __init__(self, *args, **kwargs):
            pass

        async def acquire(self, *args, **kwargs):
            return None

    import app.flowhub.channels.gateway as gateway_module
    import app.flowhub.write_pipeline.service as pipeline_module

    monkeypatch.setattr(gateway_module, "WorkspaceConnectorFactory", FakeFactory)
    monkeypatch.setattr(pipeline_module, "RateLimitService", FakeRateLimitService)
    command = WorkspaceWriteBatchCommand(
        workspace_id="workspace-1",
        snapshot_id="snapshot-1",
        draft_revision_id="draft-1",
        review_id="review-1",
        selection_checksum="a" * 64,
        correlation_id="authority-test",
        requested_by=user.username,
        intents=(
            _intent(
                origin=PricingOrigin.PRICING_MATRIX,
                authority=PricingAuthority.PRICING_MATRIX,
                event_id=matrix.event_id,
                head_version=matrix.head_version,
            ),
        ),
        pricing_origin=PricingOrigin.PRICING_MATRIX,
    )

    results = await WritePipelineService(session).execute_workspace(command, user)
    assert calls == []
    assert [(result.outcome, result.error_message) for result in results] == [
        (WriteOutcome.FAILED, "pricing_authority_conflict")
    ]
    attempt = session.query(PricingAuthorityWriteRejection).one()
    assert attempt.pricing_origin == PricingOrigin.PRICING_MATRIX.value
    assert attempt.reason_code == "pricing_authority_conflict"


@pytest.mark.asyncio
async def test_authorized_matrix_write_records_origin_before_provider_dispatch(db, monkeypatch):
    session, user = db
    from app.flowhub.write_pipeline.models import ProviderWriteAttempt
    from app.flowhub.write_pipeline.service import WritePipelineService
    from app.flowhub.write_pipeline.workspace_contracts import (
        WorkspaceWriteBatchCommand,
        WorkspaceWriteResult,
        WriteOutcome,
    )

    service = ChannelPricingAuthorityService(session)
    matrix = _to_matrix(service, user, "woocommerce:primary")
    calls: list[str] = []

    class FakeConnector:
        def capabilities(self):
            return SimpleNamespace(channel_id="woocommerce:primary")

        async def apply_updates(self, updates, *, requested_by):
            calls.extend(update.listing_id for update in updates)
            return [
                WorkspaceWriteResult(
                    listing_id=update.listing_id,
                    outcome=WriteOutcome.VERIFIED_APPLIED,
                    provider_accepted=True,
                )
                for update in updates
            ]

        async def verify_updates(self, updates, *, requested_by):
            return []

    class FakeFactory:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, channel_id):
            assert channel_id == "woocommerce:primary"
            return FakeConnector()

        get_product_pricing = get

    class FakeRateLimitService:
        def __init__(self, *args, **kwargs):
            pass

        async def acquire(self, *args, **kwargs):
            return None

    import app.flowhub.channels.gateway as gateway_module
    import app.flowhub.write_pipeline.service as pipeline_module

    monkeypatch.setattr(gateway_module, "WorkspaceConnectorFactory", FakeFactory)
    monkeypatch.setattr(pipeline_module, "RateLimitService", FakeRateLimitService)
    intent = _intent(
        origin=PricingOrigin.PRICING_MATRIX,
        authority=PricingAuthority.PRICING_MATRIX,
        event_id=matrix.event_id,
        head_version=matrix.head_version,
    )
    results = await WritePipelineService(session).execute_workspace(
        WorkspaceWriteBatchCommand(
            workspace_id="workspace-1",
            snapshot_id="snapshot-1",
            draft_revision_id="draft-1",
            review_id="review-1",
            selection_checksum="a" * 64,
            correlation_id="authority-allowed",
            requested_by=user.username,
            intents=(intent,),
            pricing_origin=PricingOrigin.PRICING_MATRIX,
        ),
        user,
    )
    assert calls == ["listing-1"]
    assert results[0].outcome is WriteOutcome.VERIFIED_APPLIED
    attempt = session.query(ProviderWriteAttempt).one()
    assert attempt.pricing_origin == PricingOrigin.PRICING_MATRIX.value
    assert attempt.pricing_authority_event_id == matrix.event_id
    assert attempt.pricing_authority_head_version == matrix.head_version
