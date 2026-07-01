"""Integration Platform service facade.

All active Beta v2 routes use this service for connector metadata and read
models. It never calls WooCommerce, Nextcloud, httpx, Apply, Scheduler, or
pricing automation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.beta.data_layer.models import (
    DlConnectorHealth,
    DlConnectorTelemetry,
    DlDestinationSnapshot,
    DlProductCache,
    DlSourceSnapshot,
)
from app.beta.integration_platform.contracts import (
    ConnectorCategoryListResponse,
    ConnectorCategoryShape,
    ConnectorCreateRequest,
    ConnectorDefinition,
    ConnectorDescriptor,
    ConnectorHealthStatus,
    ConnectorIdentity,
    ConnectorInstanceShape,
    ConnectorListResponse,
    ConnectorProductListResponse,
    ConnectorProductShape,
    ConnectorRegistryResponse,
    ConnectorSettingValue,
    ConnectorSourceListResponse,
    ConnectorSourceShape,
    ConnectorTelemetryResponse,
    ConnectorTelemetryShape,
    IntegrationSettingsSummary,
    WorkspaceIntegrationSummary,
    WorkspacePreviewResponse,
)
from app.beta.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorHealthSnapshot,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.beta.integration_platform.registry import registry
from app.beta.setup.service import AppConfigService


_SECRET_KEYS = {"key", "secret", "password", "token", "consumer_key", "consumer_secret"}


class IntegrationPlatformService:
    def __init__(self, db: Session):
        self.db = db
        self.config = AppConfigService(db)

    # Registry and instances
    def list_registry(self) -> ConnectorRegistryResponse:
        return ConnectorRegistryResponse(items=registry.list_definitions())

    def get_registry_definition(self, connector_type: str) -> ConnectorDefinition:
        definition = registry.get_definition(connector_type)
        if definition is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector definition not found.")
        return definition

    def list_instances(self) -> ConnectorListResponse:
        self.bootstrap_from_app_config()
        rows = (
            self.db.query(IntegrationConnectorInstance)
            .order_by(IntegrationConnectorInstance.connector_type.asc(), IntegrationConnectorInstance.name.asc())
            .all()
        )
        return ConnectorListResponse(items=[self._instance_to_shape(row) for row in rows])

    def create_instance(self, body: ConnectorCreateRequest) -> ConnectorInstanceShape:
        definition = self.get_registry_definition(body.connector_type)
        existing = self.db.get(IntegrationConnectorInstance, body.id)
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Connector instance already exists.")
        row = IntegrationConnectorInstance(
            id=body.id,
            connector_type=body.connector_type,
            name=body.name,
            version=definition.connector.identity.version,
            enabled=body.enabled,
            read_only=True,
            status=ConnectorHealthStatus.DISABLED.value,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        self.record_event(
            connector_id=row.id,
            event_name="connector_created",
            message=f"Connector '{row.name}' was created in read-only mode.",
            metadata={"connector_type": row.connector_type},
        )
        return self._instance_to_shape(row)

    def get_instance(self, connector_id: str) -> ConnectorInstanceShape:
        self.bootstrap_from_app_config()
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        return self._instance_to_shape(row)

    def get_settings(self, connector_id: str) -> list[ConnectorSettingValue]:
        return self.get_instance(connector_id).settings

    def update_settings(self, connector_id: str, settings: list[ConnectorSettingValue]) -> ConnectorInstanceShape:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        self._upsert_settings(row, settings)
        self.record_event(
            connector_id=connector_id,
            event_name="connector_settings_updated",
            message="Connector settings were updated; secret values remain masked.",
            metadata={"updated_keys": [item.key for item in settings]},
        )
        self.db.refresh(row)
        return self._instance_to_shape(row)

    # Legacy config bootstrap. This is local DB metadata only, no external calls.
    def bootstrap_from_app_config(self) -> None:
        wc_values = {
            "url": self.config.get("woocommerce.url"),
            "key": self.config.get("woocommerce.key"),
            "secret": self.config.get("woocommerce.secret"),
        }
        if any(wc_values.values()):
            self.ensure_connector_from_settings(
                connector_type="woocommerce",
                connector_id="woocommerce:primary",
                name="WooCommerce",
                values=wc_values,
            )
        nc_values = {
            "url": self.config.get("nextcloud.url"),
            "username": self.config.get("nextcloud.username"),
            "password": self.config.get("nextcloud.password"),
            "spreadsheet_path": self.config.get("nextcloud.spreadsheet_path"),
        }
        if any(nc_values.values()):
            self.ensure_connector_from_settings(
                connector_type="nextcloud",
                connector_id="nextcloud:primary",
                name="Nextcloud Spreadsheet",
                values=nc_values,
            )

    def ensure_connector_from_settings(
        self,
        *,
        connector_type: str,
        connector_id: str,
        name: str,
        values: dict[str, object | None],
    ) -> IntegrationConnectorInstance:
        definition = self.get_registry_definition(connector_type)
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        now = datetime.utcnow()
        if row is None:
            row = IntegrationConnectorInstance(
                id=connector_id,
                connector_type=connector_type,
                name=name,
                version=definition.connector.identity.version,
                enabled=self._required_settings_configured(definition, values),
                read_only=True,
                status=ConnectorHealthStatus.DISABLED.value,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
            self.db.flush()
            self.record_event(
                connector_id=connector_id,
                event_name="connector_registered",
                message="Connector settings were registered from local configuration.",
                metadata={"connector_type": connector_type},
                commit=False,
            )
        else:
            row.enabled = self._required_settings_configured(definition, values)
            row.read_only = True
            row.updated_at = now
        self._upsert_settings(
            row,
            [
                ConnectorSettingValue(
                    key=key,
                    value=value,
                    secret=key in _SECRET_KEYS,
                    configured=value not in (None, ""),
                )
                for key, value in values.items()
            ],
            commit=False,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    # Data Layer read surfaces
    def list_products(
        self,
        search: str = "",
        page: int = 1,
        page_size: int = 50,
        category_id: int | None = None,
        product_type: str | None = None,
    ) -> ConnectorProductListResponse:
        self.bootstrap_from_app_config()
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        q = self.db.query(DlProductCache)
        if search:
            pattern = f"%{search}%"
            q = q.filter(
                or_(
                    DlProductCache.name.ilike(pattern),
                    DlProductCache.sku.ilike(pattern),
                    DlProductCache.product_id.ilike(pattern),
                )
            )
        if product_type in {"simple", "variable", "variation"}:
            q = q.filter(DlProductCache.product_type == product_type)
        if category_id is not None:
            filtered_rows = [
                row
                for row in q.order_by(DlProductCache.name.asc(), DlProductCache.id.asc()).all()
                if _product_has_category(row, category_id)
            ]
            total = len(filtered_rows)
            rows = filtered_rows[(page - 1) * page_size : page * page_size]
        else:
            total = q.count()
            rows = (
                q.order_by(DlProductCache.name.asc(), DlProductCache.id.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        currency = self.config.get("server.currency") or "EUR"
        return ConnectorProductListResponse(
            items=[self._product_to_shape(row, currency) for row in rows],
            total=total,
            page=page,
            pageSize=page_size,
            page_size=page_size,
            configured=self._is_connector_configured("woocommerce:primary"),
        )

    def list_categories(self) -> ConnectorCategoryListResponse:
        rows = self.db.query(DlProductCache.categories).all()
        counts: dict[int, ConnectorCategoryShape] = {}
        fallback_id = 1_000_000
        for (categories,) in rows:
            for category in categories or []:
                if isinstance(category, dict):
                    name = str(category.get("name") or "").strip()
                    if not name:
                        continue
                    cid = int(category.get("id") or fallback_id)
                    parent = int(category.get("parent") or 0)
                else:
                    name = str(category).strip()
                    if not name:
                        continue
                    cid = fallback_id
                    parent = 0
                fallback_id += 1
                if cid not in counts:
                    counts[cid] = ConnectorCategoryShape(id=cid, name=name, parent=parent, count=0)
                counts[cid].count += 1
        items = sorted(counts.values(), key=lambda item: item.name.lower())
        return ConnectorCategoryListResponse(items=items, total=len(items))

    def list_sources(self) -> ConnectorSourceListResponse:
        self.bootstrap_from_app_config()
        instances = (
            self.db.query(IntegrationConnectorInstance)
            .order_by(IntegrationConnectorInstance.connector_type.asc())
            .all()
        )
        source_rows = self.db.query(DlSourceSnapshot).all()
        source_by_connector = {row.connector_id: row for row in source_rows}
        product_counts = self._product_counts_by_connector()
        items: list[ConnectorSourceShape] = []
        for instance in instances:
            if instance.connector_type not in {"nextcloud", "woocommerce"}:
                continue
            snapshot = source_by_connector.get(instance.id)
            display = self._display_url(instance)
            status_value = self._source_status(instance, snapshot)
            items.append(
                ConnectorSourceShape(
                    id=instance.id,
                    connector_id=instance.id,
                    name=instance.name,
                    type="nextcloud_excel" if instance.connector_type == "nextcloud" else "woocommerce",
                    displayUrl=display,
                    status=status_value,
                    lastSynced=_iso(snapshot.snapshotted_at) if snapshot else None,
                    productCount=product_counts.get(instance.id, 0),
                )
            )
        return ConnectorSourceListResponse(items=items)

    def workspace_summary(self) -> WorkspaceIntegrationSummary:
        self.bootstrap_from_app_config()
        return WorkspaceIntegrationSummary(
            source_count=len(self.list_sources().items),
            product_count=self.db.query(DlProductCache).count(),
            connector_count=self.db.query(IntegrationConnectorInstance).count(),
        )

    def workspace_preview(self) -> WorkspacePreviewResponse:
        self.bootstrap_from_app_config()
        now = datetime.utcnow()
        self.record_event(
            connector_id="integration-platform",
            event_name="workspace_preview_read",
            message="Workspace preview read Data Layer records only.",
            metadata={"external_call_performed": False},
        )
        return WorkspacePreviewResponse(
            id=str(uuid.uuid4()),
            sourceId="data-layer",
            sourceName="FlowHub Data Layer",
            state="preview_ready",
            totalChanges=0,
            changes=[],
            startedAt=_iso(now) or now.isoformat(),
        )

    def settings_summary(self) -> list[IntegrationSettingsSummary]:
        return [
            IntegrationSettingsSummary(
                connector_id=instance.connector.identity.id,
                connector_type=instance.connector.identity.type,
                name=instance.connector.identity.name,
                settings=instance.settings,
            )
            for instance in self.list_instances().items
        ]

    def telemetry(self, connector_id: str | None = None, limit: int = 100) -> ConnectorTelemetryResponse:
        q = self.db.query(IntegrationConnectorEvent)
        if connector_id:
            q = q.filter(IntegrationConnectorEvent.connector_id == connector_id)
        total = q.count()
        events = (
            q.order_by(IntegrationConnectorEvent.created_at.desc(), IntegrationConnectorEvent.id.desc())
            .limit(min(max(limit, 1), 500))
            .all()
        )
        aggregate = self._telemetry_aggregate(connector_id)
        return ConnectorTelemetryResponse(
            items=[self._event_to_shape(event) for event in events],
            total=total,
            aggregate=aggregate,
        )

    def diagnostics_run(self, target: str = "all") -> dict:
        self.bootstrap_from_app_config()
        started = datetime.utcnow()
        definitions = registry.list_definitions()
        if target != "all":
            definitions = [d for d in definitions if d.connector.identity.type == target]
            if not definitions:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Diagnostic target not found.")
        instances = {
            row.connector_type: row
            for row in self.db.query(IntegrationConnectorInstance).all()
        }
        checks: list[dict] = []
        for definition in definitions:
            instance = instances.get(definition.connector.identity.type)
            health = self._latest_health(instance.id) if instance else None
            for check in definition.diagnostics_contract.checks:
                check_status, message, skipped = self._diagnostic_check_result(check.name, instance, health)
                checks.append(
                    {
                        "check_name": check.name,
                        "category": check.category,
                        "target": definition.connector.identity.type,
                        "status": check_status,
                        "failure_class": "none" if check_status != "fail" else "integration_platform",
                        "severity": "info" if check_status != "fail" else "warning",
                        "message": message,
                        "repair_hint": "Configure connector settings or refresh Data Layer records." if skipped else "",
                        "duration_ms": 0.0,
                        "checked_at": _iso(started),
                        "details": {"external_call_performed": False},
                        "skipped_because": skipped,
                    }
                )
        completed = datetime.utcnow()
        overall = "ok" if checks and all(c["status"] == "pass" for c in checks) else "skip"
        return {
            "target": target,
            "started_at": _iso(started),
            "completed_at": _iso(completed),
            "duration_ms": (completed - started).total_seconds() * 1000,
            "overall_status": overall,
            "overall_failure_class": "none",
            "overall_severity": "info",
            "summary": "Integration diagnostics completed from Integration Platform and Data Layer records only.",
            "checks": checks,
            "repair_steps": [],
        }

    def record_event(
        self,
        *,
        connector_id: str,
        event_name: str,
        message: str,
        severity: str = "info",
        metadata: dict | None = None,
        commit: bool = True,
    ) -> IntegrationConnectorEvent:
        event = IntegrationConnectorEvent(
            connector_id=connector_id,
            event_name=event_name,
            severity=severity,
            message=message,
            metadata_json=metadata or {},
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    # Internal mapping helpers
    def _instance_to_shape(self, row: IntegrationConnectorInstance) -> ConnectorInstanceShape:
        definition = self.get_registry_definition(row.connector_type)
        health_status = self._health_status_for(row)
        descriptor = ConnectorDescriptor(
            identity=ConnectorIdentity(
                id=row.id,
                name=row.name,
                type=row.connector_type,
                version=row.version,
                enabled=row.enabled,
                read_only=True,
            ),
            capabilities=definition.connector.capabilities,
            status=health_status,
        )
        return ConnectorInstanceShape(
            connector=descriptor,
            settings=[self._setting_to_shape(item) for item in row.settings],
            created_at=_iso(row.created_at),
            updated_at=_iso(row.updated_at),
        )

    def _upsert_settings(
        self,
        row: IntegrationConnectorInstance,
        settings: Iterable[ConnectorSettingValue],
        *,
        commit: bool = True,
    ) -> None:
        existing = {item.key: item for item in row.settings}
        now = datetime.utcnow()
        for item in settings:
            secret = item.secret or item.key in _SECRET_KEYS
            configured = item.configured or item.value not in (None, "")
            value = None if secret else item.value
            setting = existing.get(item.key)
            if setting is None:
                setting = IntegrationConnectorSetting(
                    connector_id=row.id,
                    key=item.key,
                    value_json=value,
                    secret=secret,
                    configured=configured,
                    updated_at=now,
                )
                self.db.add(setting)
            else:
                setting.value_json = value
                setting.secret = secret
                setting.configured = configured
                setting.updated_at = now
        row.updated_at = now
        if commit:
            self.db.commit()

    def _setting_to_shape(self, row: IntegrationConnectorSetting) -> ConnectorSettingValue:
        return ConnectorSettingValue(
            key=row.key,
            value=None if row.secret else row.value_json,
            secret=row.secret,
            configured=row.configured,
        )

    def _product_to_shape(self, row: DlProductCache, currency: str) -> ConnectorProductShape:
        categories = row.categories or []
        category_names = [
            str(item.get("name") if isinstance(item, dict) else item)
            for item in categories
            if item
        ]
        image_url = None
        if row.images and isinstance(row.images, list) and row.images:
            first = row.images[0]
            image_url = first.get("src") if isinstance(first, dict) else None
        return ConnectorProductShape(
            id=str(row.id),
            wcId=row.external_id,
            connectorId=row.connector_id,
            productId=row.product_id,
            name=row.name or "",
            sku=row.sku or "",
            currentPrice=_float_or_zero(row.price),
            sourcePrice=None,
            currency=currency,
            categoryNames=category_names,
            imageUrl=image_url,
            productType=row.product_type or "simple",
            status=row.status or row.freshness or "pending",
            lastSynced=_iso(row.last_fetched_at),
        )

    def _event_to_shape(self, event: IntegrationConnectorEvent) -> ConnectorTelemetryShape:
        return ConnectorTelemetryShape(
            id=event.id,
            connector_id=event.connector_id,
            event_name=event.event_name,
            severity=event.severity,
            message=event.message,
            created_at=_iso(event.created_at) or "",
            metadata=event.metadata_json or {},
        )

    def _telemetry_aggregate(self, connector_id: str | None) -> dict:
        q = self.db.query(DlConnectorTelemetry)
        if connector_id:
            q = q.filter(DlConnectorTelemetry.connector_id == connector_id)
        rows = q.all()
        return {
            "connectors_tracked": len(rows),
            "total_requests": sum((row.request_count or 0) for row in rows),
            "total_errors": sum((row.error_count or 0) for row in rows),
            "total_products_fetched": sum((row.products_fetched or 0) for row in rows),
            "total_rows_parsed": sum((row.rows_parsed or 0) for row in rows),
        }

    def _latest_health(self, connector_id: str) -> DlConnectorHealth | None:
        return (
            self.db.query(DlConnectorHealth)
            .filter(DlConnectorHealth.connector_id == connector_id)
            .order_by(DlConnectorHealth.checked_at.desc())
            .first()
        )

    def _health_status_for(self, row: IntegrationConnectorInstance) -> ConnectorHealthStatus:
        health = self._latest_health(row.id)
        if not row.enabled:
            return ConnectorHealthStatus.DISABLED
        if health is None:
            return ConnectorHealthStatus.DEGRADED
        if health.status == "healthy":
            return ConnectorHealthStatus.HEALTHY
        if health.status == "degraded":
            return ConnectorHealthStatus.DEGRADED
        if health.error_class == "authentication_failed":
            return ConnectorHealthStatus.AUTHENTICATION_FAILED
        if health.error_class == "rate_limited":
            return ConnectorHealthStatus.RATE_LIMITED
        if health.error_class == "timeout":
            return ConnectorHealthStatus.TIMEOUT
        return ConnectorHealthStatus.ERROR

    def _display_url(self, row: IntegrationConnectorInstance) -> str:
        settings = {setting.key: setting for setting in row.settings}
        url = settings.get("url")
        path = settings.get("spreadsheet_path")
        base = str(url.value_json or "") if url and not url.secret else ""
        suffix = str(path.value_json or "") if path and not path.secret else ""
        return f"{base}{suffix}" if base else row.id

    def _source_status(self, row: IntegrationConnectorInstance, snapshot: DlSourceSnapshot | None) -> str:
        if not row.enabled:
            return "unconfigured"
        health = self._health_status_for(row)
        if health in {ConnectorHealthStatus.ERROR, ConnectorHealthStatus.AUTHENTICATION_FAILED}:
            return "error"
        return "active" if snapshot or row.enabled else "pending"

    def _product_counts_by_connector(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for (connector_id,) in self.db.query(DlProductCache.connector_id).all():
            counts[connector_id] = counts.get(connector_id, 0) + 1
        return counts

    def _is_connector_configured(self, connector_id: str) -> bool:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        return bool(row and row.enabled)

    def _required_settings_configured(self, definition: ConnectorDefinition, values: dict[str, object | None]) -> bool:
        for item in definition.settings_schema:
            if item.required and values.get(item.key) in (None, ""):
                return False
        return True

    def _diagnostic_check_result(
        self,
        check_name: str,
        instance: IntegrationConnectorInstance | None,
        health: DlConnectorHealth | None,
    ) -> tuple[str, str, str | None]:
        if instance is None or not instance.enabled:
            return "skip", "Connector instance is not configured or enabled.", "connector_not_active"
        if check_name == "health_record" and health is None:
            return "skip", "No Data Layer health record is available yet.", "health_record_missing"
        if check_name == "source_snapshot":
            snapshot = (
                self.db.query(DlSourceSnapshot)
                .filter(DlSourceSnapshot.connector_id == instance.id)
                .first()
            )
            if snapshot is None:
                return "skip", "No source snapshot record is available yet.", "source_snapshot_missing"
        if check_name == "telemetry":
            telemetry = (
                self.db.query(DlConnectorTelemetry)
                .filter(DlConnectorTelemetry.connector_id == instance.id)
                .first()
            )
            if telemetry is None:
                return "skip", "No connector telemetry record is available yet.", "telemetry_missing"
        return "pass", "Check satisfied from Integration Platform/Data Layer records.", None


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _product_has_category(row: DlProductCache, category_id: int) -> bool:
    for category in row.categories or []:
        if isinstance(category, dict) and str(category.get("id")) == str(category_id):
            return True
    return False


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"
