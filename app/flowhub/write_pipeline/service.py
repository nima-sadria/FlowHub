"""Generic FlowHub Write Pipeline service.

Approval and execution are intentionally separate. Approval records operator
intent only; execution is a second explicit action and is restricted to the
WooCommerce price adapter in FlowHub 1.0.0.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError
from app.connectors.destinations.woocommerce.connector import WooCommerceConnector
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.setup.service import AppConfigService
from app.flowhub.write_pipeline.contracts import (
    WritePipelineApprovalRequest,
    WritePipelineBatchShape,
    WritePipelineDryRunRequest,
    WritePipelineEventShape,
    WritePipelineItemShape,
)
from app.flowhub.write_pipeline.models import WriteBatch, WriteEvent, WriteItem

ALLOWED_CHANNEL_ID = "woocommerce:primary"
ALLOWED_CHANNEL_TYPE = "woocommerce"
ALLOWED_OPERATION = "price_update"
MAX_ITEMS = 100
MAX_DELTA_PERCENT = 50.0
FORBIDDEN_STOCK_KEYS = frozenset({"stock", "stock_status", "stock_quantity", "inventory", "manage_stock"})
BLOCKED_CHANNEL_PREFIXES = frozenset({"snappshop", "tapsishop", "digikala", "technolife", "shopify"})


class WritePipelineService:
    def __init__(self, db: Session):
        self.db = db
        self.config = AppConfigService(db)

    def create_dry_run(self, body: WritePipelineDryRunRequest, user: FlowHubUser) -> WritePipelineBatchShape:
        if not body.changes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one price change is required.")
        self._validate_scope(body.channelId, body.operationType)
        safety = self._validate_changes([item.model_dump() for item in body.changes])
        batch_id = f"wb_{uuid.uuid4().hex[:16]}"
        batch_hash = self._batch_hash(body)
        currency = body.changes[0].currency if body.changes else ""
        batch = WriteBatch(
            id=batch_id,
            channel_id=body.channelId,
            channel_type=ALLOWED_CHANNEL_TYPE,
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
                    },
                    status="pending",
                )
            )
        self._record_event(
            batch.id,
            "dry_run_created",
            "Dry Run created. No marketplace write was executed.",
            metadata={"approval_recorded": False, "execution_attempted": False},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_shape(batch)

    def approve(self, batch_id: str, body: WritePipelineApprovalRequest, user: FlowHubUser) -> WritePipelineBatchShape:
        batch = self._get_batch(batch_id)
        if batch.status != "dry_run_ready":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only a completed Dry Run can be approved.")
        batch.status = "approved"
        batch.approved_by = user.username
        batch.approved_at = datetime.utcnow()
        batch.approval_reason = body.reason
        self._record_event(
            batch.id,
            "approved",
            "Approved for WooCommerce price update. Execution was not started.",
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
        self._validate_batch_scope(batch)
        batch.status = "executing"
        self._record_event(
            batch.id,
            "execution_started",
            "Apply to WooCommerce started from an approved Dry Run.",
            metadata={"approved_by": batch.approved_by, "requested_by": user.username},
            commit=False,
        )
        self.db.commit()

        success_count = 0
        failure_count = 0
        for item in batch.items:
            try:
                provider_result = await self._execute_woocommerce_price_update(item)
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
                    metadata={"provider": exc.provider, "http_status": exc.http_status},
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
                    metadata={"provider": ALLOWED_CHANNEL_TYPE},
                    commit=False,
                )
            else:
                success_count += 1
                item.status = "applied"
                item.provider_result_json = provider_result
                self._record_event(
                    batch.id,
                    "item_applied",
                    "WooCommerce price update applied.",
                    item_id=item.id,
                    metadata={"provider": ALLOWED_CHANNEL_TYPE, "stock_update": False},
                    commit=False,
                )

        batch.executed_at = datetime.utcnow()
        batch.status = "applied" if failure_count == 0 else "partially_failed" if success_count else "failed"
        self._record_event(
            batch.id,
            "execution_finished",
            "Apply to WooCommerce finished.",
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

    async def _execute_woocommerce_price_update(self, item: WriteItem) -> dict:
        auth = AuthConfig(
            auth_type="api_key",
            credentials={
                "url": self.config.get("woocommerce.url") or "",
                "key": self.config.get("woocommerce.key") or "",
                "secret": self.config.get("woocommerce.secret") or "",
            },
        )
        connector = WooCommerceConnector()
        await connector.connect(auth)
        return await connector.update_price(int(item.channel_product_id), item.proposed_price)

    def _validate_scope(self, channel_id: str, operation_type: str) -> None:
        prefix = channel_id.split(":", 1)[0].lower()
        if prefix in BLOCKED_CHANNEL_PREFIXES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This channel is not write-enabled in FlowHub 1.0.0.")
        if channel_id != ALLOWED_CHANNEL_ID:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "FlowHub 1.0.0 only supports WooCommerce price updates.")
        if operation_type != ALLOWED_OPERATION:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only price updates are supported. Stock updates are blocked.")

    def _validate_changes(self, raw_changes: list[dict]) -> dict:
        if len(raw_changes) > MAX_ITEMS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Dry Run is limited to {MAX_ITEMS} items.")
        currencies: set[str] = set()
        max_delta = 0.0
        for change in raw_changes:
            forbidden = FORBIDDEN_STOCK_KEYS.intersection({key.lower() for key in change})
            if forbidden:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Stock updates are blocked in FlowHub 1.0.0.")
            product_id = str(change.get("productId") or "")
            if not product_id.isdigit():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "WooCommerce product ID must be numeric.")
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
        if len(currencies) > 1:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dry Run must use a single currency.")
        return {
            "operation": ALLOWED_OPERATION,
            "channel_id": ALLOWED_CHANNEL_ID,
            "item_count": len(raw_changes),
            "max_delta_percent": round(max_delta, 4),
            "stock_update_allowed": False,
            "scheduler_started": False,
            "automatic_apply": False,
            "marketplace_writes_limited_to": [ALLOWED_CHANNEL_TYPE],
        }

    def _validate_batch_scope(self, batch: WriteBatch) -> None:
        self._validate_scope(batch.channel_id, batch.operation_type)
        if batch.channel_type != ALLOWED_CHANNEL_TYPE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Batch channel adapter is not enabled for writes.")

    def _get_batch(self, batch_id: str) -> WriteBatch:
        row = self.db.get(WriteBatch, batch_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Dry Run not found.")
        return row

    def _batch_hash(self, body: WritePipelineDryRunRequest) -> str:
        parts = [body.channelId, body.operationType]
        for item in body.changes:
            parts.append(f"{item.productId}|{item.currentPrice:.4f}|{item.proposedPrice:.4f}|{item.currency}")
        return sha256("\n".join(parts).encode("utf-8")).hexdigest()

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
            metadata_json=metadata or {},
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
