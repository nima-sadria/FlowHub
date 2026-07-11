"""Order synchronization service for marketplace channels."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import ChannelOrder, ChannelOrderEvent, CursorPagination, PageNumberPagination, PaginatedResult
from app.flowhub.orders.models import (
    ChannelInventoryEffectRecord,
    ChannelInvoiceRecord,
    ChannelOrderEventRecord,
    ChannelOrderItemRecord,
    ChannelOrderRecord,
    ChannelShipmentRecord,
    OrderSyncAuditRecord,
    OrderSyncCheckpoint,
)
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.webhooks.models import WebhookReceipt


SNAPPSHOP_STATUS_MAP = {
    "NEW_ORDER": "new",
    "CANCELLATION": "cancelled",
    "CHANGE_STATUS": "updated",
    "DELIVERED": "fulfilled",
    "CANCELLED": "cancelled",
    "CANCELED": "cancelled",
}
TAPSISHOP_STATUS_MAP = {
    "1": "new",
    "2": "processing",
    "3": "fulfilled",
    "4": "cancelled",
    "PURCHASE": "new",
    "CANCELLATION": "cancelled",
}
LOCK_TTL_SECONDS = 15 * 60
CHANNEL_LEASE_SOURCE = "__channel_lease__"


@dataclass(frozen=True)
class OrderSyncResult:
    channel_id: str
    source: str
    processed: int
    duplicates: int
    effects_created: int
    cursor: str | None = None
    state: str = "completed"


@dataclass(frozen=True)
class OrderSyncLease:
    checkpoint_id: int
    channel_id: str
    source: str
    owner: str
    acquired_at: datetime
    expires_at: datetime


class OrderSyncService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_order(
        self,
        order: ChannelOrder,
        *,
        source: str,
        source_event_id: str | None = None,
        event_type: str | None = None,
        occurred_at: datetime | None = None,
        commit: bool = True,
    ) -> ChannelOrderRecord:
        provider_order_id = _provider_order_id(order)
        raw_hash = _hash(order.raw)
        raw_summary = _order_summary(order)
        now = datetime.utcnow()
        existing = (
            self.db.query(ChannelOrderRecord)
            .filter_by(channel_id=order.channel_id, provider_order_id=provider_order_id)
            .first()
        )
        incoming_version = _parse_dt(order.updated_at) or occurred_at or _parse_dt(order.created_at)
        if existing is None:
            existing = ChannelOrderRecord(
                channel_id=order.channel_id,
                connector_type=order.connector_type,
                provider_order_id=provider_order_id,
                first_seen_at=now,
            )
            self.db.add(existing)
        elif existing.last_provider_event_at and incoming_version and incoming_version < existing.last_provider_event_at:
            self._audit(
                order.channel_id,
                order.connector_type,
                existing.internal_id,
                "order_out_of_order_event_ignored",
                "Older provider order event was recorded without overwriting normalized order state.",
                {"source_event_id": source_event_id, "incoming_at": _iso(incoming_version), "current_at": _iso(existing.last_provider_event_at)},
            )
            if commit:
                self.db.commit()
                self.db.refresh(existing)
            return existing

        provider_status = order.status or "UNKNOWN"
        existing.order_number = order.identifiers.order_number
        existing.provider_status = provider_status
        existing.normalized_status = _normalize_status(order.connector_type, event_type or provider_status)
        existing.created_at_provider = _parse_dt(order.created_at)
        existing.updated_at_provider = _parse_dt(order.updated_at) or incoming_version
        existing.delivery_type = _str_from_raw(order.raw, "delivery_type", "deliveryMethod", "delivery_method")
        existing.currency = order.currency
        existing.original_amount = _float_from_raw(order.raw, "original_amount", "originalAmount", "original_price")
        existing.final_amount = order.total
        existing.service_fee = _float_from_raw(order.raw, "service_fee", "serviceFee")
        existing.discount_amount = _float_from_raw(order.raw, "discount_amount", "discountAmount")
        existing.customer_reference = _customer_reference(order.raw)
        existing.raw_hash = raw_hash
        existing.raw_summary_json = raw_summary
        existing.last_seen_at = now
        existing.last_provider_event_at = incoming_version or now
        existing.synchronization_state = "synced"
        existing.event_source = source
        existing.error_state = None
        self.db.flush()
        self._replace_items(existing, order)
        self._replace_shipments(existing, order.raw)
        self._replace_invoices(existing, order.raw, order.currency)
        effects = self._create_inventory_effects(existing, order, source_event_id=source_event_id, event_type=event_type)
        self._audit(
            order.channel_id,
            order.connector_type,
            existing.internal_id,
            "order_normalized",
            "Provider order normalized. Product prices and canonical inventory were not changed.",
            {"source": source, "source_event_id": source_event_id, "inventory_effects_created": effects, "price_write_performed": False},
        )
        if commit:
            self.db.commit()
            self.db.refresh(existing)
        return existing

    async def sync_snappshop_events(
        self,
        channel_id: str,
        connector: Any,
        *,
        limit_pages: int = 10,
        lease_seconds: int = LOCK_TTL_SECONDS,
        interval_seconds: int | None = None,
    ) -> OrderSyncResult:
        lease = self.acquire_checkpoint_lease(
            channel_id,
            "snappshop",
            "snappshop_events",
            lease_seconds=lease_seconds,
            interval_seconds=interval_seconds,
        )
        checkpoint = self._ensure_checkpoint(channel_id, "snappshop", "snappshop_events", interval_seconds=interval_seconds)
        processed = 0
        duplicates = 0
        effects_before = self.db.query(ChannelInventoryEffectRecord).filter_by(channel_id=channel_id).count()
        cursor = checkpoint.cursor
        try:
            for _ in range(max(1, limit_pages)):
                self.heartbeat_checkpoint_lease(lease, lease_seconds=lease_seconds)
                page = await connector.list_order_events(CursorPagination(cursor=cursor, limit=50))
                if not isinstance(page, PaginatedResult):
                    raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Connector returned malformed order event page.")
                for event in page.items:
                    if not isinstance(event, ChannelOrderEvent):
                        continue
                    if self._record_event(event, source="snappshop_poll"):
                        duplicates += 1
                        continue
                    order = await self._order_for_event(connector, event)
                    self.upsert_order(
                        order,
                        source="snappshop_poll",
                        source_event_id=event.event_id,
                        event_type=event.event_type,
                        occurred_at=_parse_dt(event.occurred_at),
                        commit=False,
                    )
                    processed += 1
                pagination = page.pagination
                next_cursor = pagination.next_cursor if isinstance(pagination, CursorPagination) else None
                checkpoint.cursor = next_cursor
                checkpoint.last_run_at = datetime.utcnow()
                checkpoint.last_success_at = checkpoint.last_run_at
                checkpoint.last_failure_category = None
                checkpoint.next_run_at = checkpoint.last_run_at + timedelta(seconds=checkpoint.interval_seconds)
                checkpoint.updated_at = datetime.utcnow()
                if hasattr(connector, "acknowledge_order_events"):
                    connector.acknowledge_order_events(page)
                self._commit_checkpoint_progress(checkpoint, lease)
                cursor = next_cursor
                if not isinstance(pagination, CursorPagination) or not pagination.has_more:
                    break
            effects_after = self.db.query(ChannelInventoryEffectRecord).filter_by(channel_id=channel_id).count()
            return OrderSyncResult(channel_id, "snappshop_events", processed, duplicates, effects_after - effects_before, cursor)
        except Exception:
            self._mark_checkpoint_failure(lease, "sync_failed")
            raise
        finally:
            self.release_checkpoint_lease(lease)

    async def process_tapsishop_webhook_receipts(
        self,
        channel_id: str,
        connector: Any | None = None,
        *,
        limit: int = 100,
        lease_seconds: int = LOCK_TTL_SECONDS,
    ) -> OrderSyncResult:
        lease = self.acquire_checkpoint_lease(
            channel_id,
            "tapsishop",
            "tapsishop_webhook",
            lease_seconds=lease_seconds,
        )
        try:
            receipts = (
                self.db.query(WebhookReceipt)
                .filter(WebhookReceipt.channel_id == channel_id, WebhookReceipt.provider == "tapsishop")
                .filter(WebhookReceipt.processing_state.in_(["queued", "retry_scheduled"]))
                .order_by(WebhookReceipt.received_at.asc(), WebhookReceipt.id.asc())
                .limit(limit)
                .all()
            )
            processed = 0
            duplicates = 0
            effects_before = self.db.query(ChannelInventoryEffectRecord).filter_by(channel_id=channel_id).count()
            for receipt in receipts:
                self.heartbeat_checkpoint_lease(lease, lease_seconds=lease_seconds)
                normalized = receipt.normalized_event_json or {}
                event = _event_from_tapsishop_receipt(receipt)
                if self._record_event(event, source="tapsishop_webhook"):
                    duplicates += 1
                    receipt.processing_state = "processed"
                    receipt.processed_at = datetime.utcnow()
                    continue
                order = await self._order_for_tapsishop_receipt(receipt.channel_id, normalized, connector)
                self.upsert_order(
                    order,
                    source="tapsishop_webhook",
                    source_event_id=receipt.provider_event_id,
                    event_type=event.event_type,
                    occurred_at=_parse_dt(event.occurred_at),
                    commit=False,
                )
                receipt.processing_state = "processed"
                receipt.processed_at = datetime.utcnow()
                receipt.last_error_category = None
                processed += 1
            checkpoint = self._ensure_checkpoint(channel_id, "tapsishop", "tapsishop_webhook")
            now = datetime.utcnow()
            checkpoint.last_run_at = now
            checkpoint.last_success_at = now
            checkpoint.last_failure_category = None
            checkpoint.next_run_at = now
            checkpoint.updated_at = now
            self._commit_checkpoint_progress(checkpoint, lease)
            effects_after = self.db.query(ChannelInventoryEffectRecord).filter_by(channel_id=channel_id).count()
            return OrderSyncResult(channel_id, "tapsishop_webhook", processed, duplicates, effects_after - effects_before)
        except Exception:
            self._mark_checkpoint_failure(lease, "webhook_processing_failed")
            raise
        finally:
            self.release_checkpoint_lease(lease)

    async def reconcile_recent_orders(
        self,
        channel_id: str,
        connector: Any,
        *,
        page_size: int = 50,
        lease_seconds: int = LOCK_TTL_SECONDS,
        interval_seconds: int | None = None,
    ) -> OrderSyncResult:
        lease = self.acquire_checkpoint_lease(
            channel_id,
            getattr(connector, "connector_type", channel_id.split(":", 1)[0]),
            "reconciliation",
            lease_seconds=lease_seconds,
            interval_seconds=interval_seconds,
        )
        processed = 0
        try:
            self.heartbeat_checkpoint_lease(lease, lease_seconds=lease_seconds)
            page = await connector.list_orders(PageNumberPagination(page=1, page_size=page_size))
            for item in page.items:
                if not isinstance(item, ChannelOrder):
                    continue
                before = (
                    self.db.query(ChannelOrderRecord)
                    .filter_by(channel_id=channel_id, provider_order_id=_provider_order_id(item))
                    .first()
                )
                row = self.upsert_order(item, source="reconciliation", source_event_id=f"reconcile:{_provider_order_id(item)}", commit=False)
                if before is None or before.raw_hash != row.raw_hash:
                    self._audit(channel_id, item.connector_type, row.internal_id, "order_reconciliation_repair", "Reconciliation repaired missing or stale order state.", {})
                processed += 1
            checkpoint = self._ensure_checkpoint(channel_id, getattr(connector, "connector_type", channel_id.split(":", 1)[0]), "reconciliation", interval_seconds=interval_seconds)
            now = datetime.utcnow()
            checkpoint.last_run_at = now
            checkpoint.last_success_at = now
            checkpoint.last_failure_category = None
            checkpoint.next_run_at = now + timedelta(seconds=checkpoint.interval_seconds)
            checkpoint.updated_at = now
            self._commit_checkpoint_progress(checkpoint, lease)
            return OrderSyncResult(channel_id, "reconciliation", processed, 0, 0)
        except Exception:
            self._mark_checkpoint_failure(lease, "reconciliation_failed")
            raise
        finally:
            self.release_checkpoint_lease(lease)

    def list_orders(self, *, page: int = 1, page_size: int = 50, channel_id: str | None = None) -> dict:
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        query = self.db.query(ChannelOrderRecord)
        if channel_id:
            query = query.filter(ChannelOrderRecord.channel_id == channel_id)
        total = query.count()
        rows = (
            query.order_by(ChannelOrderRecord.last_seen_at.desc(), ChannelOrderRecord.internal_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {"items": [self._order_shape(row, include_detail=False) for row in rows], "total": total, "page": page, "pageSize": page_size}

    def get_order(self, internal_id: int) -> dict:
        row = self.db.get(ChannelOrderRecord, internal_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
        return self._order_shape(row, include_detail=True)

    def acquire_checkpoint_lease(
        self,
        channel_id: str,
        connector_type: str,
        source: str,
        *,
        lease_seconds: int = LOCK_TTL_SECONDS,
        interval_seconds: int | None = None,
        owner: str | None = None,
    ) -> OrderSyncLease:
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=max(1, lease_seconds))
        owner = owner or str(uuid.uuid4())
        checkpoint = self._ensure_checkpoint(channel_id, connector_type, CHANNEL_LEASE_SOURCE, interval_seconds=interval_seconds)

        values = {
            "locked_at": now,
            "lock_owner": owner,
            "lease_expires_at": expires_at,
            "lease_heartbeat_at": now,
            "last_run_id": owner,
            "updated_at": now,
        }
        if interval_seconds is not None:
            values["interval_seconds"] = max(1, int(interval_seconds))

        rowcount = (
            self.db.query(OrderSyncCheckpoint)
            .filter(OrderSyncCheckpoint.id == checkpoint.id)
            .filter(or_(OrderSyncCheckpoint.lease_expires_at.is_(None), OrderSyncCheckpoint.lease_expires_at <= now))
            .update(values, synchronize_session=False)
        )
        if rowcount != 1:
            self.db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Order synchronization is already running for this channel.")
        self.db.commit()
        return OrderSyncLease(checkpoint.id, channel_id, source, owner, now, expires_at)

    def _ensure_checkpoint(
        self,
        channel_id: str,
        connector_type: str,
        source: str,
        *,
        interval_seconds: int | None = None,
    ) -> OrderSyncCheckpoint:
        checkpoint = self.db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id, source=source).first()
        if checkpoint is not None:
            if interval_seconds is not None and checkpoint.interval_seconds != max(1, int(interval_seconds)):
                checkpoint.interval_seconds = max(1, int(interval_seconds))
                checkpoint.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(checkpoint)
            return checkpoint
        checkpoint = OrderSyncCheckpoint(channel_id=channel_id, connector_type=connector_type, source=source)
        if interval_seconds is not None:
            checkpoint.interval_seconds = max(1, int(interval_seconds))
        self.db.add(checkpoint)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            checkpoint = self.db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id, source=source).one()
        return checkpoint

    def heartbeat_checkpoint_lease(self, lease: OrderSyncLease, *, lease_seconds: int = LOCK_TTL_SECONDS) -> None:
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=max(1, lease_seconds))
        rowcount = (
            self.db.query(OrderSyncCheckpoint)
            .filter(OrderSyncCheckpoint.id == lease.checkpoint_id, OrderSyncCheckpoint.lock_owner == lease.owner)
            .update({"lease_heartbeat_at": now, "lease_expires_at": expires_at, "updated_at": now}, synchronize_session=False)
        )
        if rowcount != 1:
            self.db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Order synchronization lease is no longer owned by this runner.")
        self.db.commit()

    def release_checkpoint_lease(self, lease: OrderSyncLease) -> bool:
        rowcount = (
            self.db.query(OrderSyncCheckpoint)
            .filter(OrderSyncCheckpoint.id == lease.checkpoint_id, OrderSyncCheckpoint.lock_owner == lease.owner)
            .update(
                {
                    "locked_at": None,
                    "lock_owner": None,
                    "lease_expires_at": None,
                    "lease_heartbeat_at": None,
                    "updated_at": datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        self.db.commit()
        return rowcount == 1

    def _commit_checkpoint_progress(self, checkpoint: OrderSyncCheckpoint, lease: OrderSyncLease) -> None:
        current = self.db.get(OrderSyncCheckpoint, lease.checkpoint_id)
        if current is None or current.lock_owner != lease.owner:
            self.db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Order synchronization lease is no longer owned by this runner.")
        self.db.commit()

    def _mark_checkpoint_failure(self, lease: OrderSyncLease, category: str) -> None:
        try:
            self.db.rollback()
            now = datetime.utcnow()
            (
                self.db.query(OrderSyncCheckpoint)
                .filter(OrderSyncCheckpoint.id == lease.checkpoint_id, OrderSyncCheckpoint.lock_owner == lease.owner)
                .update(
                    {"last_failure_at": now, "last_failure_category": category, "updated_at": now},
                    synchronize_session=False,
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _record_event(self, event: ChannelOrderEvent, *, source: str) -> bool:
        if self.db.query(ChannelOrderEventRecord).filter_by(channel_id=event.channel_id, provider_event_id=event.event_id).first():
            return True
        row = ChannelOrderEventRecord(
            channel_id=event.channel_id,
            connector_type=event.connector_type,
            provider_event_id=event.event_id,
            provider_order_id=event.order_identifiers.external_product_id,
            order_number=event.order_identifiers.order_number,
            event_type=event.event_type,
            normalized_event_type=_normalize_event_type(event.connector_type, event.event_type),
            occurred_at=_parse_dt(event.occurred_at),
            source=source,
            raw_hash=_hash(event.raw),
            raw_summary_json=redact_sensitive(_compact(event.raw)),
            state="accepted",
        )
        self.db.add(row)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return True
        return False

    async def _order_for_event(self, connector: Any, event: ChannelOrderEvent) -> ChannelOrder:
        order_number = event.order_identifiers.order_number
        external_id = event.order_identifiers.external_product_id
        return await connector.get_order({"order_number": order_number or "", "id": external_id or order_number or ""})

    async def _order_for_tapsishop_receipt(self, channel_id: str, normalized: dict, connector: Any | None) -> ChannelOrder:
        order_id = str(normalized.get("orderId") or normalized.get("orderDetail", {}).get("orderId"))
        if connector is not None:
            try:
                return await connector.get_order({"id": order_id, "orderId": order_id})
            except Exception:
                pass
        detail = normalized.get("orderDetail") if isinstance(normalized.get("orderDetail"), dict) else {}
        items = []
        from app.flowhub.channels.contracts import ChannelIdentifierSet, ChannelOrderItem
        for item in normalized.get("items", []):
            if not isinstance(item, dict):
                continue
            items.append(ChannelOrderItem(
                identifiers=ChannelIdentifierSet(
                    external_product_id=_to_str(item.get("productId")),
                    sku=_to_str(item.get("sku")),
                    channel_reference_code=_to_str(item.get("orderItemId")),
                ),
                name=_to_str(item.get("sku")) or "",
                quantity=float(item.get("quantity") or 0),
                unit_price=_to_float(item.get("price")),
                currency="IRR",
                raw=item,
            ))
        return ChannelOrder(
            channel_id=channel_id,
            connector_type="tapsishop",
            identifiers=ChannelIdentifierSet(external_product_id=order_id, order_number=_to_str(detail.get("orderNumber"))),
            status=_to_str(detail.get("status")) or _to_str(normalized.get("changeType")) or "UNKNOWN",
            created_at=_to_str(normalized.get("occurredAt") or detail.get("effectiveDate")),
            updated_at=_to_str(normalized.get("occurredAt") or detail.get("effectiveDate")),
            items=items,
            total=None,
            currency="IRR",
            raw=normalized,
        )

    def _replace_items(self, row: ChannelOrderRecord, order: ChannelOrder) -> None:
        self.db.query(ChannelOrderItemRecord).filter_by(order_id=row.internal_id).delete()
        for index, item in enumerate(order.items):
            raw = item.raw or {}
            provider_item_id = (
                item.identifiers.channel_reference_code
                or _to_str(raw.get("orderItemId") or raw.get("order_item_id") or raw.get("id") or raw.get("vendor_product_info_id"))
                or f"{row.provider_order_id}:item:{index}"
            )
            self.db.add(ChannelOrderItemRecord(
                order_id=row.internal_id,
                provider_item_id=provider_item_id,
                external_product_id=item.identifiers.external_product_id,
                sku=item.identifiers.sku,
                product_number=item.identifiers.product_number,
                parent_product_number=item.identifiers.parent_product_number,
                name=item.name,
                quantity=item.quantity,
                canceled_quantity=_to_float(raw.get("canceled_quantity") or raw.get("total_canceled_quantity")) or 0,
                deliverable_quantity=_to_float(raw.get("deliverable_quantity")),
                original_price=_to_float(raw.get("original_price") or raw.get("originalPrice") or item.unit_price),
                final_price=_to_float(raw.get("final_price") or raw.get("finalPrice") or item.unit_price),
                item_status=_to_str(raw.get("item_status") or raw.get("status") or raw.get("statusCode")),
                cancellation_reason=_to_str(raw.get("cancellation_reason") or raw.get("cancellationReason")),
                raw_summary_json=redact_sensitive(_compact(raw)),
            ))

    def _replace_shipments(self, row: ChannelOrderRecord, raw: dict) -> None:
        self.db.query(ChannelShipmentRecord).filter_by(order_id=row.internal_id).delete()
        values = raw.get("shipments") or raw.get("shipment") or raw.get("bundles") or []
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            return
        for index, shipment in enumerate(values):
            if not isinstance(shipment, dict):
                continue
            number = _to_str(shipment.get("shipmentNumber") or shipment.get("bundleId") or shipment.get("id")) or f"{row.provider_order_id}:shipment:{index}"
            self.db.add(ChannelShipmentRecord(
                order_id=row.internal_id,
                shipment_number=number,
                status_code=_to_str(shipment.get("statusCode") or shipment.get("shippingStatusType")),
                status_title=_to_str(shipment.get("statusTitle") or shipment.get("status")),
                delivery_method=_to_str(shipment.get("deliveryMethod") or shipment.get("delivery_method")),
                pickup_or_send_window=_to_str(shipment.get("pickupWindow") or shipment.get("sendWindow")),
                raw_summary_json=redact_sensitive(_compact(shipment)),
            ))

    def _replace_invoices(self, row: ChannelOrderRecord, raw: dict, currency: str | None) -> None:
        self.db.query(ChannelInvoiceRecord).filter_by(order_id=row.internal_id).delete()
        values = raw.get("invoices") or raw.get("invoice") or []
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list):
            return
        for index, invoice in enumerate(values):
            if not isinstance(invoice, dict):
                continue
            number = _to_str(invoice.get("invoiceNumber") or invoice.get("number") or invoice.get("id")) or f"{row.provider_order_id}:invoice:{index}"
            self.db.add(ChannelInvoiceRecord(
                order_id=row.internal_id,
                invoice_number=number,
                amount=_to_float(invoice.get("amount") or invoice.get("total")),
                currency=_to_str(invoice.get("currency")) or currency,
                raw_summary_json=redact_sensitive(_compact(invoice)),
            ))

    def _create_inventory_effects(self, row: ChannelOrderRecord, order: ChannelOrder, *, source_event_id: str | None, event_type: str | None) -> int:
        if not source_event_id:
            return 0
        normalized = _normalize_event_type(order.connector_type, event_type or order.status)
        if normalized not in {"purchase", "cancellation"}:
            return 0
        created = 0
        sign = -1 if normalized == "purchase" else 1
        for index, item in enumerate(order.items):
            raw = item.raw or {}
            provider_item_id = (
                item.identifiers.channel_reference_code
                or _to_str(raw.get("orderItemId") or raw.get("id") or raw.get("vendor_product_info_id"))
                or f"{row.provider_order_id}:item:{index}"
            )
            qty = item.quantity
            if normalized == "cancellation":
                qty = _to_float(raw.get("canceled_quantity") or raw.get("total_canceled_quantity")) or item.quantity
            effect = ChannelInventoryEffectRecord(
                channel_id=order.channel_id,
                order_id=row.internal_id,
                source_event_id=source_event_id,
                provider_item_id=provider_item_id,
                sku=item.identifiers.sku,
                external_product_id=item.identifiers.external_product_id,
                effect_type=normalized,
                quantity_delta=sign * float(qty or 0),
                applied_to_canonical_inventory=False,
                state="proposed",
            )
            exists = (
                self.db.query(ChannelInventoryEffectRecord)
                .filter_by(
                    channel_id=order.channel_id,
                    source_event_id=source_event_id,
                    provider_item_id=provider_item_id,
                    effect_type=normalized,
                )
                .first()
            )
            if exists is not None:
                continue
            self.db.add(effect)
            self.db.flush()
            created += 1
        return created

    def _audit(self, channel_id: str, connector_type: str, order_id: int | None, event_name: str, message: str, metadata: dict) -> None:
        self.db.add(OrderSyncAuditRecord(
            channel_id=channel_id,
            connector_type=connector_type,
            order_id=order_id,
            event_name=event_name,
            message=message,
            metadata_json=redact_sensitive(metadata),
        ))

    def _order_shape(self, row: ChannelOrderRecord, *, include_detail: bool) -> dict:
        shape = {
            "internalId": row.internal_id,
            "channelId": row.channel_id,
            "connectorType": row.connector_type,
            "providerOrderId": row.provider_order_id,
            "orderNumber": row.order_number,
            "providerStatus": row.provider_status,
            "normalizedStatus": row.normalized_status,
            "createdAtProvider": _iso(row.created_at_provider),
            "updatedAtProvider": _iso(row.updated_at_provider),
            "currency": row.currency,
            "finalAmount": row.final_amount,
            "itemCount": self.db.query(ChannelOrderItemRecord).filter_by(order_id=row.internal_id).count(),
            "synchronizationState": row.synchronization_state,
            "eventSource": row.event_source,
            "errorState": row.error_state,
            "lastSeenAt": _iso(row.last_seen_at),
        }
        if not include_detail:
            return shape
        shape["items"] = [
            {
                "providerItemId": item.provider_item_id,
                "externalProductId": item.external_product_id,
                "sku": item.sku,
                "productNumber": item.product_number,
                "parentProductNumber": item.parent_product_number,
                "name": item.name,
                "quantity": item.quantity,
                "canceledQuantity": item.canceled_quantity,
                "deliverableQuantity": item.deliverable_quantity,
                "originalPrice": item.original_price,
                "finalPrice": item.final_price,
                "itemStatus": item.item_status,
                "cancellationReason": item.cancellation_reason,
            }
            for item in self.db.query(ChannelOrderItemRecord).filter_by(order_id=row.internal_id).all()
        ]
        shape["shipments"] = [
            {
                "shipmentNumber": item.shipment_number,
                "statusCode": item.status_code,
                "statusTitle": item.status_title,
                "deliveryMethod": item.delivery_method,
                "pickupOrSendWindow": item.pickup_or_send_window,
            }
            for item in self.db.query(ChannelShipmentRecord).filter_by(order_id=row.internal_id).all()
        ]
        shape["invoices"] = [
            {"invoiceNumber": item.invoice_number, "amount": item.amount, "currency": item.currency}
            for item in self.db.query(ChannelInvoiceRecord).filter_by(order_id=row.internal_id).all()
        ]
        shape["timeline"] = [
            {"eventName": item.event_name, "message": item.message, "createdAt": _iso(item.created_at), "metadata": item.metadata_json}
            for item in self.db.query(OrderSyncAuditRecord).filter_by(order_id=row.internal_id).order_by(OrderSyncAuditRecord.created_at.asc()).all()
        ]
        return shape


def _event_from_tapsishop_receipt(receipt: WebhookReceipt) -> ChannelOrderEvent:
    from app.flowhub.channels.contracts import ChannelIdentifierSet

    payload = receipt.normalized_event_json or {}
    detail = payload.get("orderDetail") if isinstance(payload.get("orderDetail"), dict) else {}
    change_type = str(payload.get("changeType") or "")
    return ChannelOrderEvent(
        channel_id=receipt.channel_id,
        connector_type="tapsishop",
        event_id=receipt.provider_event_id,
        event_type="PURCHASE" if change_type == "1" else "CANCELLATION" if change_type == "2" else change_type,
        occurred_at=_to_str(payload.get("occurredAt") or detail.get("effectiveDate")),
        order_identifiers=ChannelIdentifierSet(external_product_id=_to_str(payload.get("orderId")), order_number=_to_str(detail.get("orderNumber"))),
        raw=payload,
    )


def _provider_order_id(order: ChannelOrder) -> str:
    return (
        order.identifiers.external_product_id
        or order.identifiers.channel_reference_code
        or order.identifiers.order_number
        or _to_str(order.raw.get("id") if isinstance(order.raw, dict) else None)
        or _to_str(order.raw.get("orderId") if isinstance(order.raw, dict) else None)
        or _to_str(order.raw.get("order_number") if isinstance(order.raw, dict) else None)
        or "unknown"
    )


def _normalize_status(connector_type: str, status_value: str) -> str:
    key = str(status_value or "").upper()
    if connector_type == "snappshop":
        return SNAPPSHOP_STATUS_MAP.get(key, key.lower() or "unknown")
    return TAPSISHOP_STATUS_MAP.get(key, key.lower() or "unknown")


def _normalize_event_type(connector_type: str, event_type: str) -> str:
    key = str(event_type or "").upper()
    if connector_type == "snappshop":
        if key == "NEW_ORDER":
            return "purchase"
        if key == "CANCELLATION":
            return "cancellation"
        if key == "CHANGE_STATUS":
            return "status_change"
    if key in {"1", "PURCHASE", "NEW_ORDER"}:
        return "purchase"
    if key in {"2", "CANCELLATION", "CANCELLED", "CANCELED"}:
        return "cancellation"
    return "status_change"


def _hash(value: Any) -> str:
    return sha256(json.dumps(value or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _compact(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "id", "orderId", "orderNumber", "order_number", "status", "stateCode", "stateTitle",
        "event_type", "event_id", "changeType", "created_at", "updated_at", "event_at",
        "sku", "productId", "vendor_product_info_id", "product_number", "parent_product_number",
        "quantity", "canceled_quantity", "total_canceled_quantity", "deliverable_quantity",
        "final_price", "finalPrice", "item_status",
    }
    return {k: v for k, v in value.items() if k in allowed}


def _order_summary(order: ChannelOrder) -> dict:
    return redact_sensitive({
        "providerOrderId": _provider_order_id(order),
        "orderNumber": order.identifiers.order_number,
        "status": order.status,
        "createdAt": order.created_at,
        "updatedAt": order.updated_at,
        "itemCount": len(order.items),
        "total": order.total,
        "currency": order.currency,
    })


def _customer_reference(raw: dict) -> str | None:
    if not isinstance(raw, dict):
        return None
    customer = raw.get("customer") if isinstance(raw.get("customer"), dict) else raw.get("customerInfo")
    if not isinstance(customer, dict):
        return None
    seed = "|".join(str(customer.get(key) or "") for key in ("id", "customerId", "phone", "nationalId", "nationalCode"))
    return sha256(seed.encode("utf-8")).hexdigest()[:32] if seed.strip("|") else None


def _str_from_raw(raw: dict, *keys: str) -> str | None:
    if not isinstance(raw, dict):
        return None
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _float_from_raw(raw: dict, *keys: str) -> float | None:
    if not isinstance(raw, dict):
        return None
    for key in keys:
        value = _to_float(raw.get(key))
        if value is not None:
            return value
    return None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _to_str(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
