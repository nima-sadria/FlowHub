"""Integration Platform service facade.

All active FLOWHUB v2 routes use this service for connector metadata and read
models. It never calls WooCommerce, Nextcloud, httpx, Apply, Scheduler, or
pricing automation.
"""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime
from hashlib import sha256
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import (
    DlConnectorHealth,
    DlConnectorTelemetry,
    DlDestinationSnapshot,
    DlProductCache,
    DlSourceSnapshot,
)
from app.flowhub.integration_platform.contracts import (
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
from app.flowhub.integration_platform.models import (
    IntegrationConnectorDiagnostic,
    IntegrationConnectorEvent,
    IntegrationConnectorHealthSnapshot,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
    IntegrationConnectorTelemetry,
    IntegrationPollingPolicy,
    IntegrationWebhookEvent,
)
from app.flowhub.integration_platform.registry import registry
from app.flowhub.setup.service import AppConfigService


_SECRET_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "consumer_key",
    "consumer_secret",
    "webhook_secret",
    "bearer",
    "authorization",
}


class IntegrationPlatformService:
    def __init__(self, db: Session):
        self.db = db
        self.config = AppConfigService(db)

    # Registry and instances
    def list_registry(self) -> ConnectorRegistryResponse:
        return ConnectorRegistryResponse(items=registry.list_definitions())

    def list_registry_contract(self) -> dict:
        return {
            "items": [self._definition_to_contract(item) for item in registry.list_definitions()],
            "total": len(registry.list_definitions()),
            "correlation_id": self._correlation_id(),
        }

    def get_registry_definition(self, connector_type: str) -> ConnectorDefinition:
        definition = registry.get_definition(connector_type)
        if definition is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector definition not found.")
        return definition

    def get_registry_contract(self, connector_type: str) -> dict:
        return self._definition_to_contract(self.get_registry_definition(connector_type), detail=True)

    def list_instances(self) -> ConnectorListResponse:
        self.bootstrap_from_app_config()
        rows = (
            self.db.query(IntegrationConnectorInstance)
            .order_by(IntegrationConnectorInstance.connector_type.asc(), IntegrationConnectorInstance.name.asc())
            .all()
        )
        return ConnectorListResponse(items=[self._instance_to_shape(row) for row in rows])

    def list_instances_contract(self, page: int = 1, page_size: int = 50) -> dict:
        self.bootstrap_from_app_config()
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        q = self.db.query(IntegrationConnectorInstance).order_by(
            IntegrationConnectorInstance.connector_type.asc(),
            IntegrationConnectorInstance.name.asc(),
        )
        total = q.count()
        rows = q.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [self._instance_to_contract(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "correlation_id": self._correlation_id(),
        }

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

    def create_instance_contract(self, body: dict) -> dict:
        connector_type = str(body.get("connector_type") or "").strip()
        if not connector_type:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "connector_type is required.")
        definition = self.get_registry_definition(connector_type)
        connector_id = str(body.get("id") or f"{connector_type}:{uuid.uuid4().hex[:12]}")
        existing = self.db.get(IntegrationConnectorInstance, connector_id)
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Connector instance already exists.")
        row = IntegrationConnectorInstance(
            id=connector_id,
            connector_type=connector_type,
            name=str(body.get("name") or definition.connector.identity.name),
            version=definition.connector.identity.version,
            enabled=bool(body.get("enabled", True)),
            read_only=True,
            status=ConnectorHealthStatus.DISABLED.value,
        )
        self.db.add(row)
        self.db.flush()
        settings = body.get("settings")
        if isinstance(settings, dict):
            secret_keys = self._definition_secret_keys(definition)
            self._upsert_settings(
                row,
                [
                    ConnectorSettingValue(
                        key=key,
                        value=value,
                        secret=_is_secret_key(key) or key in secret_keys,
                        configured=value not in (None, ""),
                    )
                    for key, value in settings.items()
                ],
                commit=False,
            )
        self.record_event(
            connector_id=row.id,
            event_name="connector_created",
            message="Connector instance was created in FlowHub local configuration only.",
            metadata={"external_write_performed": False},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._instance_to_contract(row)

    def update_instance_contract(self, connector_id: str, body: dict) -> dict:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        if "name" in body:
            row.name = str(body["name"])
        if "enabled" in body:
            row.enabled = bool(body["enabled"])
        row.read_only = True
        settings = body.get("settings")
        if isinstance(settings, dict):
            secret_keys = self._definition_secret_keys(self.get_registry_definition(row.connector_type))
            self._upsert_settings(
                row,
                [
                    ConnectorSettingValue(
                        key=key,
                        value=value,
                        secret=_is_secret_key(key) or key in secret_keys,
                        configured=value not in (None, ""),
                    )
                    for key, value in settings.items()
                ],
                commit=False,
            )
        row.updated_at = datetime.utcnow()
        self.record_event(
            connector_id=connector_id,
            event_name="connector_updated",
            message="Connector instance was updated locally.",
            metadata={"external_write_performed": False},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._instance_to_contract(row)

    def set_enabled_contract(self, connector_id: str, enabled: bool) -> dict:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        row.enabled = enabled
        row.read_only = True
        row.updated_at = datetime.utcnow()
        self.record_event(
            connector_id=connector_id,
            event_name="connector_enabled" if enabled else "connector_disabled",
            message="Connector enabled state changed locally. Scheduler execution was not started.",
            metadata={"scheduler_started": False, "external_write_performed": False},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(row)
        return self._instance_to_contract(row)

    def delete_instance_contract(self, connector_id: str) -> dict:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        self.db.delete(row)
        self.record_event(
            connector_id=connector_id,
            event_name="connector_deleted",
            message="Connector configuration was deleted from FlowHub only.",
            metadata={"external_platform_unchanged": True},
            commit=False,
        )
        self.db.commit()
        return {"deleted": True, "external_platform_unchanged": True, "correlation_id": self._correlation_id()}

    def get_instance(self, connector_id: str) -> ConnectorInstanceShape:
        self.bootstrap_from_app_config()
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        return self._instance_to_shape(row)

    def get_settings(self, connector_id: str) -> list[ConnectorSettingValue]:
        return self.get_instance(connector_id).settings

    def get_settings_contract(self, connector_id: str) -> dict:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        settings: dict[str, object] = {}
        secrets: dict[str, dict[str, str | None]] = {}
        for item in row.settings:
            if item.secret:
                secrets[item.key] = {
                    "status": "configured" if item.configured else "not_configured",
                    "replaced_at": _iso(item.updated_at),
                }
            else:
                settings[item.key] = item.value_json
        return {
            "connector_id": connector_id,
            "settings": settings,
            "secrets": secrets,
            "correlation_id": self._correlation_id(),
        }

    def update_settings_contract(self, connector_id: str, body: dict) -> dict:
        row = self.db.get(IntegrationConnectorInstance, connector_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        entries: list[ConnectorSettingValue] = []
        settings = body.get("settings") if isinstance(body, dict) else None
        secrets = body.get("secrets") if isinstance(body, dict) else None
        if isinstance(settings, dict):
            secret_keys = self._definition_secret_keys(self.get_registry_definition(row.connector_type))
            entries.extend(
                ConnectorSettingValue(
                    key=key,
                    value=value,
                    secret=_is_secret_key(key) or key in secret_keys,
                    configured=value not in (None, ""),
                )
                for key, value in settings.items()
            )
        if isinstance(secrets, dict):
            entries.extend(
                ConnectorSettingValue(key=key, value=value, secret=True, configured=value not in (None, ""))
                for key, value in secrets.items()
            )
        self._upsert_settings(row, entries)
        self.record_event(
            connector_id=connector_id,
            event_name="connector_settings_updated",
            message="Connector settings were updated; secrets remain write-only.",
            metadata={"secret_values_returned": False},
        )
        return self.get_settings_contract(connector_id)

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
            row.updated_at = now
        self._upsert_settings(
            row,
            [
                ConnectorSettingValue(
                    key=key,
                    value=value,
                    secret=_is_secret_key(key) or key in self._definition_secret_keys(definition),
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
        connector_id: str | None = None,
    ) -> ConnectorProductListResponse:
        self.bootstrap_from_app_config()
        page = max(page, 1)
        page_size = min(max(page_size, 1), 200)
        q = self.db.query(DlProductCache)
        if connector_id:
            q = q.filter(DlProductCache.connector_id == connector_id)
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
            configured=self._is_connector_configured(connector_id or "woocommerce:primary"),
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

    def telemetry_contract(self, connector_id: str | None = None, limit: int = 100) -> dict:
        self.bootstrap_from_app_config()
        instances = self.db.query(IntegrationConnectorInstance).all()
        instance_type = {row.id: row.connector_type for row in instances}
        aggregate = self._telemetry_aggregate(connector_id)
        rows = []
        ids = [connector_id] if connector_id else list(instance_type)
        for cid in ids:
            if not cid:
                continue
            rows.append(
                {
                    "connector_id": cid,
                    "connector_type": instance_type.get(cid, cid.split(":")[0]),
                    "operation": "data_layer_read",
                    "request_count": aggregate.get("total_requests", 0),
                    "error_count": aggregate.get("total_errors", 0),
                    "latency_ms_p50": 0,
                    "latency_ms_p95": 0,
                    "retry_count": 0,
                    "rate_limit_events": 0,
                    "refresh_duration_ms": 0,
                    "records_fetched": aggregate.get("total_products_fetched", 0) + aggregate.get("total_rows_parsed", 0),
                    "bucket_start": _iso(datetime.utcnow()),
                }
            )
        return {
            "items": rows[: min(max(limit, 1), 500)],
            "aggregate": aggregate,
            "correlation_id": self._correlation_id(),
        }

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

    def diagnostics_contract(self, connector_id: str | None = None) -> dict:
        target = "all"
        if connector_id:
            row = self.db.get(IntegrationConnectorInstance, connector_id)
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
            target = row.connector_type
        run = self.diagnostics_run(target)
        status_value = self._diagnostic_status(run["overall_status"])
        result = {
            "connector_id": connector_id or "all",
            "status": status_value,
            "checks": run["checks"],
            "started_at": run["started_at"],
            "finished_at": run["completed_at"],
            "duration_ms": int(run["duration_ms"]),
            "warnings": [c for c in run["checks"] if c["status"] == "skip"],
            "errors": [c for c in run["checks"] if c["status"] == "fail"],
            "correlation_id": self._correlation_id(),
        }
        row = IntegrationConnectorDiagnostic(
            connector_id=result["connector_id"],
            status=status_value,
            checks_json=result["checks"],
            warnings_json=result["warnings"],
            errors_json=result["errors"],
            duration_ms=result["duration_ms"],
            correlation_id=result["correlation_id"],
        )
        self.db.add(row)
        self.db.commit()
        return result

    def health_contract(self, connector_id: str | None = None) -> dict:
        self.bootstrap_from_app_config()
        q = self.db.query(IntegrationConnectorInstance)
        if connector_id:
            q = q.filter(IntegrationConnectorInstance.id == connector_id)
        rows = q.order_by(IntegrationConnectorInstance.connector_type.asc()).all()
        if connector_id and not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        items = [self._instance_to_contract(row) for row in rows]
        summary: dict[str, int] = {status_item.value: 0 for status_item in ConnectorHealthStatus}
        for item in items:
            summary[item["status"]] = summary.get(item["status"], 0) + 1
        if connector_id:
            return {**items[0]["health"], "status": items[0]["status"], "correlation_id": self._correlation_id()}
        return {"summary": summary, "items": items, "correlation_id": self._correlation_id()}

    def list_events_contract(self, limit: int = 100) -> dict:
        events = (
            self.db.query(IntegrationConnectorEvent)
            .order_by(IntegrationConnectorEvent.created_at.desc(), IntegrationConnectorEvent.id.desc())
            .limit(min(max(limit, 1), 500))
            .all()
        )
        return {
            "items": [
                {
                    "id": event.id,
                    "timestamp": _iso(event.created_at),
                    "connector_id": event.connector_id,
                    "event_type": event.event_name,
                    "severity": event.severity,
                    "message": event.message,
                    "actor": None,
                    "result": event.metadata_json.get("result", "recorded") if event.metadata_json else "recorded",
                    "correlation_id": event.metadata_json.get("correlation_id") if event.metadata_json else None,
                }
                for event in events
            ],
            "total": len(events),
            "correlation_id": self._correlation_id(),
        }

    def receive_webhook_contract(
        self,
        connector_type: str,
        connector_id: str,
        payload: dict | list | None,
        raw_body: bytes,
        signature: str | None,
    ) -> dict:
        instance = self.db.get(IntegrationConnectorInstance, connector_id)
        if instance is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector instance not found.")
        webhook_secret = self._secret_configured(instance, "webhook_secret")
        if not webhook_secret:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook signature verifier is not configured.")
        if not signature or not _verify_webhook_signature(webhook_secret, raw_body, signature):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook signature verification failed.")
        accepted = True
        reason = None
        event = IntegrationWebhookEvent(
            connector_type=connector_type,
            connector_id=connector_id,
            accepted=accepted,
            rejected=not accepted,
            reason=reason,
            payload_summary_json={"type": type(payload).__name__},
            correlation_id=self._correlation_id(),
        )
        self.db.add(event)
        self.record_event(
            connector_id=connector_id,
            event_name="webhook_received" if accepted else "webhook_rejected",
            message="Webhook was recorded. Products were not directly mutated.",
            severity="info" if accepted else "warning",
            metadata={"direct_product_mutation": False, "refresh_enqueued": False},
            commit=False,
        )
        self.db.commit()
        return {
            "accepted": accepted,
            "rejected": not accepted,
            "reason": reason,
            "event_id": f"webhook_{event.id}",
            "correlation_id": event.correlation_id,
        }

    def get_polling_contract(self, connector_id: str) -> dict:
        self.get_instance(connector_id)
        policy = self.db.get(IntegrationPollingPolicy, connector_id)
        if policy is None:
            policy = IntegrationPollingPolicy(connector_id=connector_id, enabled=False)
            self.db.add(policy)
            self.db.commit()
            self.db.refresh(policy)
        return self._polling_to_contract(policy)

    def update_polling_contract(self, connector_id: str, body: dict) -> dict:
        self.get_instance(connector_id)
        policy = self.db.get(IntegrationPollingPolicy, connector_id)
        if policy is None:
            policy = IntegrationPollingPolicy(connector_id=connector_id)
            self.db.add(policy)
        policy.enabled = bool(body.get("enabled", False))
        policy.interval_seconds = int(body.get("interval_seconds", policy.interval_seconds or 900))
        policy.jitter_seconds = int(body.get("jitter_seconds", policy.jitter_seconds or 60))
        policy.last_run_at = None
        policy.next_run_at = None
        policy.updated_at = datetime.utcnow()
        self.record_event(
            connector_id=connector_id,
            event_name="polling_policy_updated",
            message="Polling policy updated. Scheduler implementation remains disabled.",
            metadata={"scheduler_implemented": False, "scheduler_started": False},
            commit=False,
        )
        self.db.commit()
        return self._polling_to_contract(policy)

    def write_guard_contract(self, connector_id: str, operation: str) -> dict:
        instance = self.get_instance(connector_id)
        capabilities = instance.connector.capabilities.model_dump()
        self.record_event(
            connector_id=connector_id,
            event_name="write_guard_denied",
            message="Write operations are disabled in FlowHub.",
            severity="warning",
            metadata={"operation": operation, "execution_attempted": False},
        )
        return {
            "allowed": False,
            "status": "blocked",
            "error_code": "write_blocked_FLOWHUB",
            "message": "Write operations are disabled in FlowHub.",
            "capability_advertised": bool(capabilities.get(operation, False)),
            "authorization_granted": False,
            "execution_attempted": False,
            "correlation_id": self._correlation_id(),
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

    def _definition_to_contract(self, definition: ConnectorDefinition, detail: bool = False) -> dict:
        connector = definition.connector
        capabilities = connector.capabilities.model_dump()
        body = {
            "connector_type": connector.identity.type,
            "name": connector.identity.name,
            "version": connector.identity.version,
            "description": f"{connector.identity.name} connector.",
            "capabilities": capabilities,
            "authentication_types": self._authentication_types(capabilities),
            "supported_operations": [key for key, enabled in capabilities.items() if enabled and key not in {"oauth", "api_key", "webhook", "polling"}],
            "supported_transports": self._supported_transports(capabilities),
            "read_only_supported": True,
            "write_supported": bool(capabilities.get("write_prices") or capabilities.get("write_inventory")),
            "FLOWHUB_write_blocked": True,
            "status": "current" if connector.identity.type in {"woocommerce", "nextcloud"} else "future",
        }
        if detail:
            body.update(
                {
                    "settings_schema": [item.model_dump() for item in definition.settings_schema],
                    "secret_fields": [item.key for item in definition.settings_schema if item.secret],
                    "health_checks": ["settings", "data_layer_health"],
                    "diagnostic_checks": [item.model_dump() for item in definition.diagnostics_contract.checks],
                    "webhook_events": ["changed"] if capabilities.get("webhook") else [],
                    "polling_defaults": {"enabled": False, "interval_seconds": 900, "scheduler_implemented": False},
                    "rate_limit_policy": {"local_api_limit": "standard", "connector_limits_honored": True},
                    "data_layer_mappings": ["products", "inventory", "sources"],
                    "known_limitations": ["FlowHub blocks write execution."],
                }
            )
        return body

    def _instance_to_contract(self, row: IntegrationConnectorInstance) -> dict:
        definition = self.get_registry_definition(row.connector_type)
        health_status = self._health_status_for(row).value
        health = self._latest_health(row.id)
        return {
            "id": row.id,
            "connector_type": row.connector_type,
            "name": row.name,
            "enabled": row.enabled,
            "read_only": True,
            "status": health_status,
            "health": {
                "healthy": health_status == ConnectorHealthStatus.HEALTHY.value,
                "last_checked_at": _iso(health.checked_at) if health else None,
                "latency_ms": 0,
                "error_code": health.error_class if health else None,
                "message": health.message if health else ("Connector has no Data Layer health record yet."),
            },
            "capabilities": definition.connector.capabilities.model_dump(),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
            "last_checked_at": _iso(health.checked_at) if health else None,
            "runtime_write_blocked": True,
            "capability_authorizes_write": False,
        }

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
            secret = item.secret or _is_secret_key(item.key)
            configured = item.configured or item.value not in (None, "")
            value = item.value if secret and item.key == "webhook_secret" else None if secret else item.value
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

    def _polling_to_contract(self, policy: IntegrationPollingPolicy) -> dict:
        return {
            "connector_id": policy.connector_id,
            "enabled": policy.enabled,
            "interval_seconds": policy.interval_seconds,
            "jitter_seconds": policy.jitter_seconds,
            "last_run_at": _iso(policy.last_run_at),
            "next_run_at": _iso(policy.next_run_at),
            "scheduler_implemented": False,
            "correlation_id": self._correlation_id(),
        }

    def _authentication_types(self, capabilities: dict) -> list[str]:
        auth: list[str] = []
        if capabilities.get("api_key"):
            auth.append("api_key")
        if capabilities.get("oauth"):
            auth.append("oauth")
        return auth

    def _supported_transports(self, capabilities: dict) -> list[str]:
        transports = ["rest_api"]
        if capabilities.get("webhook"):
            transports.append("webhook")
        if capabilities.get("polling"):
            transports.append("polling")
        return transports

    def _definition_secret_keys(self, definition: ConnectorDefinition) -> set[str]:
        return {item.key for item in definition.settings_schema if item.secret}

    def _diagnostic_status(self, status_value: str) -> str:
        if status_value == "ok":
            return ConnectorHealthStatus.HEALTHY.value
        if status_value == "skip":
            return ConnectorHealthStatus.DEGRADED.value
        return ConnectorHealthStatus.ERROR.value

    def _correlation_id(self) -> str:
        return f"corr_{uuid.uuid4().hex[:12]}"

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

    def _secret_configured(self, row: IntegrationConnectorInstance, key: str) -> str | None:
        for item in row.settings:
            if item.key == key and item.secret and item.configured:
                return str(item.value_json or "")
        return None

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


def _is_secret_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in _SECRET_KEYS


def _verify_webhook_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode("utf-8"), raw_body, sha256).hexdigest()
    candidates = {expected, f"sha256={expected}"}
    return any(hmac.compare_digest(signature.strip(), candidate) for candidate in candidates)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"
