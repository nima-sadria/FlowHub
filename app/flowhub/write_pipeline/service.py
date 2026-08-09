"""Generic FlowHub Write Pipeline service.

Approval and execution are intentionally separate. Approval records operator
intent only; execution is a second explicit action dispatched through a
registered channel write adapter.
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.business_observability.service import BusinessObservabilityService
from app.flowhub.data_layer.telemetry_service import ConnectorTelemetryService
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.pricing_authority.contracts import PricingAuthority, PricingOrigin
from app.flowhub.pricing_authority.errors import PricingAuthorityError
from app.flowhub.pricing_authority.service import ChannelPricingAuthorityService
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.setup.service import AppConfigService
from app.flowhub.workspace.preview_store import PreviewValidationError, WorkspacePreviewStore
from app.flowhub.write_pipeline.adapters import ChannelWriteAdapter
from app.flowhub.write_pipeline.contracts import (
    WritePipelineApprovalRequest,
    WritePipelineBatchShape,
    WritePipelineDryRunRequest,
    WritePipelineEventShape,
    WritePipelineItemShape,
    WritePipelinePriceChange,
)
from app.flowhub.write_pipeline.models import (
    ProviderWriteAttempt,
    ProviderWriteAttemptEvent,
    WriteBatch,
    WriteEvent,
    WriteItem,
)
from app.flowhub.write_pipeline.registry import (
    ChannelWriteAdapterRegistry,
    default_write_adapter_registry,
)
from app.flowhub.write_pipeline.workspace_contracts import (
    WorkspaceWriteBatchCommand,
    WorkspaceWriteIntent,
    WorkspaceWriteResult,
    WriteOutcome,
)

MAX_ITEMS = 100
MAX_DELTA_PERCENT = 50.0
FORBIDDEN_STOCK_KEYS = frozenset(
    {
        "stock",
        "stock_status",
        "stockstatus",
        "stock_quantity",
        "stockquantity",
        "inventory",
        "manage_stock",
        "managestock",
    }
)
STOCK_OPERATION_TYPES = frozenset(
    {"stock_update", "inventory_update", "write_inventory", "update_stock"}
)
AUTOMATIC_APPLY_KEYS = frozenset(
    {"automaticApply", "automatic_apply", "applyNow", "apply_now", "scheduler", "scheduled"}
)


class _ProductCacheView(Protocol):
    product_id: str
    sku: str | None
    regular_price: str | None
    price: str | None
    stock_qty: int | None
    stock_status: str | None
    freshness: str
    last_successful_read: datetime | None
    record_hash: str


class WritePipelineService:
    def __init__(self, db: Session, registry: ChannelWriteAdapterRegistry | None = None):
        self.db = db
        self.config = AppConfigService(db)
        self.registry = registry or default_write_adapter_registry()
        self.integration = IntegrationPlatformService(db)

    def create_dry_run(
        self, body: WritePipelineDryRunRequest, user: FlowHubUser
    ) -> WritePipelineBatchShape:
        self._validate_request_controls(body, user)
        try:
            selection = WorkspacePreviewStore(self.db).validate_selection(
                preview_id=body.previewId,
                selected_row_ids=body.selectedRowIds,
                user=user,
            )
        except PreviewValidationError as exc:
            self._record_preview_rejection(body.previewId, body.selectedRowIds, user, exc.code)
            raise HTTPException(exc.status_code, exc.code) from exc

        channel_id = "woocommerce:primary"
        operation_type = "price_update"
        changes = [WritePipelinePriceChange.model_validate(change) for change in selection.changes]
        raw_changes = [change.model_dump() for change in changes]
        adapter = self._adapter_for(channel_id, operation_type)
        capabilities = adapter.get_capabilities()
        preview_summary: dict[str, Any] = (
            selection.preview.summary_json
            if isinstance(selection.preview.summary_json, dict)
            else {}
        )
        safety = self._validate_changes(
            raw_changes, adapter, operation_type, body.previewId, preview_summary
        )
        safety["selected_row_ids"] = list(body.selectedRowIds)
        safety["preview_hash"] = selection.preview.preview_hash
        batch_id = f"wb_{uuid.uuid4().hex[:16]}"
        batch_hash = self._batch_hash(changes, channel_id, operation_type)
        currency = changes[0].currency if changes else ""
        batch = WriteBatch(
            id=batch_id,
            channel_id=channel_id,
            channel_type=capabilities.channel_type,
            operation_type=operation_type,
            status="dry_run_ready",
            source_preview_id=body.previewId,
            batch_hash=batch_hash,
            item_count=len(changes),
            currency=currency,
            created_by=user.username,
            safety_summary_json=safety,
        )
        self.db.add(batch)
        self.db.flush()
        for change in changes:
            delta = change.proposedPrice - change.currentPrice
            pct = self._delta_percent(change.currentPrice, change.proposedPrice)
            extras = getattr(change, "model_extra", None) or {}
            source = extras.get("source")
            warnings = extras.get("validationWarnings", [])
            item_type = str(extras.get("itemType") or "simple")
            parent_product_id = extras.get("parentProductId")
            parent_product_name = extras.get("parentProductName")
            variation_id = extras.get("variationId")
            variation_attributes = extras.get("variationAttributes") or []
            self.db.add(
                WriteItem(
                    batch_id=batch.id,
                    channel_product_id=change.productId,
                    sku=change.sku,
                    product_name=change.productName,
                    current_price=change.currentPrice,
                    proposed_price=change.proposedPrice,
                    delta_amount=delta,
                    delta_percent=pct,
                    currency=change.currency,
                    pre_write_snapshot_json={
                        "productId": change.productId,
                        "sku": change.sku,
                        "price": change.currentPrice,
                        "currency": change.currency,
                        "source": source,
                        "validation_warnings": warnings,
                        "status": extras.get("status") or extras.get("validationStatus"),
                        "item_type": item_type,
                        "parent_product_id": parent_product_id,
                        "parent_product_name": parent_product_name,
                        "variation_id": variation_id,
                        "variation_attributes": variation_attributes,
                        "source_fingerprint": _source_fingerprint(source),
                    },
                    status="pending",
                )
            )
        self._record_event(
            batch.id,
            "dry_run_created_from_preview",
            "Dry Run created from immutable selected preview rows. No marketplace write was executed.",
            metadata={
                "approval_recorded": False,
                "execution_attempted": False,
                "actor": user.username,
                "channel_id": channel_id,
                "operation_type": operation_type,
                "batch_hash": batch_hash,
                "item_count": len(changes),
                "eligible_rows": safety["eligible_rows"],
                "skipped_rows": safety["skipped_rows"],
                "blocked_rows": safety["blocked_rows"],
                "source_preview_id": body.previewId,
                "preview_hash": selection.preview.preview_hash,
                "selected_row_ids": list(body.selectedRowIds),
                "selected_row_count": len(body.selectedRowIds),
                "source_rows": [
                    (getattr(change, "model_extra", None) or {}).get("source")
                    for change in changes
                    if (getattr(change, "model_extra", None) or {}).get("source")
                ],
            },
            commit=False,
        )
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_shape(batch)

    def approve(
        self, batch_id: str, body: WritePipelineApprovalRequest, user: FlowHubUser
    ) -> WritePipelineBatchShape:
        batch = self._get_batch(batch_id)
        if batch.status != "dry_run_ready":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Only a completed Dry Run can be approved."
            )
        self._assert_batch_hash_matches(batch)
        batch.status = "approved"
        batch.approved_by = user.username
        batch.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        batch.approval_reason = body.reason
        self._record_event(
            batch.id,
            "approved",
            "Approved. Execution was not started.",
            metadata={
                "approval_recorded": True,
                "execution_attempted": False,
                "actor": user.username,
                "approved_item_count": batch.item_count,
                "batch_hash": batch.batch_hash,
                "channel_id": batch.channel_id,
            },
            commit=False,
        )
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_shape(batch)

    async def execute(self, batch_id: str, user: FlowHubUser) -> WritePipelineBatchShape:
        """Execute an approved legacy batch through the shared durable engine.

        This method intentionally remains a compatibility facade for the v1
        Write Pipeline API.  It creates immutable provider-neutral intents and
        delegates all provider I/O, verification, attempt persistence, and
        reconciliation to :meth:`execute_workspace`.
        """
        batch = self._get_batch(batch_id)
        resumable_status = batch.status in {"executing", "reconciliation_required"}
        if batch.status != "approved" and not resumable_status:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Apply requires a separate approved Dry Run."
            )
        self._assert_batch_hash_matches(batch)
        # Resolve capability before access mode so unsupported channels fail
        # closed consistently with the historical endpoint contract.
        self._adapter_for(batch.channel_id, batch.operation_type)
        correlation_id = self._legacy_correlation_id(batch) or f"corr_{uuid.uuid4().hex[:28]}"
        if not resumable_status:
            # Keep the state transition in the same transaction as the first
            # immutable ProviderWriteAttempt.  A process death here therefore
            # leaves the approved batch retryable, never an inert executing
            # batch without durable dispatch evidence.
            batch.status = "executing"
            self._record_event(
                batch.id,
                "execution_started",
                "Apply started from an approved Dry Run.",
                metadata={
                    "approved_by": batch.approved_by,
                    "requested_by": user.username,
                    "correlation_id": correlation_id,
                    "source_workflow": "legacy_write_pipeline",
                },
                correlation_id=correlation_id,
                commit=False,
            )
        command = self._legacy_batch_command(batch, user, correlation_id)
        has_attempts = (
            self.db.query(ProviderWriteAttempt.id)
            .filter(
                ProviderWriteAttempt.source_workflow == "legacy_write_pipeline",
                ProviderWriteAttempt.operation_id == batch.id,
            )
            .first()
            is not None
        )
        # Recovery is verification-only when durable dispatch evidence exists;
        # it must remain possible even if a channel has since been switched to
        # read-only mode.  A resumable batch without an attempt still needs the
        # original write gate before it can create a new dispatch intent.
        if not resumable_status or not has_attempts:
            self._assert_channel_write_enabled(batch)
        results = await self.execute_workspace(
            command,
            user,
            reconcile_only=resumable_status and has_attempts,
        )
        results_by_listing = {result.listing_id: result for result in results}
        success_count = failure_count = reconciliation_count = 0
        for item in batch.items:
            result = results_by_listing.get(self._legacy_listing_id(item, batch.channel_id))
            if result is None:
                item.status = "failed"
                item.error_code = "provider_contract"
                item.error_message = "Shared Write Pipeline returned no result for the item."
                failure_count += 1
                event_type = "item_failed"
            elif result.outcome is WriteOutcome.VERIFIED_APPLIED:
                item.status = "applied"
                item.error_code = None
                item.error_message = None
                item.provider_result_json = _safe_provider_result(result.response)
                success_count += 1
                event_type = "item_applied"
            elif result.outcome is WriteOutcome.RECONCILIATION_REQUIRED:
                item.status = "reconciliation_required"
                item.error_code = result.error_category or "read_back_unverified"
                item.error_message = result.error_message or "Provider state requires reconciliation."
                item.provider_result_json = _safe_provider_result(result.response)
                reconciliation_count += 1
                event_type = "item_reconciliation_required"
            else:
                item.status = "failed"
                item.error_code = result.error_category or "provider_error"
                item.error_message = result.error_message or "Provider write failed."
                item.provider_result_json = _safe_provider_result(result.response)
                failure_count += 1
                event_type = "item_failed"
            self._record_event(
                batch.id,
                event_type,
                item.error_message or "Channel price update applied.",
                item_id=item.id,
                severity="error" if event_type != "item_applied" else "info",
                metadata={
                    "provider": batch.channel_type,
                    "actor": user.username,
                    "channel_id": batch.channel_id,
                    "batch_id": batch.id,
                    "product_id": item.channel_product_id,
                    "sku": item.sku,
                    "old_price": item.current_price,
                    "new_price": item.proposed_price,
                    "status": item.status,
                    "result": _safe_provider_result(result.response) if result else {},
                    "verification": _safe_provider_result(result.response).get("verification") if result else None,
                    "source": _item_source(item),
                    "item_type": _item_type(item),
                    "parent_product_id": _parent_product_id(item),
                    "variation_id": _variation_id(item),
                    "variation_attributes": _variation_attributes(item),
                    "correlation_id": correlation_id,
                },
                correlation_id=correlation_id,
                commit=False,
            )
            self._emit_channel_write_business_event(
                item, event_type, result, batch, correlation_id=correlation_id
            )
        batch.executed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        batch.status = (
            "applied"
            if failure_count == 0 and reconciliation_count == 0
            else "reconciliation_required"
            if reconciliation_count and success_count == 0
            else "partially_failed"
            if success_count
            else "failed"
        )
        self._record_event(
            batch.id,
            "execution_finished",
            "Apply finished.",
            metadata={
                "actor": user.username,
                "channel_id": batch.channel_id,
                "batch_id": batch.id,
                "success_count": success_count,
                "failure_count": failure_count,
                "warning_count": reconciliation_count,
                "verified_count": success_count,
                "unverified_count": reconciliation_count,
                "skipped_count": (batch.safety_summary_json or {}).get("skipped_rows", 0),
                "scheduler_started": False,
                "automatic_apply": False,
                "stock_update": False,
            },
            correlation_id=correlation_id,
            commit=False,
        )
        self._emit_batch_business_event(
            batch,
            success_count=success_count,
            failure_count=failure_count,
            reconciliation_count=reconciliation_count,
            correlation_id=correlation_id,
        )
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_shape(batch)

    def _legacy_correlation_id(self, batch: WriteBatch) -> str | None:
        """Recover the original correlation id after a worker restart."""
        for event in reversed(batch.events):
            if event.correlation_id:
                return event.correlation_id
            metadata = event.metadata_json or {}
            value = metadata.get("correlation_id")
            if isinstance(value, str) and value:
                return value
        return None

    def _legacy_listing_id(self, item: WriteItem, channel_id: str | None = None) -> str:
        """Return a stable listing identity for a legacy batch item."""
        return f"legacy:{channel_id or 'woocommerce:primary'}:{item.channel_product_id}"

    def _legacy_batch_command(
        self, batch: WriteBatch, user: FlowHubUser, correlation_id: str
    ) -> WorkspaceWriteBatchCommand:
        """Adapt approved legacy rows to immutable provider-neutral intents."""
        self._ensure_authority_channel(batch.channel_id)
        authority = ChannelPricingAuthorityService(self.db).snapshot(batch.channel_id)
        intents: list[WorkspaceWriteIntent] = []
        for item in batch.items:
            listing_id = self._legacy_listing_id(item, batch.channel_id)
            snapshot = item.pre_write_snapshot_json or {}
            payload_seed = {
                "batch_id": batch.id,
                "item_id": str(item.id),
                "listing_id": listing_id,
                "channel_id": batch.channel_id,
                "external_primary_id": item.channel_product_id,
                "field": "price",
                "target_price": item.proposed_price,
                "currency": item.currency,
                "source_fingerprint": snapshot.get("source_fingerprint", ""),
            }
            payload_hash = sha256(
                json.dumps(payload_seed, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            idempotency_key = sha256(
                f"legacy-write-pipeline:{batch.id}:{item.id}:{payload_hash}".encode()
            ).hexdigest()
            intents.append(
                WorkspaceWriteIntent(
                    apply_job_id=batch.id,
                    apply_item_ids=(str(item.id),),
                    workspace_id=f"legacy:{batch.id}",
                    snapshot_id=batch.source_preview_id or batch.batch_hash,
                    draft_revision_id=batch.id,
                    review_id=batch.source_preview_id or batch.id,
                    selection_checksum=batch.batch_hash,
                    listing_id=listing_id,
                    channel_id=batch.channel_id,
                    external_primary_id=item.channel_product_id,
                    sku=item.sku or None,
                    product_type=_item_type(item),
                    parent_external_id=_parent_product_id(item),
                    current_price=item.current_price,
                    current_stock=None,
                    current_status=None,
                    target_price=item.proposed_price,
                    target_stock=None,
                    target_status=None,
                    currency=item.currency,
                    unit=item.currency,
                    mapping_version=0,
                    cache_version=0,
                    cache_checksum=str(snapshot.get("source_fingerprint") or ""),
                    capability_version="legacy-write-pipeline-v1",
                    currency_digest=sha256(item.currency.encode()).hexdigest(),
                    idempotency_key=idempotency_key,
                    payload_hash=payload_hash,
                    pricing_origin=PricingOrigin.LEGACY_FORMULA_ENGINE,
                    expected_pricing_authority=PricingAuthority.LEGACY_FORMULA_ENGINE,
                    pricing_authority_event_id=authority.event_id,
                    pricing_authority_head_version=authority.head_version,
                )
            )
        return WorkspaceWriteBatchCommand(
            workspace_id=f"legacy:{batch.id}",
            snapshot_id=batch.source_preview_id or batch.batch_hash,
            draft_revision_id=batch.id,
            review_id=batch.source_preview_id or batch.id,
            selection_checksum=batch.batch_hash,
            correlation_id=correlation_id,
            requested_by=user.username,
            intents=tuple(intents),
            source_workflow="legacy_write_pipeline",
            pricing_origin=PricingOrigin.LEGACY_FORMULA_ENGINE,
        )

    def _ensure_authority_channel(self, channel_id: str) -> None:
        """Materialize the canonical Channel row before attaching write authority."""
        from app.flowhub.unified_workspace.models import WorkspaceChannel
        from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

        if self.db.get(WorkspaceChannel, channel_id) is None:
            UnifiedWorkspaceService(self.db)._seed_channels()
            self.db.flush()

    async def execute_workspace(
        self,
        command: WorkspaceWriteBatchCommand,
        user: FlowHubUser,
        *,
        reconcile_only: bool = False,
    ) -> list[WorkspaceWriteResult]:
        """Sole provider-dispatch authority for immutable Workspace intents."""
        from app.flowhub.channels.gateway import WorkspaceConnectorFactory
        from app.flowhub.commerce.service import CommerceHubService
        from app.flowhub.product_pricing.service import ProductPricingService

        factory = WorkspaceConnectorFactory(
            ProductPricingService(self.db), CommerceHubService(self.db)
        )
        self._assert_workspace_fence(command)
        # Canonical Workspace attempts use source_workflow="unified_workspace";
        # compatibility callers override it without creating another engine.
        workflow = command.source_workflow or "unified_workspace"
        rate_limits = RateLimitService(self.db)
        attempts: dict[str, ProviderWriteAttempt] = {}
        prior_attempts: set[str] = set()
        for intent in command.intents:
            existing = (
                self.db.query(ProviderWriteAttempt)
                .filter_by(
                    source_workflow=workflow,
                    operation_id=intent.apply_job_id,
                    logical_item_id=intent.apply_item_ids[0],
                    payload_hash=intent.payload_hash,
                )
                .order_by(ProviderWriteAttempt.attempt_number.desc())
                .first()
            )
            if existing is not None:
                attempts[intent.listing_id] = existing
                prior_attempts.add(intent.listing_id)
                continue
            if reconcile_only:
                raise ValueError(
                    f"No durable dispatch intent exists for Listing {intent.listing_id}."
                )
            attempt = ProviderWriteAttempt(
                id=f"pwa_{uuid.uuid4().hex[:28]}",
                source_workflow=workflow,
                operation_id=intent.apply_job_id,
                logical_item_id=intent.apply_item_ids[0],
                workspace_id=(
                    intent.workspace_id if workflow == "unified_workspace" else None
                ),
                # Legacy/Product Pricing operations are not rows in the
                # Workspace Apply aggregate.  Keep the provider-neutral
                # operation identity in operation_id while leaving the
                # optional Workspace foreign keys NULL so PostgreSQL FK
                # enforcement remains valid for compatibility callers.
                apply_job_id=(intent.apply_job_id if workflow == "unified_workspace" else None),
                apply_job_item_id=(
                    intent.apply_item_ids[0] if workflow == "unified_workspace" else None
                ),
                listing_id=intent.listing_id,
                channel_id=intent.channel_id,
                external_identity=intent.external_primary_id,
                normalized_payload_json=intent.normalized_payload(),
                payload_hash=intent.payload_hash,
                provider_idempotency_key=intent.idempotency_key,
                attempt_number=1,
                correlation_id=command.correlation_id,
                pricing_origin=(intent.pricing_origin.value if intent.pricing_origin else None),
                pricing_authority_event_id=intent.pricing_authority_event_id,
                pricing_authority_head_version=intent.pricing_authority_head_version,
            )
            self.db.add(attempt)
            self.db.flush()
            self.db.add(
                ProviderWriteAttemptEvent(
                    id=f"pwe_{uuid.uuid4().hex[:28]}",
                    attempt_id=attempt.id,
                    outcome=WriteOutcome.DISPATCH_INTENT_RECORDED,
                    provider_response_json={},
                )
            )
            attempts[intent.listing_id] = attempt
        self.db.commit()

        grouped: dict[str, list[WorkspaceWriteIntent]] = {}
        for intent in command.intents:
            grouped.setdefault(intent.channel_id, []).append(intent)
        results: list[WorkspaceWriteResult] = []
        for channel_id, intents in grouped.items():
            connector = (
                factory.get_product_pricing(channel_id)
                if workflow == "product_pricing"
                else factory.get(channel_id)
            )
            # A mixed retry must never redispatch an item whose durable intent
            # already exists.  Dispatch only new intents and verify prior ones
            # independently, even when they share a provider batch.
            pending_intents = [
                intent for intent in intents if intent.listing_id not in prior_attempts
            ]
            prior_intents = [
                intent for intent in intents if intent.listing_id in prior_attempts
            ]
            channel_results: list[WorkspaceWriteResult] = []
            if pending_intents and not reconcile_only:
                try:
                    for _intent in pending_intents:
                        await rate_limits.acquire(
                            channel_id,
                            "write",
                            connector_type=connector.capabilities().channel_id.split(":", 1)[0],
                        )
                except Exception as exc:
                    channel_results = [
                        WorkspaceWriteResult(
                            listing_id=intent.listing_id,
                            outcome=WriteOutcome.FAILED,
                            error_category="rate_limit",
                            error_message=str(exc),
                            retry_eligible=True,
                        )
                        for intent in pending_intents
                    ]
                else:
                    self._assert_workspace_fence(command)
                    dispatchable_intents, rejected_results = self._filter_authorized_price_intents(
                        command, pending_intents, attempts
                    )
                    channel_results.extend(rejected_results)
                    for intent in dispatchable_intents:
                        self.db.add(
                            ProviderWriteAttemptEvent(
                                id=f"pwe_{uuid.uuid4().hex[:28]}",
                                attempt_id=attempts[intent.listing_id].id,
                                outcome=WriteOutcome.DISPATCHED,
                                provider_response_json={},
                            )
                        )
                    self.db.commit()
                    if dispatchable_intents:
                        try:
                            channel_results.extend(
                                await connector.apply_updates(
                                    dispatchable_intents, requested_by=command.requested_by
                                )
                            )
                        except Exception as exc:
                            channel_results.extend(
                                WorkspaceWriteResult(
                                    listing_id=intent.listing_id,
                                    outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                                    error_category="provider_unknown",
                                    error_message=str(exc),
                                )
                                for intent in dispatchable_intents
                            )
            if prior_intents or reconcile_only:
                verify_intents = intents if reconcile_only else prior_intents
                channel_results.extend(
                    await connector.verify_updates(
                        verify_intents, requested_by=command.requested_by
                    )
                )
            self._record_transport_reports(channel_id, channel_results)
            for result in channel_results:
                # Provider I/O may outlive the original worker lease.  Recheck
                # ownership before persisting any outcome so a stale worker
                # cannot finalize an operation after recovery has fenced it.
                self._assert_workspace_fence(command)
                attempt = attempts[result.listing_id]
                if result.provider_accepted:
                    self.db.add(
                        ProviderWriteAttemptEvent(
                            id=f"pwe_{uuid.uuid4().hex[:28]}",
                            attempt_id=attempt.id,
                            outcome=WriteOutcome.PROVIDER_ACCEPTED,
                            provider_response_json=redact_sensitive(result.response),
                        )
                    )
                self.db.add(
                    ProviderWriteAttemptEvent(
                        id=f"pwe_{uuid.uuid4().hex[:28]}",
                        attempt_id=attempt.id,
                        outcome=result.outcome,
                        provider_response_json=redact_sensitive(result.response),
                        error_category=result.error_category,
                        error_message=result.error_message,
                    )
                )
                results.append(result)
            self.db.commit()
        return results

    def _filter_authorized_price_intents(
        self,
        command: WorkspaceWriteBatchCommand,
        intents: list[WorkspaceWriteIntent],
        attempts: dict[str, ProviderWriteAttempt],
    ) -> tuple[list[WorkspaceWriteIntent], list[WorkspaceWriteResult]]:
        """Enforce pricing authority at the final boundary before provider I/O."""
        service = ChannelPricingAuthorityService(self.db)
        allowed: list[WorkspaceWriteIntent] = []
        rejected: list[WorkspaceWriteResult] = []
        for intent in intents:
            if intent.target_price is None:
                allowed.append(intent)
                continue
            code = self._pricing_authority_issue(command, intent, service)
            if code is None:
                allowed.append(intent)
                continue
            origin = intent.pricing_origin or command.pricing_origin
            service.record_write_rejection(
                channel_id=intent.channel_id,
                listing_id=intent.listing_id,
                operation_id=intent.apply_job_id,
                origin=origin,
                expected_event_id=intent.pricing_authority_event_id,
                expected_head_version=intent.pricing_authority_head_version,
                reason_code=code,
                correlation_id=command.correlation_id,
            )
            rejected.append(
                WorkspaceWriteResult(
                    listing_id=intent.listing_id,
                    outcome=WriteOutcome.FAILED,
                    error_category="pricing_authority",
                    error_message=code,
                )
            )
            self._emit_pricing_authority_business_event(
                intent, reason_code=code, correlation_id=command.correlation_id
            )
        return allowed, rejected

    def _emit_pricing_authority_business_event(
        self, intent: WorkspaceWriteIntent, *, reason_code: str, correlation_id: str
    ) -> None:
        """Pricing domain producer (Business Observability v1, Phase 2).

        Fires when the final pre-dispatch pricing-authority boundary
        (``_pricing_authority_issue``) rejects a price write - the
        "Pricing apply blocked" case from the master diagram's worked
        example. Distinct from the Channels producer below: this is a
        pricing-policy rejection, not a provider/connector failure.
        """

        BusinessObservabilityService(self.db).emit_event(
            domain="pricing",
            event_type="pricing_apply_blocked",
            severity="error",
            business_impact="blocking",
            reason_code=reason_code,
            reason_message=f"Pricing apply blocked: {reason_code}",
            primary_scope_type="channel",
            primary_scope_id=intent.channel_id,
            secondary_scopes=[
                ("product", intent.listing_id, intent.sku),
                ("review", intent.review_id, None),
                ("workspace", intent.workspace_id, None),
            ],
            recommended_action=(
                "Review the pricing approval for this channel before retrying the write."
            ),
            retryable=True,
            action_route_key="workspace.review",
            action_route_params={"workspace_id": intent.workspace_id},
            correlation_id=correlation_id,
            producer="write_pipeline.service._filter_authorized_price_intents",
            commit=False,
        )

    @staticmethod
    def _pricing_authority_issue(
        command: WorkspaceWriteBatchCommand,
        intent: WorkspaceWriteIntent,
        service: ChannelPricingAuthorityService,
    ) -> str | None:
        if (
            command.pricing_origin is None
            or intent.pricing_origin is None
            or command.pricing_origin != intent.pricing_origin
            or intent.expected_pricing_authority is None
            or intent.expected_pricing_authority.value != intent.pricing_origin.value
        ):
            return "pricing_origin_not_authorized"
        try:
            service.assert_write_authorized(
                channel_id=intent.channel_id,
                origin=intent.pricing_origin,
                expected_event_id=intent.pricing_authority_event_id,
                expected_head_version=intent.pricing_authority_head_version,
            )
        except PricingAuthorityError as exc:
            return exc.code
        return None

    def _record_transport_reports(
        self,
        channel_id: str,
        results: list[WorkspaceWriteResult],
    ) -> None:
        unique: dict[str, dict[str, Any]] = {}
        for result in results:
            verification = result.response.get("verification")
            if not isinstance(verification, dict):
                continue
            report = verification.get("transport")
            if not isinstance(report, dict):
                continue
            report_key = str(report.get("operation_id") or "")
            if not report_key:
                report_key = json.dumps(report, sort_keys=True, default=str)
            unique[report_key] = report
        if not unique:
            return
        telemetry = ConnectorTelemetryService(self.db)
        connector_type = channel_id.split(":", 1)[0]
        for report in unique.values():
            requests = int(report.get("requests_issued") or 0)
            if requests <= 0:
                continue
            provider_ms = float(report.get("provider_response_ms") or 0)
            telemetry.increment(
                channel_id,
                connector_type,
                requests=requests,
                errors=int(report.get("failed_requests") or 0),
                retries=int(report.get("retries") or 0),
                products_fetched=int(report.get("entities_returned") or 0),
                latency_ms=(provider_ms / requests) if requests else None,
            )

    def _assert_workspace_fence(self, command: WorkspaceWriteBatchCommand) -> None:
        """Fail closed when Apply ownership changed during provider I/O."""
        if command.fencing_token is None or not command.lease_token:
            return
        from app.flowhub.unified_workspace.models import ApplyJob

        job = self.db.get(ApplyJob, command.intents[0].apply_job_id) if command.intents else None
        if (
            job is None
            or job.fencing_token != command.fencing_token
            or job.lease_token != command.lease_token
            or job.worker_id is None
        ):
            raise RuntimeError("workspace_apply_worker_fenced")

    async def execute_product_pricing_item(
        self,
        item: Any,
        user: FlowHubUser,
    ) -> WorkspaceWriteResult:
        """Adapt one Product Pricing item to the shared durable engine."""
        from app.flowhub.data_layer.models import DlProductCache
        from app.flowhub.unified_workspace.listing_guard import acquire_listing_guard
        from app.flowhub.unified_workspace.models import Listing

        listing = (
            self.db.query(Listing)
            .filter(
                Listing.channel_id == item.channel_id,
                Listing.external_primary_id == item.channel_product_id,
            )
            .with_for_update()
            .one_or_none()
        )
        if listing is not None:
            acquire_listing_guard(self.db, listing.channel_id, listing.id)
        cache = (
            self.db.query(DlProductCache)
            .filter_by(
                connector_id=item.channel_id,
                product_id=item.channel_product_id,
            )
            .one_or_none()
        )
        typed_cache = cache
        identity = f"{item.channel_id}:{item.channel_product_id}"
        listing_id = listing.id if listing is not None else identity
        payload = {
            "operation_id": item.operation_id,
            "source_workflow": "product_pricing",
            "channel_id": item.channel_id,
            "listing_id": listing_id,
            "external_primary_id": item.channel_product_id,
            "sku": item.sku or None,
            "field_changes": {"price": item.proposed_value},
            "normalized_target": {
                "price": item.outbound_value,
                "currency": item.currency,
                "unit": item.outbound_unit,
            },
            "expected_cache_token": item.stale_token,
            "actor": user.username,
        }
        payload_hash = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        provider_key = sha256(
            f"product-pricing:{item.operation_id}:{item.id}:{payload_hash}".encode()
        ).hexdigest()
        self._ensure_authority_channel(item.channel_id)
        authority = ChannelPricingAuthorityService(self.db).snapshot(item.channel_id)
        intent = WorkspaceWriteIntent(
            apply_job_id=item.operation_id,
            apply_item_ids=(str(item.id),),
            workspace_id=f"product-pricing:{item.operation_id}",
            snapshot_id=item.stale_token,
            draft_revision_id=item.operation_id,
            review_id=item.operation_id,
            selection_checksum=payload_hash,
            listing_id=listing_id,
            channel_id=item.channel_id,
            external_primary_id=item.channel_product_id,
            sku=item.sku or None,
            product_type="simple",
            parent_external_id=None,
            current_price=item.current_value,
            current_stock=(
                float(typed_cache.stock_qty)
                if typed_cache is not None and typed_cache.stock_qty is not None
                else None
            ),
            current_status=typed_cache.stock_status if typed_cache is not None else None,
            target_price=item.outbound_value,
            target_stock=None,
            target_status=None,
            currency=item.currency,
            unit=item.outbound_unit,
            mapping_version=0,
            cache_version=0,
            cache_checksum=item.stale_token,
            capability_version="product-pricing-v1",
            currency_digest=sha256(item.currency.encode()).hexdigest(),
            idempotency_key=provider_key,
            payload_hash=payload_hash,
            pricing_origin=PricingOrigin.LEGACY_FORMULA_ENGINE,
            expected_pricing_authority=PricingAuthority.LEGACY_FORMULA_ENGINE,
            pricing_authority_event_id=authority.event_id,
            pricing_authority_head_version=authority.head_version,
        )
        command = WorkspaceWriteBatchCommand(
            workspace_id=intent.workspace_id,
            snapshot_id=intent.snapshot_id,
            draft_revision_id=intent.draft_revision_id,
            review_id=intent.review_id,
            selection_checksum=intent.selection_checksum,
            correlation_id=f"product-pricing:{item.operation_id}",
            requested_by=user.username,
            intents=(intent,),
            source_workflow="product_pricing",
            pricing_origin=PricingOrigin.LEGACY_FORMULA_ENGINE,
        )
        try:
            results = await self.execute_workspace(command, user)
        except Exception as exc:
            # A compatibility provider exception is inherently ambiguous once
            # the durable intent exists; recovery must verify, never dispatch
            # blindly a second time.
            return WorkspaceWriteResult(
                listing_id=listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                error_category="provider_unknown",
                error_message=str(exc),
                retry_eligible=False,
            )
        if len(results) != 1:
            return WorkspaceWriteResult(
                listing_id=listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                error_category="provider_contract",
                error_message="Provider returned an ambiguous item count.",
                retry_eligible=False,
            )
        result = results[0]
        attempt = (
            self.db.query(ProviderWriteAttempt)
            .filter_by(
                source_workflow="product_pricing",
                operation_id=item.operation_id,
                logical_item_id=str(item.id),
                payload_hash=payload_hash,
            )
            .order_by(ProviderWriteAttempt.attempt_number.desc())
            .first()
        )
        if attempt is not None:
            item.result_json = {
                "dispatch_intent": {
                    "payload": attempt.normalized_payload_json,
                    "payload_hash": attempt.payload_hash,
                    "attempt_id": attempt.id,
                    "idempotency_key": attempt.provider_idempotency_key,
                    "state": result.outcome,
                    "created_at": attempt.created_at.isoformat(),
                }
            }
        if result.outcome is WriteOutcome.VERIFIED_APPLIED and typed_cache is not None:
            stored_price = (
                str(int(item.proposed_value))
                if float(item.proposed_value).is_integer()
                else str(item.proposed_value)
            )
            typed_cache.regular_price = stored_price
            typed_cache.price = stored_price
            typed_cache.freshness = "fresh"
            typed_cache.last_successful_read = datetime.now(timezone.utc).replace(tzinfo=None)
            typed_cache.record_hash = sha256(
                "|".join(
                    str(value or "")
                    for value in (
                        typed_cache.product_id,
                        typed_cache.sku,
                        typed_cache.regular_price,
                        typed_cache.price,
                    )
                ).encode("utf-8")
            ).hexdigest()
        return result

    def get_batch(self, batch_id: str) -> WritePipelineBatchShape:
        return self._batch_shape(self._get_batch(batch_id))

    def list_events(self, batch_id: str) -> list[WritePipelineEventShape]:
        self._get_batch(batch_id)
        rows = (
            self.db.query(WriteEvent)
            .filter(WriteEvent.batch_id == batch_id)
            .order_by(WriteEvent.created_at.asc(), WriteEvent.id.asc())
            .all()
        )
        return [self._event_shape(row) for row in rows]

    def _adapter_for(self, channel_id: str, operation_type: str) -> ChannelWriteAdapter:
        if operation_type in STOCK_OPERATION_TYPES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "stock_writes_disabled")
        adapter = self.registry.get(channel_id, operation_type)
        if adapter is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "unsupported_channel_write")
        capabilities = adapter.get_capabilities()
        if capabilities.scheduler_supported or capabilities.automatic_apply_supported:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "unsafe_write_capability")
        return adapter

    def _validate_request_controls(
        self, body: WritePipelineDryRunRequest, user: FlowHubUser
    ) -> None:
        extras = getattr(body, "model_extra", None) or {}
        if AUTOMATIC_APPLY_KEYS.intersection(extras):
            self._record_preview_rejection(
                body.previewId, body.selectedRowIds, user, "automatic_apply_disabled"
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "automatic_apply_disabled")
        if extras.get("channelId") not in (None, "woocommerce:primary"):
            self._record_preview_rejection(
                body.previewId, body.selectedRowIds, user, "unsupported_channel_write"
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "unsupported_channel_write")
        if STOCK_OPERATION_TYPES.intersection({str(extras.get("operationType") or "").lower()}):
            self._record_preview_rejection(
                body.previewId, body.selectedRowIds, user, "stock_writes_disabled"
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "stock_writes_disabled")
        if FORBIDDEN_STOCK_KEYS.intersection({str(key).lower() for key in extras}):
            self._record_preview_rejection(
                body.previewId, body.selectedRowIds, user, "stock_writes_disabled"
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "stock_writes_disabled")
        if extras:
            self._record_preview_rejection(
                body.previewId, body.selectedRowIds, user, "DRY_RUN_REQUEST_FIELDS_INVALID"
            )
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "DRY_RUN_REQUEST_FIELDS_INVALID: submit only previewId and selectedRowIds.",
            )

    def _validate_changes(
        self,
        raw_changes: list[dict[str, Any]],
        adapter: ChannelWriteAdapter,
        operation_type: str,
        preview_id: str,
        preview_summary: dict[str, Any],
    ) -> dict[str, Any]:
        if len(raw_changes) > MAX_ITEMS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Dry Run is limited to {MAX_ITEMS} items."
            )
        if not preview_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run requires a Workspace preview ID."
            )
        currencies: set[str] = set()
        max_delta = 0.0
        product_ids: set[str] = set()
        for change in raw_changes:
            source = change.get("source")
            if not isinstance(source, dict) or source.get("previewId") != preview_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Dry Run changes must come from the active Workspace preview.",
                )
            if change.get("eligible_for_dry_run") is not True:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Rows with validation errors cannot enter Dry Run.",
                )
            if change.get("status") == "error" or change.get("validationStatus") == "error":
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Rows with validation errors cannot enter Dry Run.",
                )
            forbidden = FORBIDDEN_STOCK_KEYS.intersection({key.lower() for key in change})
            if forbidden:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN, "Stock updates are blocked in FlowHub 1.0.0."
                )
            current = float(change["currentPrice"])
            proposed = float(change["proposedPrice"])
            if not math.isfinite(current) or not math.isfinite(proposed):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Prices must be finite numbers."
                )
            if current < 0 or proposed <= 0:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Prices must be positive."
                )
            delta_pct = abs(self._delta_percent(current, proposed))
            max_delta = max(max_delta, delta_pct)
            if delta_pct > MAX_DELTA_PERCENT:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Price change exceeds the 50% safety gate.",
                )
            currencies.add(str(change.get("currency") or ""))
            product_ids.add(str(change.get("productId") or ""))
            adapter.validate_item(change)
        if len(currencies) > 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run must use a single currency."
            )
        capabilities = adapter.get_capabilities()
        skipped_rows = (
            int(preview_summary.get("unchanged_rows") or 0)
            if isinstance(preview_summary, dict)
            else 0
        )
        blocked_rows = (
            int(preview_summary.get("error_rows") or 0) if isinstance(preview_summary, dict) else 0
        )
        warning_rows = (
            int(preview_summary.get("warning_rows") or 0)
            if isinstance(preview_summary, dict)
            else 0
        )
        return {
            "operation": operation_type,
            "channel_id": capabilities.channel_ids[0] if capabilities.channel_ids else "",
            "item_count": len(raw_changes),
            "eligible_rows": len(raw_changes),
            "skipped_rows": skipped_rows,
            "blocked_rows": blocked_rows,
            "warning_rows": warning_rows,
            "estimated_affected_products": len(product_ids),
            "max_delta_percent": round(max_delta, 4),
            "stock_update_allowed": False,
            "scheduler_started": False,
            "automatic_apply": False,
            "marketplace_writes_limited_to": [capabilities.channel_type],
        }

    def _get_batch(self, batch_id: str) -> WriteBatch:
        row = self.db.get(WriteBatch, batch_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dry Run not found.")
        return row

    def _batch_hash(
        self,
        changes: list[WritePipelinePriceChange],
        channel_id: str,
        operation_type: str,
    ) -> str:
        parts = [channel_id, operation_type]
        for item in sorted(changes, key=lambda row: row.productId):
            extras = getattr(item, "model_extra", None) or {}
            source = extras.get("source")
            source_part = _source_fingerprint(source)
            item_type = str(extras.get("itemType") or "simple")
            parent_product_id = str(extras.get("parentProductId") or "")
            variation_id = str(extras.get("variationId") or "")
            parts.append(
                f"{item.productId}|{item.currentPrice:.4f}|{item.proposedPrice:.4f}|{item.currency}|"
                f"{source_part}|{item_type}|{parent_product_id}|{variation_id}"
            )
        return sha256("\n".join(parts).encode("utf-8")).hexdigest()

    def _record_preview_rejection(
        self,
        preview_id: str,
        selected_row_ids: list[str],
        user: FlowHubUser,
        reason: str,
    ) -> None:
        self.integration.record_event(
            connector_id="nextcloud:primary",
            event_name="dry_run_rejected",
            message="Dry Run request rejected before batch creation.",
            severity="warning",
            metadata={
                "preview_id": preview_id,
                "selected_row_ids": list(selected_row_ids),
                "selected_row_count": len(selected_row_ids),
                "reason": reason,
                "actor": user.username,
                "execution_attempted": False,
            },
        )
        BusinessObservabilityService(self.db).emit_event(
            domain="write_pipeline",
            event_type="write_dry_run_rejected",
            severity="warning",
            business_impact="blocking",
            reason_code=reason,
            reason_message=f"Dry Run request rejected: {reason}",
            primary_scope_type="batch",
            primary_scope_id=preview_id,
            primary_scope_label=f"Preview {preview_id}",
            recommended_action="Review the Dry Run request and retry.",
            retryable=True,
            action_route_key="workspace.home",
            producer="write_pipeline.service._record_preview_rejection",
        )

    def _batch_hash_from_row(self, batch: WriteBatch) -> str:
        parts = [batch.channel_id, batch.operation_type]
        for item in sorted(batch.items, key=lambda row: row.channel_product_id):
            snapshot = item.pre_write_snapshot_json or {}
            source_part = str(snapshot.get("source_fingerprint") or "")
            item_type = str(snapshot.get("item_type") or "simple")
            parent_product_id = str(snapshot.get("parent_product_id") or "")
            variation_id = str(snapshot.get("variation_id") or "")
            parts.append(
                f"{item.channel_product_id}|{item.current_price:.4f}|{item.proposed_price:.4f}|{item.currency}|"
                f"{source_part}|{item_type}|{parent_product_id}|{variation_id}"
            )
        return sha256("\n".join(parts).encode("utf-8")).hexdigest()

    def _assert_batch_hash_matches(self, batch: WriteBatch) -> None:
        if self._batch_hash_from_row(batch) != batch.batch_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "approval_hash_mismatch")

    def _assert_channel_write_enabled(self, batch: WriteBatch) -> None:
        instance = self.db.get(IntegrationConnectorInstance, batch.channel_id)
        if instance is None or instance.read_only:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "channel_write_access_disabled")

    def _record_event(
        self,
        batch_id: str,
        event_type: str,
        message: str,
        *,
        item_id: int | None = None,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        commit: bool = True,
    ) -> WriteEvent:
        event = WriteEvent(
            batch_id=batch_id,
            item_id=item_id,
            event_type=event_type,
            severity=severity,
            message=message,
            metadata_json=redact_sensitive(metadata or {}),
            correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:12]}",
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    # Write Pipeline batch-outcome -> Business Observability mapping (Business
    # Observability v1, Write Pipeline producer). One event per completed
    # batch execution, covering the full outcome including full success -
    # unlike the Channels producer, which only reports failing items.
    _BATCH_STATUS_BUSINESS_EVENT: dict[str, tuple[str, str, str, str, bool]] = {
        # status -> (event_type, severity, business_impact, recommended_action, retryable)
        "applied": ("write_batch_applied", "info", "none", "", False),
        "reconciliation_required": (
            "write_batch_reconciliation_required",
            "warning",
            "blocking",
            "Review items awaiting reconciliation before relying on their applied state.",
            True,
        ),
        "partially_failed": (
            "write_batch_partially_failed",
            "error",
            "partial_failure",
            "Review the failed items in this batch and retry them.",
            True,
        ),
        "failed": (
            "write_batch_failed",
            "critical",
            "critical_business_failure",
            "Review this batch's failure details and retry the write.",
            True,
        ),
    }

    # item outcome -> Channels business event mapping (Business Observability
    # v1, Phase 2). Only non-success outcomes are reported here - unlike the
    # Write Pipeline producer, a per-item success event would add volume
    # without giving an operator anything new to act on.
    _ITEM_CHANNEL_BUSINESS_EVENT: dict[str, tuple[str, str, str, str, bool]] = {
        # event_type -> (business event_type, severity, business_impact, recommended_action, retryable)
        "item_failed": (
            "channel_write_failed",
            "error",
            "partial_failure",
            "Retry this item once the destination channel issue is resolved.",
            True,
        ),
        "item_reconciliation_required": (
            "channel_write_reconciliation_required",
            "warning",
            "blocking",
            "Verify this item's applied state on the channel before relying on it.",
            False,
        ),
    }

    def _emit_channel_write_business_event(
        self,
        item: WriteItem,
        event_type: str,
        result: WorkspaceWriteResult | None,
        batch: WriteBatch,
        *,
        correlation_id: str,
    ) -> None:
        """Channels domain producer (Business Observability v1, Phase 2).

        Every channel connector's write outcome already funnels through this
        one loop (the confirmed single external-write dispatch authority),
        so this reports uniformly across all four marketplace providers
        without needing each connector to adopt a shared error type itself.
        Pricing-authority rejections are intentionally excluded here - they
        already emit a Pricing domain event in
        ``_emit_pricing_authority_business_event`` and would otherwise be
        double-reported under two domains for the same root cause.
        """

        mapping = self._ITEM_CHANNEL_BUSINESS_EVENT.get(event_type)
        if mapping is None:
            return
        if result is not None and result.error_category == "pricing_authority":
            return
        business_event_type, severity, business_impact, recommended_action, retryable = mapping
        BusinessObservabilityService(self.db).emit_event(
            domain="channels",
            event_type=business_event_type,
            severity=severity,
            business_impact=business_impact,
            reason_code=item.error_code or "unknown",
            reason_message=item.error_message or "",
            primary_scope_type="channel",
            primary_scope_id=batch.channel_id,
            primary_scope_label=batch.channel_type,
            secondary_scopes=[("product", item.channel_product_id, item.sku)],
            recommended_action=recommended_action,
            retryable=retryable,
            action_route_key="channel.detail",
            action_route_params={"channel_id": batch.channel_id},
            correlation_id=correlation_id,
            producer="write_pipeline.service.execute (channel result)",
            commit=False,
        )

    def _emit_batch_business_event(
        self,
        batch: WriteBatch,
        *,
        success_count: int,
        failure_count: int,
        reconciliation_count: int,
        correlation_id: str,
    ) -> None:
        mapping = self._BATCH_STATUS_BUSINESS_EVENT.get(batch.status)
        if mapping is None:
            return
        event_type, severity, business_impact, recommended_action, retryable = mapping
        BusinessObservabilityService(self.db).emit_event(
            domain="write_pipeline",
            event_type=event_type,
            severity=severity,
            business_impact=business_impact,
            reason_code=batch.status,
            reason_message=(
                f"{success_count} applied, {failure_count} failed, "
                f"{reconciliation_count} requiring reconciliation."
            ),
            primary_scope_type="batch",
            primary_scope_id=batch.id,
            primary_scope_label=f"Write batch {batch.id}",
            secondary_scopes=[("channel", batch.channel_id, batch.channel_type)],
            recommended_action=recommended_action,
            retryable=retryable,
            action_route_key="workspace.home",
            correlation_id=correlation_id,
            producer="write_pipeline.service.execute_workspace",
            commit=False,
        )

    def _batch_shape(self, row: WriteBatch) -> WritePipelineBatchShape:
        return WritePipelineBatchShape(
            id=row.id,
            channelId=row.channel_id,
            channelType=row.channel_type,
            operationType=row.operation_type,
            status=row.status,
            sourcePreviewId=row.source_preview_id,
            batchHash=row.batch_hash,
            itemCount=row.item_count,
            currency=row.currency,
            safetySummary=row.safety_summary_json or {},
            resultSummary=self._result_summary(row),
            createdBy=row.created_by,
            approvedBy=row.approved_by,
            approvalReason=row.approval_reason,
            createdAt=row.created_at,
            approvedAt=row.approved_at,
            executedAt=row.executed_at,
            items=[self._item_shape(item) for item in row.items],
        )

    def _item_shape(self, row: WriteItem) -> WritePipelineItemShape:
        return WritePipelineItemShape(
            id=row.id,
            productId=row.channel_product_id,
            productName=row.product_name,
            sku=row.sku,
            currentPrice=row.current_price,
            proposedPrice=row.proposed_price,
            difference=row.delta_amount,
            changePct=row.delta_percent,
            currency=row.currency,
            status=row.status,
            errorCode=row.error_code,
            errorMessage=row.error_message,
            source=_item_source(row),
            validationWarnings=list(
                (row.pre_write_snapshot_json or {}).get("validation_warnings") or []
            ),
            itemType=_item_type(row),
            parentProductId=_parent_product_id(row),
            parentProductName=(row.pre_write_snapshot_json or {}).get("parent_product_name"),
            variationId=_variation_id(row),
            variationAttributes=_variation_attributes(row),
            providerResult=_safe_provider_result(row.provider_result_json or {}),
            verification=(row.provider_result_json or {}).get("verification"),
        )

    def _event_shape(self, row: WriteEvent) -> WritePipelineEventShape:
        return WritePipelineEventShape(
            id=row.id,
            batchId=row.batch_id,
            itemId=row.item_id,
            eventType=row.event_type,
            severity=row.severity,
            message=row.message,
            metadata=row.metadata_json or {},
            correlationId=row.correlation_id,
            createdAt=row.created_at,
        )

    def _delta_percent(self, current: float, proposed: float) -> float:
        if current == 0:
            return 0.0
        return ((proposed - current) / current) * 100.0

    def _result_summary(self, row: WriteBatch) -> dict[str, Any]:
        attempted = len(row.items) if row.executed_at else 0
        success = sum(1 for item in row.items if item.status == "applied")
        failure = sum(1 for item in row.items if item.status == "failed")
        reconciliation = sum(
            1 for item in row.items if item.status == "reconciliation_required"
        )
        verified = sum(
            1
            for item in row.items
            if (item.provider_result_json or {}).get("verification", {}).get("verified") is True
        )
        unverified = sum(
            1
            for item in row.items
            if item.status == "applied"
            and (item.provider_result_json or {}).get("verification", {}).get("verified")
            is not True
        )
        safety = row.safety_summary_json or {}
        warning_count = int(safety.get("warning_rows") or 0) + unverified
        return {
            "total_attempted": attempted,
            "success_count": success,
            "failure_count": failure,
            "reconciliation_count": reconciliation,
            "skipped_count": int(safety.get("skipped_rows") or 0),
            "blocked_count": int(safety.get("blocked_rows") or 0),
            "warning_count": warning_count,
            "verified_count": verified,
            "unverified_count": unverified,
            "estimated_affected_products": int(
                safety.get("estimated_affected_products") or row.item_count
            ),
        }


def _safe_provider_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = redact_sensitive(result or {})
    return dict(sanitized) if isinstance(sanitized, dict) else {}


def _item_source(item: WriteItem) -> dict[str, Any] | None:
    source = (item.pre_write_snapshot_json or {}).get("source")
    return source if isinstance(source, dict) else None


def _item_type(item: WriteItem) -> str:
    return str((item.pre_write_snapshot_json or {}).get("item_type") or "simple")


def _parent_product_id(item: WriteItem) -> str | None:
    value = (item.pre_write_snapshot_json or {}).get("parent_product_id")
    return str(value) if value not in (None, "") else None


def _variation_id(item: WriteItem) -> str | None:
    value = (item.pre_write_snapshot_json or {}).get("variation_id")
    return str(value) if value not in (None, "") else None


def _variation_attributes(item: WriteItem) -> list[dict[str, Any]]:
    value = (item.pre_write_snapshot_json or {}).get("variation_attributes")
    return (
        [dict(entry) for entry in value if isinstance(entry, dict)]
        if isinstance(value, list)
        else []
    )


def _source_fingerprint(source: object) -> str:
    if not isinstance(source, dict):
        return ""
    return "|".join(
        str(source.get(key) or "")
        for key in (
            "previewId",
            "sourceSnapshotId",
            "sourceSnapshotVersion",
            "sourceFilePath",
            "worksheet",
            "rowNumber",
        )
    )
