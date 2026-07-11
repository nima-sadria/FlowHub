"""Commerce Hub service.

Presents product-facing Sources and Channels while reusing Integration Platform
records for local settings, health, and capability metadata. Commerce Hub never
executes external marketplace writes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from time import monotonic

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.read.woocommerce import WooCommerceProductReadAdapter
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import ping as ping_woocommerce
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache, DlRefreshJob
from app.flowhub.data_layer.health_service import ConnectorHealthService
from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.nextcloud import NextcloudClient
from app.flowhub.config.nextcloud_url import NextcloudUrlValidationError, normalize_nextcloud_url
from app.flowhub.integration_platform.contracts import ConnectorCapabilities
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integration_platform.registry import registry
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.read_engine.manual import ManualReadService
from app.flowhub.read_engine.service import IncrementalReadEngine
from app.flowhub.security.upstream_errors import UpstreamServiceError, normalize_upstream_error
from app.flowhub.sources.spreadsheet_source import (
    SpreadsheetSourceReadService,
    normalize_read_policy,
    normalize_source_mapping,
    serialize_read_policy,
    serialize_source_mapping,
)

ACCESS_MODE_READ_ONLY = "read_only"
ACCESS_MODE_WRITE_ENABLED = "write_enabled"
ACCESS_MODES = frozenset({ACCESS_MODE_READ_ONLY, ACCESS_MODE_WRITE_ENABLED})


_CHANNELS = [
    {
        "id": "woocommerce:primary",
        "provider": "woocommerce",
        "name": "WooCommerce",
        "status": "current",
        "implemented": True,
        "placeholder": False,
    },
    {
        "id": "snappshop:main",
        "provider": "snappshop",
        "name": "Snapp Shop",
        "status": "planned",
        "implemented": False,
        "placeholder": True,
    },
    {
        "id": "tapsishop:main",
        "provider": "tapsishop",
        "name": "Tapsi Shop",
        "status": "planned",
        "implemented": False,
        "placeholder": True,
    },
    {
        "id": "digikala:main",
        "provider": "digikala",
        "name": "Digikala",
        "status": "future",
        "implemented": False,
        "placeholder": True,
    },
    {
        "id": "technolife:main",
        "provider": "technolife",
        "name": "Technolife",
        "status": "future",
        "implemented": False,
        "placeholder": True,
    },
    {
        "id": "shopify:main",
        "provider": "shopify",
        "name": "Shopify",
        "status": "future",
        "implemented": False,
        "placeholder": True,
    },
]

_SOURCES = [
    {
        "id": "nextcloud:primary",
        "provider": "nextcloud",
        "name": "Nextcloud",
        "type": "Source",
        "status": "current",
        "implemented": True,
        "placeholder": False,
        "credential_status": "not_configured",
        "last_health_check": None,
        "data_role": "Spreadsheet price input",
        "action_label": "Manage",
        "action_href": "/commerce?tab=sources",
    },
    {
        "id": "csv:import",
        "provider": "csv",
        "name": "CSV",
        "type": "Source",
        "status": "future",
        "implemented": False,
        "placeholder": True,
        "credential_status": "not_required",
        "last_health_check": None,
        "data_role": "File import input",
        "action_label": "Manage",
        "action_href": "/commerce?tab=sources",
    },
    {
        "id": "gsheets:price-list",
        "provider": "gsheets",
        "name": "Google Sheets",
        "type": "Source",
        "status": "future",
        "implemented": False,
        "placeholder": True,
        "credential_status": "not_configured",
        "last_health_check": None,
        "data_role": "Spreadsheet price input",
        "action_label": "Manage",
        "action_href": "/commerce?tab=sources",
    },
    {
        "id": "erp:api-import",
        "provider": "erp",
        "name": "ERP / API Import",
        "type": "Source",
        "status": "future",
        "implemented": False,
        "placeholder": True,
        "credential_status": "not_configured",
        "last_health_check": None,
        "data_role": "System import input",
        "action_label": "Manage",
        "action_href": "/commerce?tab=sources",
    },
]


class CommerceHubService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.integration = IntegrationPlatformService(db)

    def list_sources(self) -> dict:
        self.integration.bootstrap_from_app_config()
        items = [self._source_contract(item) for item in _SOURCES]
        return {
            "items": items,
            "runtime_write_blocked": True,
            "read_only": True,
            "relationship_map": self.relationship_map(),
        }

    def list_channels(self) -> dict:
        self.integration.bootstrap_from_app_config()
        return {
            "items": [self._channel_contract(item) for item in _CHANNELS],
            "runtime_write_blocked": True,
            "read_only": True,
            "write_blocked": True,
        }

    def list_source_types(self) -> dict:
        return {
            "items": [self._type_contract(item, kind="Source") for item in _SOURCES],
            "runtime_write_blocked": True,
            "read_only": True,
        }

    def list_channel_types(self) -> dict:
        return {
            "items": [self._type_contract(item, kind="Channel") for item in _CHANNELS],
            "runtime_write_blocked": True,
            "read_only": True,
            "write_blocked": True,
        }

    def get_channel(self, channel_id: str) -> dict:
        return self._channel_contract(self._channel_meta(channel_id), detail=True)

    def get_source(self, source_id: str) -> dict:
        return self._source_contract(self._source_meta(source_id), detail=True)

    def get_channel_health(self, channel_id: str) -> dict:
        item = self._channel_contract(self._channel_meta(channel_id))
        return {
            "channel_id": channel_id,
            "status": item["status"],
            "health": item["health"],
            "last_health_check": item["last_health_check"],
            "runtime_write_blocked": True,
            "read_only": True,
        }

    def get_channel_capabilities(self, channel_id: str) -> dict:
        item = self._channel_contract(self._channel_meta(channel_id), detail=True)
        return {
            "channel_id": channel_id,
            "capabilities": item["capabilities"],
            "capabilities_summary": item["capabilities_summary"],
            "runtime_write_blocked": True,
            "capability_authorizes_write": False,
        }

    async def test_channel_connection(self, channel_id: str) -> dict:
        meta = self._channel_meta(channel_id)
        item = self._channel_contract(meta)
        configured = item["credential_status"] == "configured"
        placeholder = bool(meta["placeholder"])
        if placeholder:
            return self._placeholder_connection_result()
        if str(meta["provider"]) == "woocommerce":
            return await self._test_woocommerce_channel_connection(configured)
        return self._unsupported_connection_result()

    async def refresh_channel_cache(self, channel_id: str, actor: str) -> dict:
        meta = self._channel_meta(channel_id)
        if str(meta["provider"]) != "woocommerce" or bool(meta.get("placeholder")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product cache refresh is not available for this channel.")
        instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        if instance is None or not instance.enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "CHANNEL_DISABLED", "message": "WooCommerce channel is disabled."},
            )

        started = datetime.utcnow()
        adapter: WooCommerceProductReadAdapter | None = None
        self.integration.record_event(
            connector_id=channel_id,
            event_name="product_cache_refresh_started",
            message="Manual WooCommerce product cache refresh started.",
            metadata={
                "actor": actor,
                "read_only": True,
                "external_write": False,
                "stock_write": False,
                "automatic_apply": False,
            },
        )
        try:
            configured_adapter = ManualReadService(self.db).adapter_for(channel_id)
            if not isinstance(configured_adapter, WooCommerceProductReadAdapter):
                raise HTTPException(status.HTTP_409_CONFLICT, "woocommerce_cache_refresh_unsupported")
            adapter = configured_adapter
            progress = await IncrementalReadEngine(self.db).run_manual(
                adapter,
                triggered_by=actor,
                force_full=True,
            )
            warnings = list(adapter.warnings)
            result_status = "completed_with_warnings" if warnings else "completed"
            completed = datetime.utcnow()
            self._mark_latest_refresh_status(channel_id, result_status, completed)
            result = self._cache_refresh_result(
                adapter,
                ok=True,
                status_value=result_status,
                cache_rows_upserted=progress.products_stored,
                warnings=warnings,
                errors=[],
                started=started,
                completed=completed,
            )
            self.integration.record_event(
                connector_id=channel_id,
                event_name="product_cache_refresh_completed",
                message="Manual WooCommerce product cache refresh completed.",
                metadata={**result, "actor": actor, "external_write": False},
            )
            return result
        except Exception as exc:
            completed = datetime.utcnow()
            cache_rows_upserted, result_status = self._mark_latest_refresh_failed(channel_id, exc, completed)
            safe_error = normalize_upstream_error(exc, source="woocommerce")
            errors = [safe_error["message"]]
            result = self._cache_refresh_result(
                adapter,
                ok=False,
                status_value=result_status,
                cache_rows_upserted=cache_rows_upserted,
                warnings=list(adapter.warnings) if adapter else [],
                errors=errors,
                started=started,
                completed=completed,
            )
            result["error"] = safe_error
            self.integration.record_event(
                connector_id=channel_id,
                event_name="product_cache_refresh_failed",
                message="Manual WooCommerce product cache refresh failed.",
                severity="error",
                metadata={**result, "actor": actor, "external_write": False},
            )
            return result

    async def test_source_connection(self, source_id: str) -> dict:
        meta = self._source_meta(source_id)
        item = self._source_contract(meta)
        configured = item["credential_status"] == "configured"
        placeholder = bool(meta["placeholder"])
        if placeholder:
            message = f"{meta['name']} is a read-only planned source. No external call was performed."
        elif str(meta["provider"]) == "nextcloud":
            return await self._test_nextcloud_source_connection()
        elif configured:
            message = "Local source configuration is present. No external call was performed."
        else:
            message = "Source is not configured. No external call was performed."
        return {
            "ok": False,
            "status": "configured" if configured else "not_configured",
            "message": message,
            "external_call_performed": False,
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
            "correlation_id": self._correlation_id(),
        }

    async def browse_source_files(self, source_id: str, body: dict) -> dict:
        meta = self._source_meta(source_id)
        if str(meta["provider"]) != "nextcloud" or bool(meta.get("placeholder")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source browser is not available.")
        values = self._nextcloud_values(body, allow_stored=True)
        if not values["url"] or not values["password"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nextcloud URL, username, and app password are required to browse files.")
        normalized = self._normalize_nextcloud_url(values["url"], values["username"])
        if not normalized["username"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nextcloud URL, username, and app password are required to browse files.")
        path = str(body.get("path") or body.get("current_path") or "/") if isinstance(body, dict) else "/"
        client = NextcloudClient(
            normalized["server_root_url"],
            normalized["username"],
            values["password"],
            webdav_files_root_url=normalized["webdav_files_root_url"],
        )
        try:
            result = await client.browse_directory(path)
        except IntegrationError as exc:
            if exc.status_code is not None and exc.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                raise HTTPException(exc.status_code, exc.message) from exc
            raise UpstreamServiceError(exc, source="nextcloud") from exc
        return {
            **result,
            "source_id": source_id,
            "external_call_performed": True,
            "credentials_returned": False,
        }

    async def read_source_now(self, source_id: str, actor: str, actor_id: int | str | None = None) -> dict:
        meta = self._source_meta(source_id)
        if str(meta["provider"]) != "nextcloud" or bool(meta.get("placeholder")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source read is not available.")
        instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        if instance is None or not instance.enabled:
            raise HTTPException(status.HTTP_409_CONFLICT, "Source must be enabled before Read now.")
        reader = SpreadsheetSourceReadService(self.db)
        result = await reader.read_nextcloud_spreadsheet(
            triggered_by=actor,
            triggered_by_id=actor_id,
            manual=True,
        )
        return reader.manual_read_response(result)

    def update_source_settings(self, source_id: str, body: dict) -> dict:
        meta = self._source_meta(source_id)
        provider = str(meta["provider"])
        if registry.get_definition(provider) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source settings are not available.")
        if provider == "nextcloud":
            self._validate_nextcloud_source_body(body)
        self._ensure_instance(meta)
        self._update_instance_state(meta, body, access_mode=ACCESS_MODE_READ_ONLY)
        if provider == "nextcloud":
            self._persist_nextcloud_app_config(body)
        result = self.integration.update_settings_contract(source_id, self._settings_body(body))
        return {
            **result,
            "source_id": source_id,
            "access_mode": ACCESS_MODE_READ_ONLY,
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
            "write_pipeline_eligible": False,
        }

    def update_channel_settings(self, channel_id: str, body: dict) -> dict:
        meta = self._channel_meta(channel_id)
        provider = str(meta["provider"])
        if registry.get_definition(provider) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel settings are not available.")
        self._ensure_instance(meta)
        access_mode = self._requested_channel_access_mode(meta, body)
        self._update_instance_state(meta, body, access_mode=access_mode)
        if provider == "woocommerce":
            self._persist_woocommerce_app_config(body)
        result = self.integration.update_settings_contract(channel_id, self._settings_body(body))
        instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        effective_access_mode = self._access_mode(instance)
        write_pipeline_eligible = self._write_pipeline_eligible(meta, instance)
        return {
            **result,
            "channel_id": channel_id,
            "access_mode": effective_access_mode,
            "read_only": effective_access_mode == ACCESS_MODE_READ_ONLY,
            "runtime_write_blocked": True,
            "write_blocked": not write_pipeline_eligible,
            "write_pipeline_eligible": write_pipeline_eligible,
        }

    def relationship_map(self) -> dict:
        return {
            "nodes": ["Source", "FlowHub / Data Layer", "Channel"],
            "example": ["Nextcloud", "Data Layer", "WooCommerce"],
            "runtime_write_blocked": True,
            "read_only": True,
        }

    def _source_contract(self, meta: dict, detail: bool = False) -> dict:
        provider = str(meta["provider"])
        definition = registry.get_definition(provider)
        instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        if provider == "nextcloud" and instance is None:
            self.integration.bootstrap_from_app_config()
            instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        health = self._health(str(meta["id"]))
        configured = self._instance_configured(instance)
        read_status = SpreadsheetSourceReadService(self.db).read_status() if provider == "nextcloud" else None
        body = {
            **meta,
            "status": self._status(meta, instance, health),
            "credential_status": "configured" if configured else "not_configured",
            "last_health_check": self._iso(health.checked_at) if health else None,
            "health": self._health_contract(health),
            "runtime_write_blocked": True,
            "read_only": True,
            "settings_available": definition is not None,
        }
        if read_status is not None:
            body["read_status"] = read_status
            body["read_policy"] = {
                key: read_status[key]
                for key in ("enabled", "max_reads_per_24h", "manual_read_allowed", "reads_used_last_24h", "reads_remaining", "reset_at", "last_read_at")
            }
        if detail:
            body["settings_schema"] = [
                item.model_dump() for item in definition.settings_schema
            ] if definition else []
            body["secrets"] = self._secret_status(instance)
        return body

    def _channel_contract(self, meta: dict, detail: bool = False) -> dict:
        provider = str(meta["provider"])
        definition = registry.get_definition(provider)
        instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        if provider == "woocommerce":
            self.integration.bootstrap_from_app_config()
            instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        health = self._health(str(meta["id"]))
        configured = self._instance_configured(instance)
        access_mode = self._access_mode(instance)
        write_pipeline_eligible = self._write_pipeline_eligible(meta, instance)
        capabilities = definition.connector.capabilities if definition else ConnectorCapabilities()
        cache_rows = (
            self.db.query(DlProductCache)
            .filter(DlProductCache.connector_id == str(meta["id"]), DlProductCache.exists.is_(True))
            .all()
            if provider == "woocommerce"
            else []
        )
        cached_variations = sum(1 for row in cache_rows if (row.product_type or "").lower() == "variation")
        latest_refresh = (
            self.db.query(DlRefreshJob)
            .filter(
                DlRefreshJob.connector_id == str(meta["id"]),
                DlRefreshJob.entity_type == "products",
            )
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
            if provider == "woocommerce"
            else None
        )
        body = {
            "id": meta["id"],
            "provider": provider,
            "name": meta["name"],
            "type": "Channel",
            "status": self._status(meta, instance, health),
            "implemented": meta["implemented"],
            "placeholder": meta["placeholder"],
            "access_mode": access_mode,
            "read_only": access_mode == ACCESS_MODE_READ_ONLY,
            "write_blocked": not write_pipeline_eligible,
            "write_pipeline_eligible": write_pipeline_eligible,
            "runtime_write_blocked": True,
            "credential_status": "configured" if configured else "not_configured",
            "last_health_check": self._iso(health.checked_at) if health else None,
            "health": self._health_contract(health),
            "capabilities": capabilities.model_dump(),
            "capabilities_summary": self._capabilities_summary(capabilities),
            "settings_available": definition is not None,
            "cached_products": len(cache_rows) - cached_variations,
            "cached_variations": cached_variations,
            "last_cache_refresh": self._iso(
                latest_refresh.completed_at or latest_refresh.started_at or latest_refresh.created_at
            ) if latest_refresh else None,
            "cache_refresh_status": latest_refresh.status if latest_refresh else "not_run",
        }
        if detail:
            body["settings_schema"] = [
                item.model_dump() for item in definition.settings_schema
            ] if definition else []
            body["secrets"] = self._secret_status(instance)
        return body

    def _cache_refresh_result(
        self,
        adapter: WooCommerceProductReadAdapter | None,
        *,
        ok: bool,
        status_value: str,
        cache_rows_upserted: int,
        warnings: list[str],
        errors: list[str],
        started: datetime,
        completed: datetime,
    ) -> dict:
        return {
            "ok": ok,
            "status": status_value,
            "products_read": adapter.products_read if adapter else 0,
            "variable_products_read": adapter.variable_products_read if adapter else 0,
            "variations_read": adapter.variations_read if adapter else 0,
            "cache_rows_upserted": cache_rows_upserted,
            "warnings": warnings,
            "errors": errors,
            "started_at": self._iso(started),
            "completed_at": self._iso(completed),
            "read_only": True,
            "external_write": False,
            "stock_write": False,
            "source_write": False,
            "dry_run_created": False,
            "approval_created": False,
            "apply_executed": False,
            "credentials_returned": False,
        }

    def _mark_latest_refresh_status(self, channel_id: str, status_value: str, completed: datetime) -> None:
        job = (
            self.db.query(DlRefreshJob)
            .filter(DlRefreshJob.connector_id == channel_id, DlRefreshJob.entity_type == "products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )
        if job is None:
            return
        job.status = status_value
        job.completed_at = completed
        self.db.commit()

    def _mark_latest_refresh_failed(self, channel_id: str, exc: Exception, completed: datetime) -> tuple[int, str]:
        job = (
            self.db.query(DlRefreshJob)
            .filter(DlRefreshJob.connector_id == channel_id, DlRefreshJob.entity_type == "products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )
        if job is None:
            return 0, "failed"
        stored = int((job.meta or {}).get("products_stored") or 0)
        status_value = "partial_failed" if stored > 0 else "failed"
        job.status = status_value
        job.completed_at = completed
        job.error_message = self._safe_cache_refresh_error(exc)[:500]
        self.db.commit()
        return stored, status_value

    def _safe_cache_refresh_error(self, exc: Exception) -> str:
        return str(normalize_upstream_error(exc, source="woocommerce")["message"])

    def _ensure_instance(self, meta: dict) -> IntegrationConnectorInstance:
        row = self.db.get(IntegrationConnectorInstance, meta["id"])
        if row is not None:
            return row
        definition = registry.get_definition(str(meta["provider"]))
        if definition is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel type is not available.")
        row = IntegrationConnectorInstance(
            id=str(meta["id"]),
            connector_type=str(meta["provider"]),
            name=str(meta["name"]),
            version=definition.connector.identity.version,
            enabled=False,
            read_only=True,
            status="disabled",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def _update_instance_state(self, meta: dict, body: dict, *, access_mode: str) -> None:
        row = self.db.get(IntegrationConnectorInstance, meta["id"])
        if row is None:
            return
        display_name = str(body.get("display_name") or "").strip() if isinstance(body, dict) else ""
        if display_name:
            row.name = display_name
        enabled = body.get("enabled") if isinstance(body, dict) else None
        if enabled is not None:
            row.enabled = bool(enabled) and not bool(meta.get("placeholder"))
        elif access_mode == ACCESS_MODE_WRITE_ENABLED:
            row.enabled = not bool(meta.get("placeholder"))
        row.read_only = access_mode != ACCESS_MODE_WRITE_ENABLED
        row.status = "disabled" if not row.enabled else "configured"
        row.updated_at = datetime.utcnow()
        self.db.commit()

    def _settings_body(self, body: dict) -> dict:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        description = str(body.get("description") or "").strip() if isinstance(body, dict) else ""
        if description:
            settings["description"] = description
        return {
            "settings": settings,
            "secrets": body.get("secrets") if isinstance(body, dict) else None,
        }

    def _requested_channel_access_mode(self, meta: dict, body: dict) -> str:
        raw = None
        if isinstance(body, dict):
            raw = body.get("access_mode", body.get("accessMode"))
        if raw in (None, ""):
            return self._access_mode(self.db.get(IntegrationConnectorInstance, meta["id"]))
        access_mode = str(raw).strip().lower().replace("-", "_")
        if access_mode not in ACCESS_MODES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "access_mode must be read_only or write_enabled.")
        if access_mode == ACCESS_MODE_WRITE_ENABLED and not self._write_pipeline_supported(meta):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "channel_write_access_unsupported")
        return access_mode

    def _access_mode(self, instance: IntegrationConnectorInstance | None) -> str:
        if instance is None or instance.read_only:
            return ACCESS_MODE_READ_ONLY
        return ACCESS_MODE_WRITE_ENABLED

    def _write_pipeline_supported(self, meta: dict) -> bool:
        return str(meta.get("id")) == "woocommerce:primary" and not bool(meta.get("placeholder"))

    def _write_pipeline_eligible(self, meta: dict, instance: IntegrationConnectorInstance | None) -> bool:
        return self._write_pipeline_supported(meta) and self._access_mode(instance) == ACCESS_MODE_WRITE_ENABLED

    async def _test_woocommerce_channel_connection(self, configured: bool) -> dict:
        creds = self._woocommerce_credentials()
        if not configured or creds is None:
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status": "not_configured",
                "http_status": None,
                "latency_ms": None,
                "checked_at": self._checked_at(),
                "message": "WooCommerce is not configured. No external call was performed.",
                "external_call_performed": False,
            }

        started = monotonic()
        checked_at = self._checked_at()
        try:
            result = await ping_woocommerce(creds)
            latency_ms = round((monotonic() - started) * 1000, 2)
            http_status = int(result.get("http_status") or 200)
            records_checked = int(result.get("records_checked") or 0)
            return {
                **self._connection_base(),
                "ok": True,
                "connected": True,
                "authenticated": True,
                "status": "connected",
                "http_status": http_status,
                "latency_ms": latency_ms,
                "checked_at": checked_at,
                "external_call_performed": True,
                "message": f"Connected to WooCommerce. Read-only API probe returned HTTP {http_status} with {records_checked} product record(s) checked.",
            }
        except ConnectorError as exc:
            latency_ms = round((monotonic() - started) * 1000, 2)
            authenticated = exc.code not in {ConnectorErrorCode.AUTH_FAILED, ConnectorErrorCode.PERMISSION}
            safe_error = normalize_upstream_error(exc, source="woocommerce")
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": authenticated,
                "status": "authentication_failed" if not authenticated else "error",
                "http_status": exc.http_status,
                "latency_ms": latency_ms,
                "checked_at": checked_at,
                "external_call_performed": True,
                "message": safe_error["message"],
                "code": safe_error["code"],
            }

    def _woocommerce_credentials(self) -> WooCommerceCredentials | None:
        url = self.integration.config.get("woocommerce.url")
        key = self.integration.config.get("woocommerce.key")
        secret = self.integration.config.get("woocommerce.secret")
        if not url or not key or not secret:
            return None
        return WooCommerceCredentials(url=url.rstrip("/"), key=key, secret=secret)

    async def _test_nextcloud_source_connection(self) -> dict:
        values = self._nextcloud_values({}, allow_stored=True)
        if not values["url"] or not values["password"]:
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status": "error",
                "http_status": None,
                "latency_ms": None,
                "checked_at": self._checked_at(),
                "message": "Nextcloud is not configured. No external call was performed.",
                "webdav_reachable": False,
                "spreadsheet_found": None,
                "normalized_base_url": "",
                "normalized_webdav_url": "",
                "external_call_performed": False,
            }

        checked_at = self._checked_at()
        started = monotonic()
        try:
            normalized = self._normalize_nextcloud_url(values["url"], values["username"])
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            message = str(detail.get("message") or exc.detail)
            return self._nextcloud_test_failure(
                started,
                checked_at,
                message,
                normalized_base_url="",
                normalized_webdav_url="",
                webdav_reachable=False,
                spreadsheet_found=None,
                external=False,
                error_class="invalid_url",
                code=str(detail.get("code") or "INVALID_NEXTCLOUD_URL"),
            )
        if not normalized["username"]:
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status": "error",
                "http_status": None,
                "latency_ms": None,
                "checked_at": checked_at,
                "message": "Nextcloud is not configured. No external call was performed.",
                "webdav_reachable": False,
                "spreadsheet_found": None,
                "normalized_base_url": normalized["server_root_url"],
                "normalized_webdav_url": normalized["webdav_files_root_url"],
                "external_call_performed": False,
            }
        normalized_webdav_url = normalized["webdav_files_root_url"]
        client = NextcloudClient(
            normalized["server_root_url"],
            normalized["username"],
            values["password"],
            webdav_files_root_url=normalized_webdav_url,
        )
        try:
            await client.browse_directory("/")
            spreadsheet_path = values.get("spreadsheet_path") or ""
            spreadsheet_found: bool | None = None
            if spreadsheet_path:
                try:
                    item = await client.get_resource_info(spreadsheet_path)
                except IntegrationError as exc:
                    return self._nextcloud_test_failure(
                        started,
                        checked_at,
                        "Spreadsheet not found.",
                        normalized_base_url=normalized["server_root_url"],
                        normalized_webdav_url=normalized_webdav_url,
                        webdav_reachable=True,
                        spreadsheet_found=False,
                        external=True,
                        http_status=exc.status_code,
                        error_class="spreadsheet_not_found",
                    )
                if item["type"] != "file":
                    return self._nextcloud_test_failure(
                        started,
                        checked_at,
                        "Spreadsheet Path points to a directory.",
                        normalized_base_url=normalized["server_root_url"],
                        normalized_webdav_url=normalized_webdav_url,
                        webdav_reachable=True,
                        spreadsheet_found=False,
                        external=True,
                        error_class="spreadsheet_invalid",
                    )
                if item.get("supported") is not True:
                    return self._nextcloud_test_failure(
                        started,
                        checked_at,
                        "Spreadsheet Path must be a supported .xlsx file.",
                        normalized_base_url=normalized["server_root_url"],
                        normalized_webdav_url=normalized_webdav_url,
                        webdav_reachable=True,
                        spreadsheet_found=False,
                        external=True,
                        error_class="spreadsheet_unsupported",
                    )
                spreadsheet_found = True
            latency_ms = round((monotonic() - started) * 1000, 2)
            message = (
                "Connection successful. Spreadsheet found."
                if spreadsheet_found is True
                else "Connection successful. Select a spreadsheet file to enable preview."
            )
            self._record_source_health("nextcloud:primary", "healthy", latency_ms, message, None)
            return {
                **self._connection_base(),
                "ok": True,
                "connected": True,
                "authenticated": True,
                "status": "operational",
                "http_status": None,
                "latency_ms": latency_ms,
                "checked_at": checked_at,
                "message": message,
                "webdav_reachable": True,
                "spreadsheet_found": spreadsheet_found,
                "normalized_base_url": normalized["server_root_url"],
                "normalized_webdav_url": normalized_webdav_url,
                "external_call_performed": True,
            }
        except IntegrationError as exc:
            return self._nextcloud_test_failure(
                started,
                checked_at,
                self._safe_nextcloud_error_message(exc),
                normalized_base_url=normalized["server_root_url"],
                normalized_webdav_url=normalized_webdav_url,
                webdav_reachable=False,
                spreadsheet_found=None,
                external=True,
                http_status=exc.status_code,
                error_class=self._nextcloud_error_class(exc),
            )
        except HTTPException:
            raise
        except Exception as exc:
            return self._nextcloud_test_failure(
                started,
                checked_at,
                "WebDAV not reachable.",
                normalized_base_url=normalized["server_root_url"],
                normalized_webdav_url=normalized_webdav_url,
                webdav_reachable=False,
                spreadsheet_found=None,
                external=True,
                error_class=type(exc).__name__,
            )

    def _nextcloud_test_failure(
        self,
        started: float,
        checked_at: str,
        message: str,
        *,
        normalized_base_url: str,
        normalized_webdav_url: str,
        webdav_reachable: bool,
        spreadsheet_found: bool | None,
        external: bool,
        http_status: int | None = None,
        error_class: str | None = None,
        code: str | None = None,
    ) -> dict:
        latency_ms = round((monotonic() - started) * 1000, 2)
        self._record_source_health("nextcloud:primary", "unhealthy", latency_ms, message, error_class or "connection_failed")
        return {
            **self._connection_base(),
            "ok": False,
            "connected": False,
            "authenticated": False,
            "status": "error",
            "http_status": http_status,
            "latency_ms": latency_ms,
            "checked_at": checked_at,
            "message": message,
            **({"code": code} if code else {}),
            "webdav_reachable": webdav_reachable,
            "spreadsheet_found": spreadsheet_found,
            "normalized_base_url": normalized_base_url,
            "normalized_webdav_url": normalized_webdav_url,
            "external_call_performed": external,
        }

    def _record_source_health(
        self,
        source_id: str,
        status_value: str,
        latency_ms: float | None,
        detail: str,
        error_class: str | None,
    ) -> None:
        ConnectorHealthService(self.db).upsert(
            source_id,
            "source",
            status_value,
            latency_ms=latency_ms,
            detail=detail[:500],
            error_class=error_class,
        )

    def _safe_nextcloud_error_message(self, exc: IntegrationError) -> str:
        return str(normalize_upstream_error(exc, source="nextcloud")["message"])

    def _nextcloud_error_class(self, exc: IntegrationError) -> str:
        message = (exc.message or "").lower()
        if "authentication failed" in message or "access denied" in message:
            return "authentication_failed"
        if "not found" in message:
            return "webdav_not_found"
        if "timed out" in message:
            return "timeout"
        if "could not connect" in message or "connection" in message:
            return "network"
        return "connection_failed"

    def _nextcloud_values(self, body: dict, *, allow_stored: bool) -> dict[str, str]:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        values = {
            "url": str(settings.get("url") or "").strip(),
            "username": str(settings.get("username") or "").strip(),
            "password": str(secrets.get("password") or settings.get("password") or "").strip(),
            "spreadsheet_path": str(settings.get("spreadsheet_path") or "").strip(),
            "webdav_files_root_url": str(settings.get("webdav_files_root_url") or "").strip(),
        }
        if allow_stored:
            values = {
                "url": values["url"] or str(self.integration.config.get("nextcloud.url") or "").strip(),
                "username": values["username"] or str(self.integration.config.get("nextcloud.username") or "").strip(),
                "password": values["password"] or str(self.integration.config.get("nextcloud.password") or "").strip(),
                "spreadsheet_path": values["spreadsheet_path"] or str(self.integration.config.get("nextcloud.spreadsheet_path") or "").strip(),
                "webdav_files_root_url": values["webdav_files_root_url"] or str(self.integration.config.get("nextcloud.webdav_files_root_url") or "").strip(),
            }
        return values

    def _validate_nextcloud_source_body(self, body: dict) -> None:
        values = self._nextcloud_values(body, allow_stored=False)
        if values["url"]:
            self._normalize_nextcloud_url(values["url"], values["username"])
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        if "source_mapping" in settings:
            normalize_source_mapping(settings.get("source_mapping"))
        if "source_read_policy" in settings:
            normalize_read_policy(settings.get("source_read_policy"))
        worksheet_mode = str(settings.get("worksheet_mode") or "all").strip().lower()
        if worksheet_mode not in {"all", "selected"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "worksheet_mode must be all or selected.")
        if worksheet_mode == "selected" and not str(settings.get("worksheet_name") or "").strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "worksheet_name is required when selected worksheet mode is enabled.")

    def _validate_nextcloud_base_url(self, raw_url: str) -> str:
        return self._normalize_nextcloud_url(raw_url, "")["server_root_url"]

    def _normalize_nextcloud_url(self, raw_url: str, configured_username: str = "") -> dict[str, str]:
        try:
            return normalize_nextcloud_url(raw_url, configured_username)
        except NextcloudUrlValidationError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": exc.code, "message": str(exc)},
            ) from exc

    def _persist_woocommerce_app_config(self, body: dict) -> None:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        pairs: dict[str, str] = {}
        if settings.get("url"):
            pairs["woocommerce.url"] = str(settings["url"]).strip().rstrip("/")
        if secrets.get("key"):
            pairs["woocommerce.key"] = str(secrets["key"])
        if secrets.get("secret"):
            pairs["woocommerce.secret"] = str(secrets["secret"])
        if pairs:
            self.integration.config.set_many(pairs, updated_by="commerce_hub")

    def _persist_nextcloud_app_config(self, body: dict) -> None:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        pairs: dict[str, str] = {}
        normalized = self._normalize_nextcloud_url(str(settings.get("url") or ""), str(settings.get("username") or "")) if settings.get("url") else None
        if normalized:
            pairs["nextcloud.url"] = normalized["server_root_url"]
            if normalized["webdav_files_root_url"]:
                pairs["nextcloud.webdav_files_root_url"] = normalized["webdav_files_root_url"]
            if normalized["username"]:
                pairs["nextcloud.username"] = normalized["username"]
        elif settings.get("username"):
            pairs["nextcloud.username"] = str(settings["username"]).strip()
        if secrets.get("password"):
            pairs["nextcloud.password"] = str(secrets["password"])
        if settings.get("spreadsheet_path"):
            pairs["nextcloud.spreadsheet_path"] = str(settings["spreadsheet_path"]).strip()
        if "source_mapping" in settings:
            pairs["nextcloud.source_mapping"] = serialize_source_mapping(normalize_source_mapping(settings.get("source_mapping")))
        if "source_read_policy" in settings:
            pairs["nextcloud.source_read_policy"] = serialize_read_policy(normalize_read_policy(settings.get("source_read_policy")))
        if settings.get("worksheet_mode"):
            pairs["nextcloud.worksheet_mode"] = str(settings["worksheet_mode"]).strip().lower()
        if "worksheet_name" in settings:
            pairs["nextcloud.worksheet_name"] = str(settings.get("worksheet_name") or "").strip()
        if pairs:
            self.integration.config.set_many(pairs, updated_by="commerce_hub")

    def _placeholder_connection_result(self) -> dict:
        return {
            **self._connection_base(),
            "ok": False,
            "connected": False,
            "authenticated": False,
            "status": "placeholder",
            "http_status": None,
            "latency_ms": None,
            "checked_at": self._checked_at(),
            "message": "Real connector is not implemented yet. No external call was performed.",
            "external_call_performed": False,
        }

    def _unsupported_connection_result(self) -> dict:
        return {
            **self._connection_base(),
            "ok": False,
            "connected": False,
            "authenticated": False,
            "status": "unsupported",
            "http_status": None,
            "latency_ms": None,
            "checked_at": self._checked_at(),
            "message": "Real connector is not implemented yet. No external call was performed.",
            "external_call_performed": False,
        }

    def _connection_base(self) -> dict:
        return {
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
            "correlation_id": self._correlation_id(),
        }

    def _channel_meta(self, channel_id: str) -> dict:
        for item in _CHANNELS:
            if item["id"] == channel_id or item["provider"] == channel_id:
                return item
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found.")

    def _source_meta(self, source_id: str) -> dict:
        for item in _SOURCES:
            if item["id"] == source_id or item["provider"] == source_id:
                return item
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")

    def _type_contract(self, meta: dict, *, kind: str) -> dict:
        definition = registry.get_definition(str(meta["provider"]))
        return {
            "id": meta["id"],
            "provider": meta["provider"],
            "name": meta["name"],
            "type": kind,
            "implemented": bool(meta["implemented"]),
            "placeholder": bool(meta["placeholder"]),
            "read_only": True,
            "write_blocked": kind == "Channel",
            "runtime_write_blocked": True,
            "settings_schema": [item.model_dump() for item in definition.settings_schema] if definition else [],
        }

    def _status(
        self,
        meta: dict,
        instance: IntegrationConnectorInstance | None,
        health: DlConnectorHealth | None,
    ) -> str:
        if meta.get("placeholder"):
            return "not_configured"
        if instance is None or not instance.enabled:
            return "not_configured"
        if health is None:
            return "configured"
        if health.status == "healthy":
            return "healthy"
        if health.status == "degraded":
            return "degraded"
        if health.status == "unhealthy":
            return "error"
        return "configured"

    def _health(self, channel_id: str) -> DlConnectorHealth | None:
        return (
            self.db.query(DlConnectorHealth)
            .filter(DlConnectorHealth.connector_id == channel_id)
            .order_by(DlConnectorHealth.checked_at.desc())
            .first()
        )

    def _instance_configured(self, instance: IntegrationConnectorInstance | None) -> bool:
        if instance is None:
            return False
        settings = {item.key: item for item in instance.settings}
        if instance.connector_type == "woocommerce":
            required = {"url", "key", "secret"}
        elif instance.connector_type in {"snappshop", "tapsishop"}:
            required = {"api_key"}
        elif instance.connector_type in {"digikala", "technolife", "shopify"}:
            required = {"api_token"}
        elif instance.connector_type == "nextcloud":
            required = {"url", "username", "password"}
        elif instance.connector_type == "csv":
            required = {"file_path"}
        elif instance.connector_type == "gsheets":
            required = {"sheet_ref"}
        elif instance.connector_type == "erp":
            required = {"api_token"}
        else:
            required = set()
        return bool(required) and all(settings.get(key) and settings[key].configured for key in required)

    def _secret_status(self, instance: IntegrationConnectorInstance | None) -> dict:
        if instance is None:
            return {}
        return {
            item.key: {
                "status": "configured" if item.configured else "not_configured",
                "replaced_at": self._iso(item.updated_at),
            }
            for item in instance.settings
            if item.secret
        }

    def _health_contract(self, health: DlConnectorHealth | None) -> dict:
        if health is None:
            return {
                "status": "unknown",
                "message": "No health check has been recorded.",
                "latency_ms": None,
                "error_code": None,
            }
        return {
            "status": health.status,
            "message": health.detail or "",
            "latency_ms": health.latency_ms,
            "error_code": health.error_class,
        }

    def _capabilities_summary(self, capabilities: ConnectorCapabilities) -> list[str]:
        labels = [
            ("read_products", "Product read"),
            ("read_categories", "Category read"),
            ("read_inventory", "Inventory read"),
            ("read_orders", "Order read"),
            ("webhook", "Webhook"),
            ("polling", "Polling"),
        ]
        enabled = [label for key, label in labels if getattr(capabilities, key)]
        return enabled or ["Planned channel unavailable in 1.0.0"]

    def _correlation_id(self) -> str:
        return f"corr_{uuid.uuid4().hex[:12]}"

    def _checked_at(self) -> str:
        return self._iso(datetime.utcnow()) or ""

    def _iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat() + "Z"
