"""Protected multi-channel product Price/Stock QTY/Stock Status workflow.

This is the backend for the Manual Channel Editor (/products): the Owner
directly edits a supported Channel field with no Source comparison,
auto-selection, warnings/blockers, or Apply Manifest business rules (that
automation lives in the Workspace engine, app/flowhub/unified_workspace/).
Channels and their per-field write capability are read from the same
WorkspaceConnectorFactory/connector capabilities() the Workspace engine
uses -- shared infrastructure, not a duplicated registry -- so a field is
only ever offered here when a real connector actually supports writing it.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.channels.snappshop import SnappShopConnectorError
from app.flowhub.channels.tapsishop import TapsiShopConnectorError
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.product_media import primary_image_url
from app.flowhub.product_pricing.models import ProductPriceOperation, ProductPriceOperationItem
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.security.upstream_errors import normalize_upstream_error
from app.flowhub.setup.service import AppConfigService
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: F401
from app.flowhub.write_pipeline.service import WritePipelineService
from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

FIELDS = ("price", "stock", "status")
STATUS_VALUES = ("instock", "outofstock")


@dataclass(frozen=True)
class _ChannelWriteCapability:
    write_price: bool
    write_stock: bool
    write_status: bool
    currency: str
    unit: str


@dataclass(frozen=True)
class FieldProposal:
    channel_id: str
    field: str
    proposed_value: float | str
    stale_token: str
    unit: str | None = None
    special_price: float | None = None


class ProductPricingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)
        self.integration = IntegrationPlatformService(db)

    # -- Channel discovery -----------------------------------------------
    # Real, connector-declared channels only. No hardcoded channel list:
    # this reuses the exact same connector factory and per-field
    # capabilities() the Workspace automation engine calls, so a channel
    # only appears here when its connector genuinely exists and declares
    # read support, and a field is only offered for edit when that same
    # connector genuinely declares write support for it.

    def _channel_directory(self) -> list[tuple[str, str, str, "_ChannelWriteCapability"]]:
        # Uses the static marketplace capability registry (safe: pure data,
        # no live connector construction) rather than the Workspace engine's
        # richer unified_workspace.connectors.*.capabilities(), which
        # constructs/health-checks a real provider connector as a side
        # effect and is therefore unsafe to call on every read of this
        # editor. The registry's write_price/write_stock/write_status
        # booleans are kept aligned with the Workspace connectors' verified,
        # real write support (see channels/registry.py's WooCommerce entry).
        from app.flowhub.channels.contracts import ChannelCapability
        from app.flowhub.channels.registry import default_marketplace_registry

        registry = default_marketplace_registry()
        directory: list[tuple[str, str, str, _ChannelWriteCapability]] = []
        for definition in registry.list_definitions():
            if not definition.implemented or ChannelCapability.PRODUCTS_READ not in definition.capabilities:
                continue
            currency, unit = _currency_unit_for(definition.connector_type, self.config)
            capability = _ChannelWriteCapability(
                write_price=ChannelCapability.PRODUCTS_WRITE_PRICE in definition.capabilities,
                write_stock=ChannelCapability.PRODUCTS_WRITE_STOCK in definition.capabilities,
                write_status=ChannelCapability.PRODUCTS_WRITE_STATUS in definition.capabilities,
                currency=currency,
                unit=unit,
            )
            directory.append((definition.channel_id, definition.name, definition.connector_type, capability))
        return directory

    def load(self, product_id: str) -> dict:
        canonical = self._canonical_row(product_id)
        if canonical is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
        channel_rows = self._channel_rows(canonical)
        channels = [
            self._channel_state(channel_id, name, connector_type, capabilities, channel_rows.get(channel_id))
            for channel_id, name, connector_type, capabilities in self._channel_directory()
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
        validated = self._validate_proposals(states, proposals)
        return {**states, "channels": validated, "status": "validated"}

    def dry_run(self, product_id: str, body: dict, user: FlowHubUser) -> dict:
        states = self.load(product_id)
        proposals = self._proposals(body)
        if str(body.get("version") or "") != states["version"]:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "STALE_PRODUCT_PRICE_STATE",
                    "message": "Product Channel fields changed after the editor was opened.",
                },
            )
        validated = self._validate_proposals(states, proposals)
        changed = _flatten_changed_fields(validated)
        if not changed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "No valid Channel field changes were submitted.",
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
            is_status = item["field"] == "status"
            self.db.add(
                ProductPriceOperationItem(
                    operation_id=operation_id,
                    channel_id=item["channelId"],
                    connector_type=item["connectorType"],
                    channel_product_id=item["channelProductId"],
                    sku=item["sku"] or "",
                    field=item["field"],
                    current_value=None if is_status else _as_float(item["currentValue"]),
                    proposed_value=None if is_status else _as_float(item["proposedValue"]),
                    current_status_value=item["currentValue"] if is_status else None,
                    proposed_status_value=item["proposedValue"] if is_status else None,
                    currency=item["currency"],
                    unit=item["unit"],
                    outbound_value=None if is_status else _as_float(item["outboundValue"]),
                    outbound_unit=item["outboundUnit"],
                    stale_token=item["staleToken"],
                    status="pending",
                    validation_state=item["validationState"],
                    result_json={"dry_run": True, "external_write": False},
                )
            )
            self._audit(
                "multi_channel_field_dry_run_item",
                "Multi-channel Channel field Dry Run item recorded. No external write was executed.",
                user=user,
                product=states["product"],
                channel=item,
                result="pending",
                upstream_reference=None,
                commit=False,
            )
        self._audit(
            "multi_channel_field_dry_run_created",
            "Multi-channel Channel field Dry Run created. No external write was executed.",
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
        op.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        op.approval_reason = str(body.get("reason") or "").strip() or None
        self._audit(
            "multi_channel_field_approved",
            "Multi-channel Channel field operation approved. Apply was not started.",
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
        if op.status not in {"approved", "reconciliation_required"}:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Apply requires a separate approved Dry Run."
            )
        self._assert_still_current(op)
        product = self._operation_product(op)
        success = 0
        failure = 0
        reconciliation = 0
        eligible_items = (
            op.items
            if op.status == "approved"
            else [item for item in op.items if item.status == "reconciliation_required"]
        )
        for item in eligible_items:
            try:
                result = await WritePipelineService(self.db).execute_product_pricing_item(
                    item, user
                )
            except Exception as exc:
                failure += 1
                item.status = "failed"
                item.error_message = self._safe_error(exc)
                item.result_json = {"success": False, "message": item.error_message}
                self._audit(
                    "multi_channel_field_item_failed",
                    item.error_message,
                    user=user,
                    product=product,
                    channel=self._item_channel_shape(item),
                    result="failed",
                    upstream_reference=None,
                    commit=False,
                )
            else:
                if result.outcome is not WriteOutcome.VERIFIED_APPLIED:
                    if result.outcome is WriteOutcome.RECONCILIATION_REQUIRED:
                        reconciliation += 1
                    else:
                        failure += 1
                    item.status = result.outcome.value
                    item.error_message = result.error_message
                    dispatch_intent = dict(item.result_json).get("dispatch_intent")
                    item.result_json = redact_sensitive(
                        {
                            "dispatch_intent": dispatch_intent,
                            "outcome": result.outcome,
                            "providerAccepted": result.provider_accepted,
                            "response": result.response,
                            "errorCategory": result.error_category,
                            "errorMessage": result.error_message,
                        }
                    )
                    self._audit(
                        "multi_channel_field_item_reconciliation_required"
                        if result.outcome is WriteOutcome.RECONCILIATION_REQUIRED
                        else "multi_channel_field_item_failed",
                        result.error_message or "Provider state was not exactly verified.",
                        user=user,
                        product=product,
                        channel=self._item_channel_shape(item),
                        result=result.outcome.value,
                        upstream_reference=result.external_response_id,
                        commit=False,
                    )
                    continue
                success += 1
                item.status = "applied"
                item.result_json = redact_sensitive(
                    {
                        "dispatch_intent": dict(item.result_json).get("dispatch_intent"),
                        "outcome": result.outcome,
                        "response": result.response,
                    }
                )
                self._audit(
                    "multi_channel_field_item_applied",
                    "Channel field update applied.",
                    user=user,
                    product=product,
                    channel=self._item_channel_shape(item),
                    result="applied",
                    upstream_reference=result.external_response_id,
                    commit=False,
                )
        op.applied_at = datetime.now(timezone.utc).replace(tzinfo=None)
        op.status = (
            "reconciliation_required"
            if reconciliation
            else "applied"
            if failure == 0
            else "partially_failed"
            if success
            else "failed"
        )
        op.summary_json = self._operation_summary(op)
        self._audit(
            "multi_channel_field_apply_finished",
            "Multi-channel Channel field Apply finished.",
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
        channel_ids = [channel_id for channel_id, *_ in self._channel_directory()]
        rows = (
            self.db.query(DlProductCache)
            .filter(DlProductCache.connector_id.in_(channel_ids))
            .all()
        )
        by_channel: dict[str, DlProductCache] = {}
        for channel_id in channel_ids:
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
        capabilities: _ChannelWriteCapability,
        row: DlProductCache | None,
    ) -> dict:
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        health = (
            self.db.query(DlConnectorHealth)
            .filter(DlConnectorHealth.connector_id == channel_id)
            .first()
        )
        enabled = bool(instance and instance.enabled)
        read_only = bool(instance.read_only) if instance else True
        connection_state = "disabled" if not enabled else "connected" if row else "disconnected"
        stale_token = _stale_token(row)
        fields = {
            "price": self._price_field_state(row, capabilities, enabled, read_only),
            "stock": self._stock_field_state(row, capabilities, enabled, read_only),
            "status": self._status_field_state(row, capabilities, enabled, read_only),
        }
        return {
            "channelId": channel_id,
            "channelName": name,
            "connectorType": connector_type,
            "channelProductId": row.product_id if row else "",
            "sku": row.sku if row else "",
            "connectionState": connection_state,
            "healthStatus": health.status if health else "unknown",
            "freshness": row.freshness if row else "missing",
            "lastSyncedAt": _iso(row.last_successful_read or row.last_fetched_at) if row else None,
            "staleToken": stale_token,
            "fields": fields,
        }

    def _field_base(
        self, *, can_write: bool, row_present: bool, capability_supported: bool
    ) -> dict:
        if not capability_supported:
            return {"canWrite": False, "validationState": "read_only", "validationMessage": "Channel does not support writing this field."}
        if not can_write:
            return {
                "canWrite": False,
                "validationState": "read_only" if row_present else "disconnected",
                "validationMessage": "Channel is disabled, disconnected, or read-only." if row_present else "Channel has no synchronized product row.",
            }
        return {"canWrite": True, "validationState": "valid", "validationMessage": None}

    def _price_field_state(self, row, capabilities: _ChannelWriteCapability, enabled, read_only) -> dict:
        supported = capabilities.write_price
        can_write = bool(row and enabled and not read_only and supported)
        base = self._field_base(can_write=can_write, row_present=bool(row), capability_supported=supported)
        current = _price(row)
        return {
            **base,
            "currentValue": current,
            "proposedValue": current,
            "currency": capabilities.currency,
            "unit": capabilities.unit,
            "outboundValue": current,
            "outboundUnit": capabilities.unit,
            "pendingChange": False,
            # Cross-currency comparison aid only (e.g. SnappShop TOMAN -> RIAL);
            # never authoritative for comparison, checksum, or write.
            "normalizedValue": _normalized_price(capabilities.unit, current),
            "normalizedCurrency": "IRR" if capabilities.currency == "IRR" else capabilities.currency,
            "normalizedUnit": "RIAL" if capabilities.currency == "IRR" else capabilities.unit,
        }

    def _stock_field_state(self, row, capabilities: _ChannelWriteCapability, enabled, read_only) -> dict:
        supported = capabilities.write_stock
        can_write = bool(row and enabled and not read_only and supported)
        base = self._field_base(can_write=can_write, row_present=bool(row), capability_supported=supported)
        current = float(row.stock_qty) if row and row.stock_qty is not None else None
        return {
            **base,
            "currentValue": current,
            "proposedValue": current,
            "currency": "",
            "unit": "units",
            "outboundValue": current,
            "outboundUnit": "units",
            "pendingChange": False,
        }

    def _status_field_state(self, row, capabilities: _ChannelWriteCapability, enabled, read_only) -> dict:
        supported = capabilities.write_status
        can_write = bool(row and enabled and not read_only and supported)
        base = self._field_base(can_write=can_write, row_present=bool(row), capability_supported=supported)
        current = row.stock_status if row and row.stock_status in STATUS_VALUES else None
        return {
            **base,
            "currentValue": current,
            "proposedValue": current,
            "currency": "",
            "unit": "",
            "outboundValue": current,
            "outboundUnit": "",
            "pendingChange": False,
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

    def _proposals(self, body: dict) -> list[FieldProposal]:
        proposals = []
        for raw in body.get("changes") or []:
            field = str(raw.get("field") or "price").strip()
            if field not in FIELDS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported field: {field}")
            if field == "status":
                value = str(raw.get("proposedValue") or "").strip()
            else:
                try:
                    value = float(raw.get("proposedValue"))
                except (TypeError, ValueError):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} must be numeric."
                    ) from None
            special = raw.get("specialPrice")
            try:
                special_value = None if special in (None, "") else float(special)
            except (TypeError, ValueError):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, "Special price must be numeric."
                ) from None
            proposals.append(
                FieldProposal(
                    channel_id=str(raw.get("channelId") or ""),
                    field=field,
                    proposed_value=value,
                    stale_token=str(raw.get("staleToken") or ""),
                    unit=str(raw.get("unit") or "").strip() or None,
                    special_price=special_value,
                )
            )
        return proposals

    def _validate_proposals(self, states: dict, proposals: list[FieldProposal]) -> list[dict]:
        by_channel = {item["channelId"]: dict(item) for item in states["channels"]}
        for proposal in proposals:
            channel = by_channel.get(proposal.channel_id)
            if channel is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown channel: {proposal.channel_id}"
                )
            if proposal.stale_token != channel["staleToken"]:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "STALE_CHANNEL_PRICE_STATE",
                        "message": f"{proposal.channel_id} changed after the editor was opened.",
                    },
                )
            channel["fields"] = dict(channel["fields"])
            field_state = dict(channel["fields"][proposal.field])
            self._apply_field_proposal(proposal, field_state, channel_id=proposal.channel_id)
            channel["fields"][proposal.field] = field_state
        return list(by_channel.values())

    def _apply_field_proposal(self, proposal: FieldProposal, field_state: dict, *, channel_id: str) -> None:
        errors: list[str] = []
        if not field_state["canWrite"]:
            errors.append("Channel does not support writing this field, or is disabled/disconnected/read-only.")
        if proposal.field == "price":
            self._validate_price_proposal(proposal, field_state, errors)
        elif proposal.field == "stock":
            self._validate_stock_proposal(proposal, field_state, errors)
        else:
            self._validate_status_proposal(proposal, field_state, errors)
        field_state["validationState"] = "error" if errors else "valid"
        field_state["validationMessage"] = "; ".join(errors) if errors else None

    def _validate_price_proposal(self, proposal: FieldProposal, field_state: dict, errors: list[str]) -> None:
        value = proposal.proposed_value
        assert isinstance(value, float)
        proposed_is_finite = math.isfinite(value)
        if not proposed_is_finite or value < 0:
            errors.append("Price must be numeric and non-negative.")
        elif not value.is_integer():
            errors.append("Price must be a whole number.")
        if proposal.special_price is not None and proposal.special_price > value:
            errors.append("Special price must not exceed regular price.")
        expected_unit = str(field_state["unit"] or "")
        if proposal.unit and proposal.unit.upper() != expected_unit.upper():
            errors.append(f"Expected {expected_unit} for {proposal.channel_id}.")
        if proposed_is_finite and proposal.channel_id == "snappshop:main" and int(value) != value:
            errors.append("SnappShop toman values must be whole numbers.")
        if proposed_is_finite and proposal.channel_id == "tapsishop:main":
            if int(value) != value:
                errors.append("TapsiShop rial values must be whole numbers.")
            elif int(value) % 10 != 0:
                errors.append("TapsiShop rial values must preserve toman/rial precision and be divisible by 10.")
        field_state["proposedValue"] = value
        field_state["outboundValue"] = value if errors else self._outbound_price(proposal.channel_id, value)
        field_state["pendingChange"] = (
            field_state["currentValue"] is None
            or abs(float(field_state["currentValue"]) - value) > 0.0001
        )

    def _validate_stock_proposal(self, proposal: FieldProposal, field_state: dict, errors: list[str]) -> None:
        value = proposal.proposed_value
        assert isinstance(value, float)
        if not math.isfinite(value) or value < 0 or not value.is_integer():
            errors.append("Stock quantity must be a non-negative whole number.")
        field_state["proposedValue"] = value
        field_state["outboundValue"] = value
        field_state["pendingChange"] = (
            field_state["currentValue"] is None
            or abs(float(field_state["currentValue"]) - value) > 0.0001
        )

    def _validate_status_proposal(self, proposal: FieldProposal, field_state: dict, errors: list[str]) -> None:
        value = proposal.proposed_value
        assert isinstance(value, str)
        if value not in STATUS_VALUES:
            errors.append("Stock status must be exactly 'instock' or 'outofstock'.")
        field_state["proposedValue"] = value
        field_state["outboundValue"] = value
        field_state["pendingChange"] = field_state["currentValue"] != value

    def _outbound_price(self, channel_id: str, value: float) -> float:
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
            "reconciliationRequired": sum(
                1 for item in op.items if item.status == "reconciliation_required"
            ),
            "external_write_performed": op.applied_at is not None,
        }

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
        is_status = item.field == "status"
        return {
            "id": item.id,
            "channelId": item.channel_id,
            "connectorType": item.connector_type,
            "channelProductId": item.channel_product_id,
            "sku": item.sku,
            "field": item.field,
            "currentValue": item.current_status_value if is_status else item.current_value,
            "proposedValue": item.proposed_status_value if is_status else item.proposed_value,
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
        is_status = item.field == "status"
        return {
            "channelId": item.channel_id,
            "connectorType": item.connector_type,
            "channelProductId": item.channel_product_id,
            "field": item.field,
            "currentValue": item.current_status_value if is_status else item.current_value,
            "proposedValue": item.proposed_status_value if is_status else item.proposed_value,
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
            "field": channel.get("field") if channel else None,
            "previous_value": channel.get("currentValue") if channel else None,
            "proposed_value": channel.get("proposedValue") if channel else None,
            "converted_outbound_value": channel.get("outboundValue") if channel else None,
            "unit": channel.get("unit") if channel else None,
            "result": result,
            "upstream_reference": upstream_reference,
            "timestamp": _iso(datetime.now(timezone.utc).replace(tzinfo=None)),
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
        parts = [f"{item['channelId']}:{item['staleToken']}" for item in channels]
        return sha256("|".join(parts).encode("utf-8")).hexdigest()


_IRR_UNIT_BY_CONNECTOR_TYPE = {"snappshop": "TOMAN", "tapsishop": "RIAL", "technolife": "RIAL"}


def _currency_unit_for(connector_type: str, config: AppConfigService) -> tuple[str, str]:
    unit = _IRR_UNIT_BY_CONNECTOR_TYPE.get(connector_type)
    if unit is not None:
        return "IRR", unit
    currency = config.get("server.currency") or "EUR"
    return currency, currency


def _normalized_price(unit: str, value: float | None) -> float | None:
    if value is None:
        return None
    return value * 10 if unit == "TOMAN" else value


def _flatten_changed_fields(channels: list[dict]) -> list[dict]:
    """Flatten validated channel/fields rows to one entry per pending,
    valid field change -- a single Owner submission may edit more than one
    field (e.g. price and stock) on the same channel in one Dry Run."""

    flattened: list[dict] = []
    for channel in channels:
        for field_name, field_state in channel["fields"].items():
            if field_state["pendingChange"] and field_state["validationState"] == "valid":
                flattened.append(
                    {
                        "channelId": channel["channelId"],
                        "connectorType": channel["connectorType"],
                        "channelProductId": channel["channelProductId"],
                        "sku": channel["sku"],
                        "field": field_name,
                        "currentValue": field_state["currentValue"],
                        "proposedValue": field_state["proposedValue"],
                        "currency": field_state["currency"],
                        "unit": field_state["unit"],
                        "outboundValue": field_state["outboundValue"],
                        "outboundUnit": field_state["outboundUnit"],
                        "staleToken": channel["staleToken"],
                        "validationState": field_state["validationState"],
                    }
                )
    return flattened


def _as_float(value: object) -> float | None:
    return None if value is None else float(value)


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
    return primary_image_url(row.images)


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
                row.stock_qty,
                row.stock_status,
                row.freshness,
                row.last_successful_read,
                row.record_hash,
            )
        ).encode("utf-8")
    ).hexdigest()


def _reference(result: dict) -> str | None:
    for key in ("referenceCode", "reference", "id", "request_id"):
        value = result.get(key)
        if value:
            return str(value)
    return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None
