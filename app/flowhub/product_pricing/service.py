"""Protected multi-channel product price workflow."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelIdentifierSet,
    ChannelProductUpdate,
)
from app.flowhub.channels.registry import default_marketplace_registry
from app.flowhub.channels.snappshop import SnappShopConnectorError
from app.flowhub.channels.tapsishop import TapsiShopConnectorError
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.product_pricing.models import ProductPriceOperation, ProductPriceOperationItem
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.security.upstream_errors import normalize_upstream_error
from app.flowhub.setup.service import AppConfigService
from app.flowhub.write_pipeline.adapters import ChannelWriteContext

CHANNELS = (
    ("woocommerce:primary", "WooCommerce", "woocommerce", "store currency"),
    ("snappshop:main", "Snapp Shop", "snappshop", "toman"),
    ("tapsishop:main", "Tapsi Shop", "tapsishop", "rial"),
)
CHANNEL_CAPABILITY = {
    "woocommerce:primary": ChannelCapability.PRODUCTS_WRITE_PRICE,
    "snappshop:main": ChannelCapability.PRODUCTS_WRITE_PRICE,
    "tapsishop:main": ChannelCapability.PRODUCTS_WRITE_PRICE,
}


@dataclass(frozen=True)
class PriceProposal:
    channel_id: str
    proposed_value: float
    unit: str | None
    stale_token: str
    special_price: float | None = None


class ProductPricingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)
        self.integration = IntegrationPlatformService(db)

    def load(self, product_id: str) -> dict:
        canonical = self._canonical_row(product_id)
        if canonical is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
        channel_rows = self._channel_rows(canonical)
        channels = [
            self._channel_state(
                channel_id, name, connector_type, unit, channel_rows.get(channel_id)
            )
            for channel_id, name, connector_type, unit in CHANNELS
        ]
        return {
            "product": self._product_identity(canonical),
            "version": self._version(channels),
            "canonical": self._canonical_state(canonical),
            "channels": channels,
            "dryRunRequired": True,
            "applyRequiresApproval": True,
        }

    def validate(self, product_id: str, body: dict) -> dict:
        states = self.load(product_id)
        proposals = self._proposals(body)
        validated = self._validate_proposals(states, proposals, persist=False)
        return {**states, "channels": validated, "status": "validated"}

    def dry_run(self, product_id: str, body: dict, user: FlowHubUser) -> dict:
        states = self.load(product_id)
        proposals = self._proposals(body)
        if str(body.get("version") or "") != states["version"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "STALE_PRODUCT_PRICE_STATE",
                    "message": "Product channel prices changed after the editor was opened.",
                },
            )
        validated = self._validate_proposals(states, proposals, persist=True)
        changed = [
            item
            for item in validated
            if item["pendingChange"] and item["validationState"] == "valid"
        ]
        if not changed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "No valid channel price changes were submitted.",
            )
        operation_id = f"mcp_{uuid.uuid4().hex[:16]}"
        op = ProductPriceOperation(
            id=operation_id,
            product_id=states["product"]["id"],
            sku=states["product"]["sku"] or "",
            product_name=states["product"]["name"] or "",
            status="dry_run_ready",
            version_token=states["version"],
            created_by=user.username,
            summary_json=self._summary(changed, attempted=False),
        )
        self.db.add(op)
        for item in changed:
            self.db.add(
                ProductPriceOperationItem(
                    operation_id=operation_id,
                    channel_id=item["channelId"],
                    connector_type=item["connectorType"],
                    channel_product_id=item["channelProductId"],
                    sku=item["sku"] or "",
                    current_value=float(item["currentValue"]),
                    proposed_value=float(item["proposedValue"]),
                    currency=item["currency"],
                    unit=item["unit"],
                    outbound_value=float(item["outboundValue"]),
                    outbound_unit=item["outboundUnit"],
                    stale_token=item["staleToken"],
                    status="pending",
                    validation_state=item["validationState"],
                    result_json={"dry_run": True, "external_write": False},
                )
            )
            self._audit(
                "multi_channel_price_dry_run_item",
                "Multi-channel price Dry Run item recorded. No external write was executed.",
                user=user,
                product=states["product"],
                channel=item,
                result="pending",
                upstream_reference=None,
                commit=False,
            )
        self._audit(
            "multi_channel_price_dry_run_created",
            "Multi-channel price Dry Run created. No external write was executed.",
            user=user,
            product=states["product"],
            channel=None,
            result="dry_run_ready",
            upstream_reference=operation_id,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(op)
        return self.operation(operation_id)

    def approve(self, operation_id: str, body: dict, user: FlowHubUser) -> dict:
        op = self._operation(operation_id)
        if op.status != "dry_run_ready":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Only a completed Dry Run can be approved."
            )
        self._assert_still_current(op)
        op.status = "approved"
        op.approved_by = user.username
        op.approved_at = datetime.utcnow()
        op.approval_reason = str(body.get("reason") or "").strip() or None
        self._audit(
            "multi_channel_price_approved",
            "Multi-channel price operation approved. Apply was not started.",
            user=user,
            product=self._operation_product(op),
            channel=None,
            result="approved",
            upstream_reference=op.id,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(op)
        return self.operation(op.id)

    async def apply(self, operation_id: str, user: FlowHubUser) -> dict:
        op = self._operation(operation_id)
        if op.status != "approved":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Apply requires a separate approved Dry Run."
            )
        self._assert_still_current(op)
        product = self._operation_product(op)
        success = 0
        failure = 0
        for item in op.items:
            try:
                result = await self._apply_item(item, user)
            except Exception as exc:
                failure += 1
                item.status = "failed"
                item.error_message = self._safe_error(exc)
                item.result_json = {"success": False, "message": item.error_message}
                self._audit(
                    "multi_channel_price_item_failed",
                    item.error_message,
                    user=user,
                    product=product,
                    channel=self._item_channel_shape(item),
                    result="failed",
                    upstream_reference=None,
                    commit=False,
                )
            else:
                success += 1
                item.status = "applied"
                item.result_json = redact_sensitive(result)
                self._update_cache_after_success(item)
                self._audit(
                    "multi_channel_price_item_applied",
                    "Channel price update applied.",
                    user=user,
                    product=product,
                    channel=self._item_channel_shape(item),
                    result="applied",
                    upstream_reference=_reference(result),
                    commit=False,
                )
        op.applied_at = datetime.utcnow()
        op.status = "applied" if failure == 0 else "partially_failed" if success else "failed"
        op.summary_json = self._operation_summary(op)
        self._audit(
            "multi_channel_price_apply_finished",
            "Multi-channel price Apply finished.",
            user=user,
            product=product,
            channel=None,
            result=op.status,
            upstream_reference=op.id,
            commit=False,
        )
        self.db.commit()
        self.db.refresh(op)
        return self.operation(op.id)

    def operation(self, operation_id: str) -> dict:
        op = self._operation(operation_id)
        return {
            "id": op.id,
            "productId": op.product_id,
            "sku": op.sku,
            "productName": op.product_name,
            "status": op.status,
            "version": op.version_token,
            "createdBy": op.created_by,
            "approvedBy": op.approved_by,
            "approvalReason": op.approval_reason,
            "createdAt": _iso(op.created_at),
            "approvedAt": _iso(op.approved_at),
            "appliedAt": _iso(op.applied_at),
            "summary": self._operation_summary(op),
            "items": [self._operation_item_shape(item) for item in op.items],
            "externalWritePerformed": op.applied_at is not None,
            "applyRequiresApproval": True,
        }

    def _canonical_row(self, product_id: str) -> DlProductCache | None:
        return (
            self.db.query(DlProductCache)
            .filter(DlProductCache.product_id == product_id)
            .order_by(
                (DlProductCache.connector_id == "woocommerce:primary").desc(),
                DlProductCache.id.asc(),
            )
            .first()
        )

    def _channel_rows(self, canonical: DlProductCache) -> dict[str, DlProductCache]:
        rows = (
            self.db.query(DlProductCache)
            .filter(DlProductCache.connector_id.in_([item[0] for item in CHANNELS]))
            .all()
        )
        by_channel: dict[str, DlProductCache] = {}
        for channel_id, *_ in CHANNELS:
            candidates = [row for row in rows if row.connector_id == channel_id]
            exact = next(
                (row for row in candidates if row.product_id == canonical.product_id), None
            )
            sku_match = next(
                (row for row in candidates if canonical.sku and row.sku == canonical.sku), None
            )
            selected = exact or sku_match
            if selected is not None:
                by_channel[channel_id] = selected
        return by_channel

    def _channel_state(
        self,
        channel_id: str,
        name: str,
        connector_type: str,
        default_unit: str,
        row: DlProductCache | None,
    ) -> dict:
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        health = (
            self.db.query(DlConnectorHealth)
            .filter(DlConnectorHealth.connector_id == channel_id)
            .first()
        )
        registry = default_marketplace_registry()
        can_read = registry.supports(channel_id, ChannelCapability.PRODUCTS_READ)
        capability = CHANNEL_CAPABILITY[channel_id]
        can_write_capability = registry.supports(channel_id, capability)
        enabled = bool(instance and instance.enabled)
        read_only = bool(instance.read_only) if instance else True
        can_write = bool(row and enabled and not read_only and can_write_capability)
        connection_state = "disabled" if not enabled else "connected" if row else "disconnected"
        current = _price(row)
        unit = _unit_for_channel(channel_id, self.config.get("server.currency") or "EUR")
        stale_token = _stale_token(row)
        return {
            "channelId": channel_id,
            "channelName": name,
            "connectorType": connector_type,
            "channelProductId": row.product_id if row else "",
            "sku": row.sku if row else "",
            "connectionState": connection_state,
            "healthStatus": health.status if health else "unknown",
            "canRead": can_read,
            "canWrite": can_write,
            "readOnly": read_only,
            "writeCapability": capability.value,
            "currentValue": current,
            "proposedValue": current,
            "currency": _currency_for_channel(
                channel_id, self.config.get("server.currency") or "EUR"
            ),
            "unit": unit,
            "normalizedValue": _normalized_value(channel_id, current),
            "normalizedCurrency": "IRR"
            if channel_id in {"snappshop:main", "tapsishop:main"}
            else (self.config.get("server.currency") or "EUR"),
            "normalizedUnit": "rial"
            if channel_id in {"snappshop:main", "tapsishop:main"}
            else default_unit,
            "freshness": row.freshness if row else "missing",
            "lastSyncedAt": _iso(row.last_successful_read or row.last_fetched_at) if row else None,
            "validationState": "valid" if can_write else "read_only" if row else "disconnected",
            "validationMessage": None
            if can_write
            else "Channel is not writable from this editor."
            if row
            else "Channel has no synchronized product row.",
            "pendingChange": False,
            "staleToken": stale_token,
        }

    def _canonical_state(self, row: DlProductCache) -> dict:
        currency = self.config.get("server.currency") or "EUR"
        value = _price(row)
        return {
            "label": "Canonical/business price",
            "value": value,
            "currency": currency,
            "unit": "store currency",
            "freshness": row.freshness,
            "lastSyncedAt": _iso(row.last_successful_read or row.last_fetched_at),
            "staleToken": _stale_token(row),
        }

    def _product_identity(self, row: DlProductCache) -> dict:
        return {
            "id": row.product_id,
            "name": row.name or row.product_id,
            "sku": row.sku or "",
            "productType": row.product_type or "simple",
            "imageUrl": _image_url(row),
        }

    def _proposals(self, body: dict) -> list[PriceProposal]:
        proposals = []
        for raw in body.get("changes") or []:
            try:
                proposed = float(raw.get("proposedValue"))
            except (TypeError, ValueError):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Price must be numeric."
                ) from None
            special = raw.get("specialPrice")
            try:
                special_value = None if special in (None, "") else float(special)
            except (TypeError, ValueError):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Special price must be numeric."
                ) from None
            proposals.append(
                PriceProposal(
                    channel_id=str(raw.get("channelId") or ""),
                    proposed_value=proposed,
                    unit=str(raw.get("unit") or "").strip() or None,
                    stale_token=str(raw.get("staleToken") or ""),
                    special_price=special_value,
                )
            )
        return proposals

    def _validate_proposals(
        self, states: dict, proposals: list[PriceProposal], *, persist: bool
    ) -> list[dict]:
        by_channel = {item["channelId"]: dict(item) for item in states["channels"]}
        for proposal in proposals:
            state = by_channel.get(proposal.channel_id)
            if state is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown channel: {proposal.channel_id}"
                )
            if proposal.stale_token != state["staleToken"]:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "STALE_CHANNEL_PRICE_STATE",
                        "message": f"{proposal.channel_id} changed after the editor was opened.",
                    },
                )
            errors = []
            if not state["canWrite"]:
                errors.append("Channel is disabled, disconnected, or read-only.")
            proposed_is_finite = math.isfinite(proposal.proposed_value)
            if not proposed_is_finite or proposal.proposed_value < 0:
                errors.append("Price must be numeric and non-negative.")
            elif not proposal.proposed_value.is_integer():
                errors.append("Price must be a whole number.")
            if (
                proposal.special_price is not None
                and proposal.special_price > proposal.proposed_value
            ):
                errors.append("Special price must not exceed regular price.")
            expected_unit = state["unit"]
            if proposal.unit and proposal.unit != expected_unit:
                errors.append(f"Expected {expected_unit} for {proposal.channel_id}.")
            if (
                proposed_is_finite
                and proposal.channel_id == "snappshop:main"
                and int(proposal.proposed_value) != proposal.proposed_value
            ):
                errors.append("SnappShop toman values must be whole numbers.")
            if proposed_is_finite and proposal.channel_id == "tapsishop:main":
                if int(proposal.proposed_value) != proposal.proposed_value:
                    errors.append("TapsiShop rial values must be whole numbers.")
                elif int(proposal.proposed_value) % 10 != 0:
                    errors.append(
                        "TapsiShop rial values must preserve toman/rial precision and be divisible by 10."
                    )
            state["proposedValue"] = proposal.proposed_value
            state["outboundValue"] = (
                proposal.proposed_value
                if errors
                else self._outbound_value(proposal.channel_id, proposal.proposed_value)
            )
            state["outboundUnit"] = _outbound_unit(proposal.channel_id)
            state["normalizedValue"] = _normalized_value(
                proposal.channel_id, proposal.proposed_value
            )
            state["pendingChange"] = (
                state["currentValue"] is None
                or abs(float(state["currentValue"]) - proposal.proposed_value) > 0.0001
            )
            state["validationState"] = "error" if errors else "valid"
            state["validationMessage"] = "; ".join(errors) if errors else None
        return list(by_channel.values())

    def _outbound_value(self, channel_id: str, value: float) -> float:
        if channel_id == "snappshop:main":
            if int(value) != value:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "SnappShop toman values must be integers."
                )
            return value
        if channel_id == "tapsishop:main":
            if int(value) != value:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "TapsiShop rial values must be integers."
                )
            if int(value) % 10 != 0:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "TapsiShop rial values must be divisible by 10.",
                )
            return value
        return value

    def _summary(self, changed: list[dict], *, attempted: bool) -> dict:
        return {
            "total": len(changed),
            "pending": len(changed) if not attempted else 0,
            "success": 0,
            "failed": 0,
            "external_write_performed": attempted,
        }

    def _operation_summary(self, op: ProductPriceOperation) -> dict:
        return {
            "total": len(op.items),
            "pending": sum(1 for item in op.items if item.status == "pending"),
            "success": sum(1 for item in op.items if item.status == "applied"),
            "failed": sum(1 for item in op.items if item.status == "failed"),
            "external_write_performed": op.applied_at is not None,
        }

    async def _apply_item(self, item: ProductPriceOperationItem, user: FlowHubUser) -> dict:
        if item.channel_id == "woocommerce:primary":
            adapter = WooCommercePriceWriteAdapter()
            context = ChannelWriteContext(get_setting=self.config.get, requested_by=user.username)
            transient = _TransientWriteItem(item)
            return await adapter.execute_item(transient, context)
        current = (
            self.db.query(DlProductCache)
            .filter_by(connector_id=item.channel_id, product_id=item.channel_product_id)
            .first()
        )
        update = ChannelProductUpdate(
            channel_id=item.channel_id,
            identifiers=ChannelIdentifierSet(
                external_product_id=item.channel_product_id, sku=item.sku or None
            ),
            price=item.proposed_value,
            stock_quantity=current.stock_qty if current is not None else None,
            currency="TMN" if item.channel_id == "snappshop:main" else "IRR",
            price_unit="toman" if item.channel_id == "snappshop:main" else "rial",
            idempotency_key=f"{item.operation_id}-{item.id}",
        )
        commerce = CommerceHubService(self.db)
        connector = (
            commerce._snappshop_connector()
            if item.channel_id == "snappshop:main"
            else commerce._tapsishop_connector()
        )
        if connector is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Channel connector is not configured.")
        results = await connector.update_products([update])
        result = results[0] if results else None
        if result is None or not result.success:
            message = result.error.message if result and result.error else "Channel update failed."
            raise ConnectorError(
                ConnectorErrorCode.PROVIDER_ERROR, message, provider=item.connector_type
            )
        return result.raw

    def _update_cache_after_success(self, item: ProductPriceOperationItem) -> None:
        row = (
            self.db.query(DlProductCache)
            .filter_by(connector_id=item.channel_id, product_id=item.channel_product_id)
            .first()
        )
        if row is None:
            return
        stored_price = (
            str(int(item.proposed_value))
            if item.proposed_value.is_integer()
            else str(item.proposed_value)
        )
        row.regular_price = stored_price
        row.price = stored_price
        row.freshness = "fresh"
        row.last_successful_read = datetime.utcnow()
        row.record_hash = _row_hash(row)

    def _assert_still_current(self, op: ProductPriceOperation) -> None:
        states = self.load(op.product_id)
        current = {item["channelId"]: item["staleToken"] for item in states["channels"]}
        for item in op.items:
            if current.get(item.channel_id) != item.stale_token:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "STALE_CHANNEL_PRICE_STATE",
                        "message": f"{item.channel_id} changed after Dry Run.",
                    },
                )

    def _operation(self, operation_id: str) -> ProductPriceOperation:
        op = self.db.get(ProductPriceOperation, operation_id)
        if op is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product price operation not found.")
        return op

    def _operation_product(self, op: ProductPriceOperation) -> dict:
        return {"id": op.product_id, "name": op.product_name, "sku": op.sku}

    def _operation_item_shape(self, item: ProductPriceOperationItem) -> dict:
        return {
            "id": item.id,
            "channelId": item.channel_id,
            "connectorType": item.connector_type,
            "channelProductId": item.channel_product_id,
            "sku": item.sku,
            "currentValue": item.current_value,
            "proposedValue": item.proposed_value,
            "currency": item.currency,
            "unit": item.unit,
            "outboundValue": item.outbound_value,
            "outboundUnit": item.outbound_unit,
            "staleToken": item.stale_token,
            "status": item.status,
            "validationState": item.validation_state,
            "errorMessage": item.error_message,
            "result": redact_sensitive(item.result_json or {}),
        }

    def _item_channel_shape(self, item: ProductPriceOperationItem) -> dict:
        return {
            "channelId": item.channel_id,
            "connectorType": item.connector_type,
            "channelProductId": item.channel_product_id,
            "currentValue": item.current_value,
            "proposedValue": item.proposed_value,
            "currency": item.currency,
            "unit": item.unit,
            "outboundValue": item.outbound_value,
            "outboundUnit": item.outbound_unit,
            "staleToken": item.stale_token,
        }

    def _audit(
        self,
        event_name: str,
        message: str,
        *,
        user: FlowHubUser,
        product: dict,
        channel: dict | None,
        result: str,
        upstream_reference: str | None,
        commit: bool,
    ) -> None:
        metadata = {
            "actor": user.username,
            "product": product,
            "channel": channel.get("channelId") if channel else None,
            "previous_value": channel.get("currentValue") if channel else None,
            "proposed_value": channel.get("proposedValue") if channel else None,
            "converted_outbound_value": channel.get("outboundValue") if channel else None,
            "unit": channel.get("unit") if channel else None,
            "result": result,
            "upstream_reference": upstream_reference,
            "timestamp": _iso(datetime.utcnow()),
        }
        self.integration.record_event(
            connector_id=str(channel.get("channelId") if channel else "multi-channel-pricing"),
            event_name=event_name,
            message=message,
            severity="error" if result == "failed" else "info",
            metadata=metadata,
            commit=commit,
        )

    def _safe_error(self, exc: Exception) -> str:
        if isinstance(exc, HTTPException):
            return str(exc.detail)
        if isinstance(exc, (SnappShopConnectorError, TapsiShopConnectorError)):
            return exc.error.message
        return str(normalize_upstream_error(exc, source="channel")["message"])

    def _version(self, channels: list[dict]) -> str:
        parts = [
            f"{item['channelId']}:{item['staleToken']}:{item['currentValue']}" for item in channels
        ]
        return sha256("|".join(parts).encode("utf-8")).hexdigest()


class _TransientWriteItem:
    def __init__(self, item: ProductPriceOperationItem) -> None:
        self.channel_product_id = item.channel_product_id
        self.proposed_price = item.proposed_value
        self.pre_write_snapshot_json = {}


def _price(row: DlProductCache | None) -> float | None:
    if row is None:
        return None
    for raw in (row.regular_price, row.price, row.last_price):
        try:
            return float(str(raw).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    return None


def _image_url(row: DlProductCache) -> str | None:
    images = row.images if isinstance(row.images, list) else []
    first = images[0] if images else None
    return first.get("src") if isinstance(first, dict) else None


def _stale_token(row: DlProductCache | None) -> str:
    if row is None:
        return "missing"
    return sha256(
        "|".join(
            str(value or "")
            for value in (
                row.connector_id,
                row.product_id,
                row.sku,
                row.regular_price,
                row.price,
                row.sale_price,
                row.freshness,
                row.last_successful_read,
                row.record_hash,
            )
        ).encode("utf-8")
    ).hexdigest()


def _row_hash(row: DlProductCache) -> str:
    return sha256(
        "|".join(
            str(value or "") for value in (row.product_id, row.sku, row.regular_price, row.price)
        ).encode("utf-8")
    ).hexdigest()


def _currency_for_channel(channel_id: str, default: str) -> str:
    return "IRR" if channel_id in {"snappshop:main", "tapsishop:main"} else default


def _unit_for_channel(channel_id: str, default_currency: str) -> str:
    if channel_id == "snappshop:main":
        return "toman"
    if channel_id == "tapsishop:main":
        return "rial"
    return default_currency


def _outbound_unit(channel_id: str) -> str:
    if channel_id == "snappshop:main":
        return "toman"
    if channel_id == "tapsishop:main":
        return "rial"
    return "store currency"


def _normalized_value(channel_id: str, value: float | None) -> float | None:
    if value is None:
        return None
    if channel_id == "snappshop:main":
        return value * 10
    return value


def _reference(result: dict) -> str | None:
    for key in ("referenceCode", "reference", "id", "request_id"):
        value = result.get(key)
        if value:
            return str(value)
    return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None
