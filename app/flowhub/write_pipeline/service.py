"""Generic FlowHub Write Pipeline service.

Approval and execution are intentionally separate. Approval records operator
intent only; execution is a second explicit action dispatched through a
registered channel write adapter.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.errors import ConnectorError
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.security.redaction import redact_sensitive, redact_sensitive_text
from app.flowhub.setup.service import AppConfigService
from app.flowhub.write_pipeline.adapters import ChannelWriteAdapter, ChannelWriteContext
from app.flowhub.write_pipeline.contracts import (
    WritePipelineApprovalRequest,
    WritePipelineBatchShape,
    WritePipelineDryRunRequest,
    WritePipelineEventShape,
    WritePipelineItemShape,
    WritePipelinePriceChange,
)
from app.flowhub.write_pipeline.models import WriteBatch, WriteEvent, WriteItem
from app.flowhub.write_pipeline.registry import ChannelWriteAdapterRegistry, default_write_adapter_registry
from app.flowhub.workspace.preview_store import PreviewValidationError, WorkspacePreviewStore

MAX_ITEMS = 100
MAX_DELTA_PERCENT = 50.0
VERIFY_SMALL_BATCH_LIMIT = 25
VERIFY_TIMEOUT_SECONDS = 10.0
FORBIDDEN_STOCK_KEYS = frozenset({
    "stock", "stock_status", "stockstatus", "stock_quantity", "stockquantity", "inventory", "manage_stock", "managestock"
})
STOCK_OPERATION_TYPES = frozenset({"stock_update", "inventory_update", "write_inventory", "update_stock"})
AUTOMATIC_APPLY_KEYS = frozenset({"automaticApply", "automatic_apply", "applyNow", "apply_now", "scheduler", "scheduled"})


class WritePipelineService:
    def __init__(self, db: Session, registry: ChannelWriteAdapterRegistry | None = None):
        self.db = db
        self.config = AppConfigService(db)
        self.registry = registry or default_write_adapter_registry()
        self.integration = IntegrationPlatformService(db)

    def create_dry_run(self, body: WritePipelineDryRunRequest, user: FlowHubUser) -> WritePipelineBatchShape:
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
        preview_summary = selection.preview.summary_json if isinstance(selection.preview.summary_json, dict) else {}
        safety = self._validate_changes(raw_changes, adapter, operation_type, body.previewId, preview_summary)
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

    def approve(self, batch_id: str, body: WritePipelineApprovalRequest, user: FlowHubUser) -> WritePipelineBatchShape:
        batch = self._get_batch(batch_id)
        if batch.status != "dry_run_ready":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only a completed Dry Run can be approved.")
        self._assert_batch_hash_matches(batch)
        batch.status = "approved"
        batch.approved_by = user.username
        batch.approved_at = datetime.utcnow()
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
        batch = self._get_batch(batch_id)
        if batch.status != "approved":
            raise HTTPException(status.HTTP_409_CONFLICT, "Apply requires a separate approved Dry Run.")
        self._assert_batch_hash_matches(batch)
        adapter = self._adapter_for(batch.channel_id, batch.operation_type)
        self._assert_channel_write_enabled(batch)
        capabilities = adapter.get_capabilities()
        context = ChannelWriteContext(get_setting=self.config.get, requested_by=user.username)
        rate_limits = RateLimitService(self.db)
        batch.status = "executing"
        self._record_event(
            batch.id,
            "execution_started",
            "Apply started from an approved Dry Run.",
            metadata={"approved_by": batch.approved_by, "requested_by": user.username},
            commit=False,
        )
        self.db.commit()

        success_count = 0
        failure_count = 0
        verified_count = 0
        unverified_count = 0
        verification_warning_count = 0
        verification_enabled = batch.item_count <= VERIFY_SMALL_BATCH_LIMIT
        for item in batch.items:
            try:
                await rate_limits.acquire(batch.channel_id, "write", connector_type=capabilities.channel_type)
                provider_result = _safe_provider_result(await adapter.execute_item(item, context))
            except ConnectorError as exc:
                failure_count += 1
                item.status = "failed"
                item.error_code = exc.code.value
                item.error_message = redact_sensitive_text(exc.message)
                self._record_event(
                    batch.id,
                    "item_failed",
                    item.error_message,
                    item_id=item.id,
                    severity="error",
                    metadata={
                        "provider": exc.provider,
                        "http_status": exc.http_status,
                        "actor": user.username,
                        "channel_id": batch.channel_id,
                        "batch_id": batch.id,
                        "product_id": item.channel_product_id,
                        "sku": item.sku,
                        "old_price": item.current_price,
                        "new_price": item.proposed_price,
                        "status": item.status,
                        "source": _item_source(item),
                        "item_type": _item_type(item),
                        "parent_product_id": _parent_product_id(item),
                        "variation_id": _variation_id(item),
                        "variation_attributes": _variation_attributes(item),
                    },
                    commit=False,
                )
            except Exception as exc:  # pragma: no cover - defensive adapter boundary
                failure_count += 1
                item.status = "failed"
                item.error_code = "unexpected_error"
                item.error_message = redact_sensitive_text(str(exc))
                self._record_event(
                    batch.id,
                    "item_failed",
                    item.error_message,
                    item_id=item.id,
                    severity="error",
                    metadata={
                        "provider": capabilities.channel_type,
                        "actor": user.username,
                        "channel_id": batch.channel_id,
                        "batch_id": batch.id,
                        "product_id": item.channel_product_id,
                        "sku": item.sku,
                        "old_price": item.current_price,
                        "new_price": item.proposed_price,
                        "status": item.status,
                        "source": _item_source(item),
                        "item_type": _item_type(item),
                        "parent_product_id": _parent_product_id(item),
                        "variation_id": _variation_id(item),
                        "variation_attributes": _variation_attributes(item),
                    },
                    commit=False,
                )
            else:
                verification = self._verification_skipped_result()
                if verification_enabled:
                    verification = await self._verify_applied_item(adapter, item, context)
                    if verification.get("verified") is True:
                        verified_count += 1
                    else:
                        unverified_count += 1
                        verification_warning_count += 1
                        self._record_event(
                            batch.id,
                            "item_verification_warning",
                            "Price read-back verification did not confirm the expected value.",
                            item_id=item.id,
                            severity="warning",
                            metadata={
                                "actor": user.username,
                                "channel_id": batch.channel_id,
                                "batch_id": batch.id,
                                "product_id": item.channel_product_id,
                                "sku": item.sku,
                                "old_price": item.current_price,
                                "new_price": item.proposed_price,
                                "status": item.status,
                                "verification": verification,
                                "source": _item_source(item),
                                "item_type": _item_type(item),
                                "parent_product_id": _parent_product_id(item),
                                "variation_id": _variation_id(item),
                                "variation_attributes": _variation_attributes(item),
                            },
                            commit=False,
                        )
                else:
                    unverified_count += 1
                success_count += 1
                item.status = "applied"
                provider_result["verification"] = verification
                item.provider_result_json = _safe_provider_result(provider_result)
                self._record_event(
                    batch.id,
                    "item_applied",
                    "Channel price update applied.",
                    item_id=item.id,
                    metadata={
                        "provider": capabilities.channel_type,
                        "stock_update": False,
                        "actor": user.username,
                        "channel_id": batch.channel_id,
                        "batch_id": batch.id,
                        "product_id": item.channel_product_id,
                        "sku": item.sku,
                        "old_price": item.current_price,
                        "new_price": item.proposed_price,
                        "status": item.status,
                        "result": _safe_provider_result(provider_result),
                        "verification": verification,
                        "source": _item_source(item),
                        "item_type": _item_type(item),
                        "parent_product_id": _parent_product_id(item),
                        "variation_id": _variation_id(item),
                        "variation_attributes": _variation_attributes(item),
                    },
                    commit=False,
                )

        batch.executed_at = datetime.utcnow()
        batch.status = "applied" if failure_count == 0 else "partially_failed" if success_count else "failed"
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
                "warning_count": verification_warning_count,
                "verified_count": verified_count,
                "unverified_count": unverified_count,
                "skipped_count": (batch.safety_summary_json or {}).get("skipped_rows", 0),
                "scheduler_started": False,
                "automatic_apply": False,
                "stock_update": False,
            },
            commit=False,
        )
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_shape(batch)

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

    def _validate_request_controls(self, body: WritePipelineDryRunRequest, user: FlowHubUser) -> None:
        extras = getattr(body, "model_extra", None) or {}
        if AUTOMATIC_APPLY_KEYS.intersection(extras):
            self._record_preview_rejection(body.previewId, body.selectedRowIds, user, "automatic_apply_disabled")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "automatic_apply_disabled")
        if extras.get("channelId") not in (None, "woocommerce:primary"):
            self._record_preview_rejection(body.previewId, body.selectedRowIds, user, "unsupported_channel_write")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "unsupported_channel_write")
        if STOCK_OPERATION_TYPES.intersection({str(extras.get("operationType") or "").lower()}):
            self._record_preview_rejection(body.previewId, body.selectedRowIds, user, "stock_writes_disabled")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "stock_writes_disabled")
        if FORBIDDEN_STOCK_KEYS.intersection({str(key).lower() for key in extras}):
            self._record_preview_rejection(body.previewId, body.selectedRowIds, user, "stock_writes_disabled")
            raise HTTPException(status.HTTP_403_FORBIDDEN, "stock_writes_disabled")
        if extras:
            self._record_preview_rejection(body.previewId, body.selectedRowIds, user, "DRY_RUN_REQUEST_FIELDS_INVALID")
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "DRY_RUN_REQUEST_FIELDS_INVALID: submit only previewId and selectedRowIds.",
            )

    def _validate_changes(
        self,
        raw_changes: list[dict],
        adapter: ChannelWriteAdapter,
        operation_type: str,
        preview_id: str,
        preview_summary: dict,
    ) -> dict:
        if len(raw_changes) > MAX_ITEMS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Dry Run is limited to {MAX_ITEMS} items.")
        if not preview_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run requires a Workspace preview ID.")
        currencies: set[str] = set()
        max_delta = 0.0
        product_ids: set[str] = set()
        for change in raw_changes:
            source = change.get("source")
            if not isinstance(source, dict) or source.get("previewId") != preview_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run changes must come from the active Workspace preview.")
            if change.get("eligible_for_dry_run") is not True:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rows with validation errors cannot enter Dry Run.")
            if change.get("status") == "error" or change.get("validationStatus") == "error":
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rows with validation errors cannot enter Dry Run.")
            forbidden = FORBIDDEN_STOCK_KEYS.intersection({key.lower() for key in change})
            if forbidden:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Stock updates are blocked in FlowHub 1.0.0.")
            current = float(change["currentPrice"])
            proposed = float(change["proposedPrice"])
            if not math.isfinite(current) or not math.isfinite(proposed):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Prices must be finite numbers.")
            if current < 0 or proposed <= 0:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Prices must be positive.")
            delta_pct = abs(self._delta_percent(current, proposed))
            max_delta = max(max_delta, delta_pct)
            if delta_pct > MAX_DELTA_PERCENT:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Price change exceeds the 50% safety gate.")
            currencies.add(str(change.get("currency") or ""))
            product_ids.add(str(change.get("productId") or ""))
            adapter.validate_item(change)
        if len(currencies) > 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run must use a single currency.")
        capabilities = adapter.get_capabilities()
        skipped_rows = int(preview_summary.get("unchanged_rows") or 0) if isinstance(preview_summary, dict) else 0
        blocked_rows = int(preview_summary.get("error_rows") or 0) if isinstance(preview_summary, dict) else 0
        warning_rows = int(preview_summary.get("warning_rows") or 0) if isinstance(preview_summary, dict) else 0
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
        metadata: dict | None = None,
        commit: bool = True,
    ) -> WriteEvent:
        event = WriteEvent(
            batch_id=batch_id,
            item_id=item_id,
            event_type=event_type,
            severity=severity,
            message=message,
            metadata_json=redact_sensitive(metadata or {}),
            correlation_id=f"corr_{uuid.uuid4().hex[:12]}",
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

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
            validationWarnings=list((row.pre_write_snapshot_json or {}).get("validation_warnings") or []),
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

    async def _verify_applied_item(
        self,
        adapter: ChannelWriteAdapter,
        item: WriteItem,
        context: ChannelWriteContext,
    ) -> dict:
        try:
            async with asyncio.timeout(VERIFY_TIMEOUT_SECONDS):
                result = await adapter.verify_item(item, context)
            return _safe_provider_result({
                "verified": bool(result.get("verified")),
                "observed_price": result.get("observed_price"),
                "expected_price": result.get("expected_price", item.proposed_price),
                "verification_error": result.get("verification_error"),
            })
        except ConnectorError as exc:
            return {
                "verified": False,
                "observed_price": None,
                "expected_price": item.proposed_price,
                "verification_error": redact_sensitive_text(exc.message),
            }
        except TimeoutError:
            return {
                "verified": False,
                "observed_price": None,
                "expected_price": item.proposed_price,
                "verification_error": "verification_timeout",
            }
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            return {
                "verified": False,
                "observed_price": None,
                "expected_price": item.proposed_price,
                "verification_error": redact_sensitive_text(str(exc)),
            }

    def _verification_skipped_result(self) -> dict:
        return {
            "verified": False,
            "observed_price": None,
            "expected_price": None,
            "verification_error": "verification_skipped_batch_too_large",
        }

    def _result_summary(self, row: WriteBatch) -> dict:
        attempted = len(row.items) if row.executed_at else 0
        success = sum(1 for item in row.items if item.status == "applied")
        failure = sum(1 for item in row.items if item.status == "failed")
        verified = sum(1 for item in row.items if (item.provider_result_json or {}).get("verification", {}).get("verified") is True)
        unverified = sum(
            1
            for item in row.items
            if item.status == "applied" and (item.provider_result_json or {}).get("verification", {}).get("verified") is not True
        )
        safety = row.safety_summary_json or {}
        warning_count = int(safety.get("warning_rows") or 0) + unverified
        return {
            "total_attempted": attempted,
            "success_count": success,
            "failure_count": failure,
            "skipped_count": int(safety.get("skipped_rows") or 0),
            "blocked_count": int(safety.get("blocked_rows") or 0),
            "warning_count": warning_count,
            "verified_count": verified,
            "unverified_count": unverified,
            "estimated_affected_products": int(safety.get("estimated_affected_products") or row.item_count),
        }


def _safe_provider_result(result: dict) -> dict:
    return redact_sensitive(result or {})


def _item_source(item: WriteItem) -> dict | None:
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


def _variation_attributes(item: WriteItem) -> list[dict]:
    value = (item.pre_write_snapshot_json or {}).get("variation_attributes")
    return value if isinstance(value, list) else []


def _source_fingerprint(source: object) -> str:
    if not isinstance(source, dict):
        return ""
    return "|".join(
        str(source.get(key) or "")
        for key in ("previewId", "sourceSnapshotId", "sourceSnapshotVersion", "sourceFilePath", "worksheet", "rowNumber")
    )
