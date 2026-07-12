"""Commerce Hub service.

Presents product-facing Sources and Channels while reusing Integration Platform
records for local settings, health, and capability metadata. Commerce Hub never
executes external marketplace writes.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from time import monotonic
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.read.woocommerce import WooCommerceProductReadAdapter
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import ping as ping_woocommerce
from app.flowhub.channels.snappshop import (
    SNAPPSHOP_BASE_URL,
    SNAPPSHOP_DEFAULT_AGENT_HEADER,
    IntegrationSettingsOrderEventCursorStore,
    SnappShopConfig,
    SnappShopConnector,
    SnappShopConnectorError,
)
from app.flowhub.channels.snappshop_product_sync import SnappShopProductSyncService
from app.flowhub.channels.tapsishop import (
    TAPSISHOP_BASE_URL,
    TapsiShopConfig,
    TapsiShopConnector,
    TapsiShopConnectorError,
)
from app.flowhub.config.values import parse_config_bool
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
        "status": "current",
        "implemented": True,
        "placeholder": False,
    },
    {
        "id": "tapsishop:main",
        "provider": "tapsishop",
        "name": "Tapsi Shop",
        "status": "current",
        "implemented": True,
        "placeholder": False,
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

    async def test_channel_connection(self, channel_id: str, body: dict | None = None) -> dict:
        meta = self._channel_meta(channel_id)
        item = self._channel_contract(meta)
        configured = item["credential_status"] == "configured" or self._has_submitted_credentials(meta, body)
        placeholder = bool(meta["placeholder"])
        if placeholder:
            return self._placeholder_connection_result()
        if str(meta["provider"]) == "woocommerce":
            return await self._test_woocommerce_channel_connection(configured)
        if str(meta["provider"]) == "snappshop":
            return await self._test_snappshop_channel_connection(configured, body)
        if str(meta["provider"]) == "tapsishop":
            return await self._test_tapsishop_channel_connection(configured, body)
        return self._unsupported_connection_result()

    async def refresh_channel_cache(self, channel_id: str, actor: str) -> dict:
        meta = self._channel_meta(channel_id)
        provider = str(meta["provider"])
        if provider == "snappshop" and not bool(meta.get("placeholder")):
            return await self._refresh_snappshop_channel_cache(channel_id, actor)
        if provider != "woocommerce" or bool(meta.get("placeholder")):
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

    async def _refresh_snappshop_channel_cache(self, channel_id: str, actor: str) -> dict:
        meta = self._channel_meta(channel_id)
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        if instance is None or not instance.enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "CHANNEL_DISABLED", "message": "SnappShop channel is disabled."},
            )
        if not self._instance_configured(instance):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "CHANNEL_NOT_CONFIGURED", "message": "Select and save a SnappShop vendor before refreshing products."},
            )
        connector = self._snappshop_connector()
        if connector is None or not connector.config.vendor_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "SnappShop configuration is incomplete.")

        result = await SnappShopProductSyncService(self.db).run(
            connector,
            actor=actor,
            max_pages=_env_int("FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_MAX_PAGES", 250, minimum=1, maximum=5_000),
            retry_attempts=_env_int("FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_RETRIES", 2, minimum=0, maximum=5),
            page_delay_seconds=_env_float(
                "FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_PAGE_DELAY_SECONDS", 1.1, minimum=0.0, maximum=10.0
            ),
            rate_limit_backoff_seconds=_env_float(
                "FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_RATE_LIMIT_BACKOFF_SECONDS", 30.0, minimum=1.0, maximum=60.0
            ),
        )
        payload = {
            **result.as_dict(),
            "products_read": result.products_received,
            "variable_products_read": 0,
            "variations_read": 0,
            "cache_rows_upserted": result.products_stored,
            "warnings": [],
            "errors": list(result.failures),
        }
        if result.failures:
            latest = self._latest_product_refresh(channel_id)
            category = str((latest.meta or {}).get("error_category") or "unexpected_response") if latest else "unexpected_response"
            ConnectorHealthService(self.db).upsert(
                channel_id,
                "snappshop",
                "unhealthy",
                detail="SnappShop product synchronization failed.",
                error_class=category,
            )
        else:
            ConnectorHealthService(self.db).upsert(
                channel_id,
                "snappshop",
                "healthy",
                detail="SnappShop vendor and product reads completed successfully.",
            )
        return payload

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

    async def update_channel_settings(self, channel_id: str, body: dict, *, actor: str = "system") -> dict:
        meta = self._channel_meta(channel_id)
        provider = str(meta["provider"])
        if registry.get_definition(provider) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel settings are not available.")
        if bool(meta.get("placeholder")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel settings are not available.")
        access_mode = self._requested_channel_access_mode(meta, body)
        self._validate_channel_configuration(meta, body)
        if provider == "snappshop":
            await self._validate_snappshop_vendor_selection(body)
        if provider in {"snappshop", "tapsishop"}:
            return self._update_marketplace_channel_settings(
                channel_id,
                meta,
                body,
                actor=actor,
                access_mode=access_mode,
            )
        self._ensure_instance(meta)
        if provider == "woocommerce":
            self._persist_woocommerce_app_config(body)
        result = self.integration.update_settings_contract(channel_id, self._settings_body(body))
        self._update_instance_state(meta, body, access_mode=access_mode)
        self.integration.record_event(
            connector_id=channel_id,
            event_name="channel_configuration_changed",
            message="Channel configuration was updated; credential values remain write-only.",
            metadata={"actor": actor, "secret_values_returned": False},
        )
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

    def _update_marketplace_channel_settings(
        self,
        channel_id: str,
        meta: dict,
        body: dict,
        *,
        actor: str,
        access_mode: str,
    ) -> dict:
        provider = str(meta["provider"])
        changed_fields = self._configuration_changed_fields(body)
        try:
            self._ensure_instance(meta, commit=False)
            if provider == "snappshop":
                self._persist_snappshop_app_config(body, commit=False)
            else:
                self._persist_tapsishop_app_config(body, commit=False)
            self.integration.stage_settings_contract(channel_id, self._settings_body(body))
            self._update_instance_state(meta, body, access_mode=access_mode, commit=False)
            self.integration.record_event(
                connector_id=channel_id,
                event_name="channel_configuration_changed",
                message="Channel configuration was updated; credential values remain write-only.",
                metadata={
                    "actor": actor,
                    "channel_id": channel_id,
                    "changed_fields": changed_fields,
                    "secret_values_returned": False,
                },
                commit=False,
            )
            self.db.flush()
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        result = self.integration.get_settings_contract(channel_id)
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

    def _configuration_changed_fields(self, body: dict) -> list[str]:
        changed = set((body.get("settings") or {}).keys()) if isinstance(body.get("settings"), dict) else set()
        changed.update(
            key
            for key in ("display_name", "enabled", "access_mode", "description")
            if key in body
        )
        return sorted(str(key) for key in changed)

    def get_channel_configuration(self, channel_id: str) -> dict:
        meta = self._channel_meta(channel_id)
        if bool(meta.get("placeholder")) or registry.get_definition(str(meta["provider"])) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel settings are not available.")
        if meta["provider"] == "woocommerce":
            self.integration.bootstrap_from_app_config()
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        definition = registry.get_definition(str(meta["provider"]))
        settings: dict[str, object] = {
            item.key: item.default
            for item in definition.settings_schema
            if not item.secret and item.default is not None
        } if definition else {}
        secret_status: dict[str, dict[str, str | None]] = {}
        if instance is not None:
            for item in instance.settings:
                if item.secret:
                    secret_status[item.key] = {
                        "status": "configured" if item.configured else "not_configured",
                        "replaced_at": self._iso(item.updated_at),
                    }
                else:
                    settings[item.key] = self._configuration_setting_value(
                        str(meta["provider"]), item.key, item.value_json
                    )
        return {
            "channel_id": channel_id,
            "provider": meta["provider"],
            "display_name": instance.name if instance else meta["name"],
            "configured": self._instance_configured(instance),
            "enabled": bool(instance and instance.enabled),
            "access_mode": self._access_mode(instance),
            "settings": settings,
            "secrets": secret_status,
            "token_configured": secret_status.get("token", {}).get("status") == "configured",
            "webhook_token_configured": secret_status.get("webhook_token", {}).get("status") == "configured",
            "settings_schema": [item.model_dump() for item in definition.settings_schema] if definition else [],
            "webhook_path": f"/api/v2/webhooks/tapsishop/{channel_id}" if meta["provider"] == "tapsishop" else None,
            "credentials_returned": False,
        }

    def _configuration_setting_value(self, provider: str, key: str, value: object) -> object:
        if provider == "tapsishop" and key in {"token_refresh_enabled", "revoke_current_token"}:
            return parse_config_bool(value)
        if provider == "snappshop":
            if key == "request_timeout":
                return _safe_integer_timeout(value)
            if key == "agent_header_name":
                return str(value or SNAPPSHOP_DEFAULT_AGENT_HEADER)
        return value

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
        secret_status = self._secret_status(instance)
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
            body["secrets"] = secret_status
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
        secret_status = self._secret_status(instance)
        access_mode = self._access_mode(instance)
        write_pipeline_eligible = self._write_pipeline_eligible(meta, instance)
        capabilities = definition.connector.capabilities if definition else ConnectorCapabilities()
        cache_rows = (
            self.db.query(DlProductCache)
            .filter(DlProductCache.connector_id == str(meta["id"]), DlProductCache.exists.is_(True))
            .all()
        )
        cached_variations = sum(1 for row in cache_rows if (row.product_type or "").lower() == "variation")
        latest_refresh = self._latest_product_refresh(str(meta["id"]))
        configuration_state = self._channel_configuration_state(instance, health, latest_refresh)
        body = {
            "id": meta["id"],
            "provider": provider,
            "name": meta["name"],
            "type": "Channel",
            "status": self._status(meta, instance, health),
            "implemented": meta["implemented"],
            "placeholder": meta["placeholder"],
            "enabled": bool(instance and instance.enabled),
            "access_mode": access_mode,
            "read_only": access_mode == ACCESS_MODE_READ_ONLY,
            "write_blocked": not write_pipeline_eligible,
            "write_pipeline_eligible": write_pipeline_eligible,
            "runtime_write_blocked": True,
            "credential_status": "configured" if configured else "not_configured",
            "configuration_state": configuration_state,
            "credentials_configured": self._credentials_configured(instance),
            "credentials_verified": bool(health and health.last_success_at),
            "vendor_selected": self._vendor_selected(instance),
            "vendor_accessible": bool(configured and health and health.status == "healthy"),
            "token_configured": secret_status.get("token", {}).get("status") == "configured",
            "webhook_token_configured": secret_status.get("webhook_token", {}).get("status") == "configured",
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
            "product_sync_error_category": (
                str((latest_refresh.meta or {}).get("error_category") or "") or None
                if latest_refresh and latest_refresh.status == "failed"
                else None
            ),
        }
        if detail:
            body["settings_schema"] = [
                item.model_dump() for item in definition.settings_schema
            ] if definition else []
            body["secrets"] = secret_status
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

    def _latest_product_refresh(self, channel_id: str) -> DlRefreshJob | None:
        return (
            self.db.query(DlRefreshJob)
            .filter(DlRefreshJob.connector_id == channel_id, DlRefreshJob.entity_type == "products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )

    def _credentials_configured(self, instance: IntegrationConnectorInstance | None) -> bool:
        if instance is None:
            return False
        settings = {item.key: item for item in instance.settings}
        required = {
            "woocommerce": {"url", "key", "secret"},
            "snappshop": {"token", "agent_identifier"},
            "tapsishop": {"token"},
        }.get(instance.connector_type, set())
        return bool(required) and all(settings.get(key) and settings[key].configured for key in required)

    def _vendor_selected(self, instance: IntegrationConnectorInstance | None) -> bool:
        if instance is None or instance.connector_type != "snappshop":
            return False
        row = next((item for item in instance.settings if item.key == "vendor_id"), None)
        return bool(row and row.configured and str(row.value_json or "").strip())

    def _channel_configuration_state(
        self,
        instance: IntegrationConnectorInstance | None,
        health: DlConnectorHealth | None,
        refresh: DlRefreshJob | None,
    ) -> str:
        if instance is None or not self._credentials_configured(instance):
            return "not_configured"
        if health and health.status == "unhealthy":
            return "error"
        if instance.connector_type == "snappshop" and not self._instance_configured(instance):
            return "credentials_verified" if health and health.last_success_at else "not_configured"
        if refresh and refresh.status == "failed":
            return "error"
        if refresh and refresh.status == "completed":
            return "operational"
        return "configured"

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

    def _ensure_instance(self, meta: dict, *, commit: bool = True) -> IntegrationConnectorInstance:
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
        if commit:
            self.db.commit()
            self.db.refresh(row)
        else:
            self.db.flush()
        return row

    def _update_instance_state(
        self,
        meta: dict,
        body: dict,
        *,
        access_mode: str,
        commit: bool = True,
    ) -> None:
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
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def _settings_body(self, body: dict) -> dict:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        access_mode = body.get("access_mode", body.get("accessMode")) if isinstance(body, dict) else None
        if access_mode not in (None, ""):
            settings["access_mode"] = access_mode
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

    def _has_submitted_credentials(self, meta: dict, body: dict | None) -> bool:
        if not isinstance(body, dict):
            return False
        settings = body.get("settings") if isinstance(body.get("settings"), dict) else {}
        secrets = body.get("secrets") if isinstance(body.get("secrets"), dict) else {}
        provider = str(meta["provider"])
        if provider == "snappshop":
            return bool(str(settings.get("agent_identifier") or self.integration.config.get("snappshop.agent_identifier") or "").strip()) and bool(
                str(secrets.get("token") or self.integration.config.get("snappshop.token") or "").strip()
            )
        if provider == "tapsishop":
            return bool(str(secrets.get("token") or self.integration.config.get("tapsishop.token") or "").strip())
        return False

    def _validate_channel_configuration(self, meta: dict, body: dict) -> None:
        provider = str(meta["provider"])
        if provider not in {"snappshop", "tapsishop"}:
            return
        settings, secrets = self._connector_values(provider, body)
        base_url = str(settings.get("base_url") or "").strip()
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A valid channel Base URL is required.")
        timeout = settings.get("request_timeout") or 30
        if isinstance(timeout, bool):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Request timeout must be a whole number of seconds.")
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Request timeout must be a whole number of seconds.") from exc
        if not timeout_value.is_integer() or timeout_value < 1 or timeout_value > 120:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Request timeout must be an integer between 1 and 120 seconds.")
        try:
            if provider == "snappshop":
                SnappShopConfig.from_values(settings=settings, secrets=secrets)
            else:
                TapsiShopConfig.from_values(settings=settings, secrets=secrets)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    def _connector_values(self, provider: str, body: dict | None) -> tuple[dict, dict]:
        submitted_settings = body.get("settings") if isinstance(body, dict) and isinstance(body.get("settings"), dict) else {}
        submitted_secrets = body.get("secrets") if isinstance(body, dict) and isinstance(body.get("secrets"), dict) else {}
        setting_keys = {
            "snappshop": ("base_url", "agent_identifier", "agent_header_name", "request_timeout", "vendor_id"),
            "tapsishop": (
                "base_url", "request_timeout", "selected_vendor_id", "token_refresh_enabled",
                "token_refresh_name", "revoke_current_token", "token_refresh_expired_at",
            ),
        }.get(provider, ())
        secret_keys = {"snappshop": ("token",), "tapsishop": ("token", "webhook_token")}.get(provider, ())
        defaults = {
            "snappshop": {"base_url": SNAPPSHOP_BASE_URL, "agent_header_name": "User-Agent", "request_timeout": 30},
            "tapsishop": {"base_url": TAPSISHOP_BASE_URL, "request_timeout": 30},
        }.get(provider, {})
        settings = {
            key: submitted_settings[key]
            if key in submitted_settings
            else self.integration.config.get(f"{provider}.{key}") or defaults.get(key)
            for key in setting_keys
        }
        if provider == "snappshop":
            settings["base_url"] = str(settings.get("base_url") or SNAPPSHOP_BASE_URL).strip().rstrip("/")
            settings["agent_header_name"] = str(
                settings.get("agent_header_name") or SNAPPSHOP_DEFAULT_AGENT_HEADER
            ).strip()
            if "request_timeout" not in submitted_settings:
                settings["request_timeout"] = _safe_integer_timeout(settings.get("request_timeout"))
        secrets = {
            key: submitted_secrets.get(key) or self.integration.config.get(f"{provider}.{key}")
            for key in secret_keys
        }
        return settings, secrets

    def _vendor_contract(self, vendor) -> dict:
        return {
            "id": vendor.vendor_id,
            "name": vendor.name,
            "title": vendor.metadata.get("title"),
            "title_en": vendor.metadata.get("title_en"),
            "status": vendor.metadata.get("status"),
            "store_url": vendor.display_url,
            "reference_code": vendor.identifiers.channel_reference_code,
        }

    async def _validate_snappshop_vendor_selection(self, body: dict) -> None:
        settings, _ = self._connector_values("snappshop", body)
        selected_vendor_id = str(settings.get("vendor_id") or "").strip()
        if not selected_vendor_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "SNAPPSHOP_VENDOR_REQUIRED", "message": "Select a SnappShop vendor after testing the connection."},
            )
        connector = self._snappshop_connector(body)
        if connector is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "SnappShop credentials are incomplete.")
        try:
            vendors = await connector.list_vendors()
        except SnappShopConnectorError as exc:
            error = exc.error
            if error.category.value in {"authentication", "authorization", "validation"}:
                response_status = status.HTTP_422_UNPROCESSABLE_ENTITY
            elif error.category.value == "timeout":
                response_status = status.HTTP_504_GATEWAY_TIMEOUT
            else:
                response_status = status.HTTP_502_BAD_GATEWAY
            raise HTTPException(
                response_status,
                {
                    "code": f"SNAPPSHOP_{error.category.value.upper()}",
                    "message": error.message,
                    "upstream_status": error.http_status,
                },
            ) from exc
        selected = next((vendor for vendor in vendors if vendor.vendor_id == selected_vendor_id), None)
        if selected is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "SNAPPSHOP_VENDOR_INVALID", "message": "The selected SnappShop vendor is not available for these credentials."},
            )
        if not _snappshop_vendor_is_active(selected.metadata.get("status")):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "SNAPPSHOP_VENDOR_INACTIVE", "message": "The selected SnappShop vendor is inactive."},
            )

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

    async def _test_snappshop_channel_connection(self, configured: bool, body: dict | None = None) -> dict:
        connector = self._snappshop_connector(body)
        if not configured or connector is None:
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status": "not_configured",
                "http_status": None,
                "latency_ms": None,
                "checked_at": self._checked_at(),
                "message": "SnappShop is not configured. No external call was performed.",
                "external_call_performed": False,
            }
        started = monotonic()
        try:
            vendors = await connector.list_vendors()
            if not vendors:
                raise ValueError("No authorized SnappShop vendors were returned.")
            if connector.config.vendor_id:
                selected = next((vendor for vendor in vendors if vendor.vendor_id == connector.config.vendor_id), None)
                if selected is None:
                    raise ValueError("Selected SnappShop vendor was not returned.")
            latency_ms = round((monotonic() - started) * 1000, 2)
        except SnappShopConnectorError as exc:
            error = exc.error
            return {
                **self._connection_base(), "ok": False, "connected": False,
                "authenticated": error.category.value not in {"authentication", "authorization"},
                "status": "authentication_failed" if error.category.value == "authentication" else "error",
                "http_status": error.http_status, "latency_ms": round((monotonic() - started) * 1000, 2),
                "checked_at": self._checked_at(), "message": error.message, "external_call_performed": True,
            }
        except ValueError as exc:
            return {
                **self._connection_base(), "ok": False, "connected": False, "authenticated": True,
                "status": "error", "http_status": None, "latency_ms": round((monotonic() - started) * 1000, 2),
                "checked_at": self._checked_at(), "message": str(exc), "external_call_performed": True,
            }
        return {
            **self._connection_base(),
            "ok": True,
            "connected": True,
            "authenticated": True,
            "status": "configured" if connector.config.vendor_id else "credentials_verified",
            "http_status": 200,
            "latency_ms": latency_ms,
            "checked_at": self._checked_at(),
            "message": "SnappShop credentials were verified successfully.",
            "external_call_performed": True,
            "vendors": [self._vendor_contract(item) for item in vendors],
            "suggested_vendor_id": _single_active_vendor_id(vendors),
            "selected_vendor_id": connector.config.vendor_id,
        }

    def _snappshop_connector(self, body: dict | None = None) -> SnappShopConnector | None:
        settings, secrets = self._connector_values("snappshop", body)
        try:
            config = SnappShopConfig.from_values(
                settings=settings,
                secrets=secrets,
            )
        except (TypeError, ValueError):
            return None
        return SnappShopConnector(
            channel_id="snappshop:main",
            config=config,
            cursor_store=IntegrationSettingsOrderEventCursorStore(self.db),
        )

    async def _test_tapsishop_channel_connection(self, configured: bool, body: dict | None = None) -> dict:
        connector = self._tapsishop_connector(body)
        if not configured or connector is None:
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status": "not_configured",
                "http_status": None,
                "latency_ms": None,
                "checked_at": self._checked_at(),
                "message": "TapsiShop is not configured. No external call was performed.",
                "external_call_performed": False,
            }
        started = monotonic()
        try:
            vendor = await connector.get_vendor_information()
            if connector.config.selected_vendor_id and vendor.vendor_id != connector.config.selected_vendor_id:
                raise ValueError("Selected TapsiShop vendor does not match vendor-information.")
            latency_ms = round((monotonic() - started) * 1000, 2)
        except TapsiShopConnectorError as exc:
            error = exc.error
            return {
                **self._connection_base(), "ok": False, "connected": False,
                "authenticated": error.category.value not in {"authentication", "authorization"},
                "status": "authentication_failed" if error.category.value == "authentication" else "error",
                "http_status": error.http_status, "latency_ms": round((monotonic() - started) * 1000, 2),
                "checked_at": self._checked_at(), "message": error.message, "external_call_performed": True,
            }
        except ValueError as exc:
            return {
                **self._connection_base(), "ok": False, "connected": False, "authenticated": True,
                "status": "error", "http_status": None, "latency_ms": round((monotonic() - started) * 1000, 2),
                "checked_at": self._checked_at(), "message": str(exc), "external_call_performed": True,
            }
        return {
            **self._connection_base(),
            "ok": True,
            "connected": True,
            "authenticated": True,
            "status": "connected",
            "http_status": 200,
            "latency_ms": latency_ms,
            "checked_at": self._checked_at(),
            "message": "Connected to TapsiShop. Vendor information probe succeeded.",
            "external_call_performed": True,
            "vendor_information": self._vendor_contract(vendor),
        }

    def _tapsishop_connector(self, body: dict | None = None) -> TapsiShopConnector | None:
        settings, secrets = self._connector_values("tapsishop", body)
        try:
            config = TapsiShopConfig.from_values(
                settings=settings,
                secrets=secrets,
            )
        except (TypeError, ValueError):
            return None

        def update_token(new_token: str) -> None:
            self.integration.config.set("tapsishop.token", new_token, updated_by="tapsishop_refresh")

        return TapsiShopConnector(
            channel_id="tapsishop:main",
            config=config,
            token_updater=update_token,
        )

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

    def _persist_snappshop_app_config(self, body: dict, *, commit: bool = True) -> None:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        pairs: dict[str, str] = {}
        pairs["snappshop.base_url"] = str(
            settings.get("base_url") or "https://apix.snappshop.ir/automation/v1"
        ).strip().rstrip("/")
        pairs["snappshop.agent_header_name"] = str(
            settings.get("agent_header_name") or SNAPPSHOP_DEFAULT_AGENT_HEADER
        ).strip()
        if settings.get("agent_identifier"):
            pairs["snappshop.agent_identifier"] = str(settings["agent_identifier"]).strip()
        pairs["snappshop.request_timeout"] = str(_safe_integer_timeout(settings.get("request_timeout")))
        if "vendor_id" in settings:
            pairs["snappshop.vendor_id"] = str(settings.get("vendor_id") or "").strip()
        if secrets.get("token"):
            pairs["snappshop.token"] = str(secrets["token"])
        if pairs:
            self.integration.config.set_many(pairs, updated_by="commerce_hub", commit=commit)

    def _persist_tapsishop_app_config(self, body: dict, *, commit: bool = True) -> None:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        pairs: dict[str, str] = {
            "tapsishop.base_url": str(settings.get("base_url") or TAPSISHOP_BASE_URL).strip().rstrip("/"),
        }
        for source_key, config_key in (
            ("request_timeout", "tapsishop.request_timeout"),
            ("token_refresh_enabled", "tapsishop.token_refresh_enabled"),
            ("token_refresh_name", "tapsishop.token_refresh_name"),
            ("revoke_current_token", "tapsishop.revoke_current_token"),
            ("token_refresh_expired_at", "tapsishop.token_refresh_expired_at"),
            ("selected_vendor_id", "tapsishop.selected_vendor_id"),
        ):
            if source_key in settings:
                if source_key in {"token_refresh_enabled", "revoke_current_token"}:
                    pairs[config_key] = "true" if parse_config_bool(settings.get(source_key)) else "false"
                else:
                    pairs[config_key] = str(settings.get(source_key) or "").strip()
        if secrets.get("token"):
            pairs["tapsishop.token"] = str(secrets["token"])
        if secrets.get("webhook_token"):
            pairs["tapsishop.webhook_token"] = str(secrets["webhook_token"])
        if pairs:
            self.integration.config.set_many(pairs, updated_by="commerce_hub", commit=commit)

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
        elif instance.connector_type == "snappshop":
            required = {"token", "agent_identifier", "vendor_id"}
        elif instance.connector_type == "tapsishop":
            required = {"token"}
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


def _safe_integer_timeout(value: object, default: int = 30) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default
    if not parsed.is_integer() or parsed < 1 or parsed > 120:
        return default
    return int(parsed)


def _snappshop_vendor_is_active(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().upper() in {"ACTIVE", "ENABLED", "TRUE", "1"}


def _single_active_vendor_id(vendors: list) -> str | None:
    active = [vendor for vendor in vendors if vendor.vendor_id and _snappshop_vendor_is_active(vendor.metadata.get("status"))]
    return active[0].vendor_id if len(active) == 1 else None


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if minimum <= value <= maximum else default
