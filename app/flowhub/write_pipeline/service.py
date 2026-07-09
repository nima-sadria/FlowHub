"""Generic FlowHub Write Pipeline service.

Approval and execution are intentionally separate. Approval records operator
intent only; execution is a second explicit action dispatched through a
registered channel write adapter.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.errors import ConnectorError
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.setup.service import AppConfigService
from app.flowhub.write_pipeline.adapters import ChannelWriteAdapter, ChannelWriteContext
from app.flowhub.write_pipeline.contracts import (
    WritePipelineApprovalRequest,
    WritePipelineBatchShape,
    WritePipelineDryRunRequest,
    WritePipelineEventShape,
    WritePipelineItemShape,
)
from app.flowhub.write_pipeline.models import WriteBatch, WriteEvent, WriteItem
from app.flowhub.write_pipeline.registry import ChannelWriteAdapterRegistry, default_write_adapter_registry

MAX_ITEMS = 100
MAX_DELTA_PERCENT = 50.0
FORBIDDEN_STOCK_KEYS = frozenset({"stock", "stock_status", "stock_quantity", "inventory", "manage_stock"})
STOCK_OPERATION_TYPES = frozenset({"stock_update", "inventory_update", "write_inventory", "update_stock"})
AUTOMATIC_APPLY_KEYS = frozenset({"automaticApply", "automatic_apply", "applyNow", "apply_now", "scheduler", "scheduled"})


class WritePipelineService:
    def __init__(self, db: Session, registry: ChannelWriteAdapterRegistry | None = None):
        self.db = db
        self.config = AppConfigService(db)
        self.registry = registry or default_write_adapter_registry()

    def create_dry_run(self, body: WritePipelineDryRunRequest, user: FlowHubUser) -> WritePipelineBatchShape:
        if not body.changes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one price change is required.")
        self._validate_request_controls(body)
        adapter = self._adapter_for(body.channelId, body.operationType)
        capabilities = adapter.get_capabilities()
        raw_changes = [item.model_dump() for item in body.changes]
        safety = self._validate_changes(raw_changes, adapter, body.operationType)
        batch_id = f"wb_{uuid.uuid4().hex[:16]}"
        batch_hash = self._batch_hash(body)
        currency = body.changes[0].currency if body.changes else ""
        batch = WriteBatch(
            id=batch_id,
            channel_id=body.channelId,
            channel_type=capabilities.channel_type,
            operation_type=body.operationType,
            status="dry_run_ready",
            source_preview_id=body.previewId,
            batch_hash=batch_hash,
            item_count=len(body.changes),
            currency=currency,
            created_by=user.username,
            safety_summary_json=safety,
        )
        self.db.add(batch)
        self.db.flush()
        for change in body.changes:
            delta = change.proposedPrice - change.currentPrice
            pct = self._delta_percent(change.currentPrice, change.proposedPrice)
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
                        "source": (getattr(change, "model_extra", None) or {}).get("source"),
                        "validation_warnings": (getattr(change, "model_extra", None) or {}).get("validationWarnings", []),
                    },
                    status="pending",
                )
            )
        self._record_event(
            batch.id,
            "dry_run_created",
            "Dry Run created. No marketplace write was executed.",
            metadata={
                "approval_recorded": False,
                "execution_attempted": False,
                "source_preview_id": body.previewId,
                "source_rows": [
                    (getattr(change, "model_extra", None) or {}).get("source")
                    for change in body.changes
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
            metadata={"approval_recorded": True, "execution_attempted": False},
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
        for item in batch.items:
            try:
                await rate_limits.acquire(batch.channel_id, "write", connector_type=capabilities.channel_type)
                provider_result = _safe_provider_result(await adapter.execute_item(item, context))
            except ConnectorError as exc:
                failure_count += 1
                item.status = "failed"
                item.error_code = exc.code.value
                item.error_message = exc.message
                self._record_event(
                    batch.id,
                    "item_failed",
                    exc.message,
                    item_id=item.id,
                    severity="error",
                    metadata={
                        "provider": exc.provider,
                        "http_status": exc.http_status,
                        "old_price": item.current_price,
                        "new_price": item.proposed_price,
                    },
                    commit=False,
                )
            except Exception as exc:  # pragma: no cover - defensive adapter boundary
                failure_count += 1
                item.status = "failed"
                item.error_code = "unexpected_error"
                item.error_message = str(exc)
                self._record_event(
                    batch.id,
                    "item_failed",
                    str(exc),
                    item_id=item.id,
                    severity="error",
                    metadata={
                        "provider": capabilities.channel_type,
                        "old_price": item.current_price,
                        "new_price": item.proposed_price,
                    },
                    commit=False,
                )
            else:
                success_count += 1
                item.status = "applied"
                item.provider_result_json = provider_result
                self._record_event(
                    batch.id,
                    "item_applied",
                    "Channel price update applied.",
                    item_id=item.id,
                    metadata={
                        "provider": capabilities.channel_type,
                        "stock_update": False,
                        "old_price": item.current_price,
                        "new_price": item.proposed_price,
                        "result": _safe_provider_result(provider_result),
                    },
                    commit=False,
                )

        batch.executed_at = datetime.utcnow()
        batch.status = "applied" if failure_count == 0 else "partially_failed" if success_count else "failed"
        self._record_event(
            batch.id,
            "execution_finished",
            "Apply finished.",
            metadata={"success_count": success_count, "failure_count": failure_count, "scheduler_started": False},
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

    def _validate_request_controls(self, body: WritePipelineDryRunRequest) -> None:
        extras = getattr(body, "model_extra", None) or {}
        if AUTOMATIC_APPLY_KEYS.intersection(extras):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "automatic_apply_disabled")

    def _validate_changes(self, raw_changes: list[dict], adapter: ChannelWriteAdapter, operation_type: str) -> dict:
        if len(raw_changes) > MAX_ITEMS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Dry Run is limited to {MAX_ITEMS} items.")
        currencies: set[str] = set()
        max_delta = 0.0
        for change in raw_changes:
            if change.get("eligible_for_dry_run") is False:
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
            adapter.validate_item(change)
        if len(currencies) > 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run must use a single currency.")
        capabilities = adapter.get_capabilities()
        return {
            "operation": operation_type,
            "channel_id": capabilities.channel_ids[0] if capabilities.channel_ids else "",
            "item_count": len(raw_changes),
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

    def _batch_hash(self, body: WritePipelineDryRunRequest) -> str:
        parts = [body.channelId, body.operationType]
        for item in sorted(body.changes, key=lambda row: row.productId):
            parts.append(f"{item.productId}|{item.currentPrice:.4f}|{item.proposedPrice:.4f}|{item.currency}")
        return sha256("\n".join(parts).encode("utf-8")).hexdigest()

    def _batch_hash_from_row(self, batch: WriteBatch) -> str:
        parts = [batch.channel_id, batch.operation_type]
        for item in sorted(batch.items, key=lambda row: row.channel_product_id):
            parts.append(f"{item.channel_product_id}|{item.current_price:.4f}|{item.proposed_price:.4f}|{item.currency}")
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


def _safe_provider_result(result: dict) -> dict:
    return redact_sensitive(result or {})
