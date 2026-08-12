"""Commerce Hub service.

Presents product-facing Sources and Channels while reusing Integration Platform
records for local settings, health, and capability metadata. Commerce Hub never
executes external marketplace writes.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from time import monotonic
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import ping as ping_woocommerce
from app.connectors.read.woocommerce import WooCommerceProductReadAdapter
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.channels.digikala import (
    DIGIKALA_BASE_URL,
    DigikalaConfig,
    DigikalaConnector,
)
from app.flowhub.channels.marketplace_product_sync import MarketplaceProductSyncService
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
from app.flowhub.channels.technolife import (
    TECHNOLIFE_BASE_URL,
    TechnolifeConfig,
    TechnolifeConnector,
)
from app.flowhub.config.nextcloud_url import NextcloudUrlValidationError, normalize_nextcloud_url
from app.connectors.common.source_http import (
    SourceHttpClient,
    SourceHttpError,
    parse_trusted_private_networks,
)
from app.flowhub.config.values import parse_config_bool
from app.flowhub.data_layer.health_service import ConnectorHealthService
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache, DlRefreshJob
from app.flowhub.integration_platform.contracts import ConnectorCapabilities
from app.flowhub.integration_platform.models import (
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.integration_platform.registry import registry
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.nextcloud import NextcloudClient
from app.flowhub.pricing_matrix.service import PricingMatrixService
from app.flowhub.read_engine.manual import ManualReadService
from app.flowhub.read_engine.service import IncrementalReadEngine
from app.flowhub.security.upstream_errors import UpstreamServiceError, normalize_upstream_error
from app.flowhub.source_acquisition.nextcloud_provider import NextcloudWebDavAcquisitionProvider
from app.flowhub.source_workspace.models import SourceMappingRevision, SourceProfile
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
        "name": "SnappShop",
        "status": "current",
        "implemented": True,
        "placeholder": False,
    },
    {
        "id": "tapsishop:main",
        "provider": "tapsishop",
        "name": "TapsiShop",
        "status": "current",
        "implemented": True,
        "placeholder": False,
    },
    {
        "id": "digikala:main",
        "provider": "digikala",
        "name": "Digikala",
        "status": "current",
        "implemented": True,
        "placeholder": False,
        "implementation_status": "IMPLEMENTED_UNVERIFIED",
    },
    {
        "id": "technolife:main",
        "provider": "technolife",
        "name": "Technolife",
        "status": "current",
        "implemented": True,
        "placeholder": False,
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

# These exact values shipped as system defaults before channel names became
# locale-aware. They are not Owner custom names and must render as the current
# locale's canonical brand label. Any other persisted value remains custom.
_CHANNEL_SYSTEM_NAME_ALIASES = {
    "woocommerce": frozenset({"woocommerce", "ووکامرس"}),
    "snappshop": frozenset({"snappshop", "snapp shop", "اسنپ شاپ"}),
    "tapsishop": frozenset({"tapsishop", "tapsi shop", "تپ‌سی شاپ"}),
    "digikala": frozenset({"digikala", "دیجی‌کالا"}),
    "technolife": frozenset({"technolife", "تکنولایف"}),
    "shopify": frozenset({"shopify", "شاپیفای"}),
}
_CHANNEL_DISPLAY_NAME_CUSTOM_KEY = "_flowhub_display_name_custom"
_CHANNEL_IDS = frozenset(str(item["id"]) for item in _CHANNELS)

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
        "name": "Excel / CSV",
        "type": "Source",
        # This is a local, managed-sheet import rather than an external
        # connector.  Its setup is /sources/import, not Commerce Hub.
        "status": "current",
        "implemented": True,
        "placeholder": False,
        "credential_status": "not_required",
        "last_health_check": None,
        "data_role": "File import input",
        "action_label": "Manage",
        "action_href": "/sources/import",
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
        record_health = self._channel_test_matches_stored_configuration(meta, body)
        placeholder = bool(meta["placeholder"])
        if placeholder:
            return self._placeholder_connection_result()
        if str(meta["provider"]) == "woocommerce":
            result = await self._test_woocommerce_channel_connection(configured, body)
        elif str(meta["provider"]) == "snappshop":
            result = await self._test_snappshop_channel_connection(configured, body)
        elif str(meta["provider"]) == "tapsishop":
            result = await self._test_tapsishop_channel_connection(configured, body)
        elif str(meta["provider"]) == "technolife":
            result = await self._test_technolife_channel_connection(configured, body)
        elif str(meta["provider"]) == "digikala":
            result = await self._test_digikala_channel_connection(configured, body)
        else:
            return self._unsupported_connection_result()
        if record_health:
            self._record_channel_test_health(meta, result)
        return result

    async def refresh_channel_cache(
        self,
        channel_id: str,
        actor: str,
        *,
        before_cache_write: Callable[[str, str], None] | None = None,
    ) -> dict:
        meta = self._channel_meta(channel_id)
        provider = str(meta["provider"])
        if provider == "snappshop" and not bool(meta.get("placeholder")):
            return await self._refresh_snappshop_channel_cache(channel_id, actor)
        if provider in {"tapsishop", "technolife"} and not bool(meta.get("placeholder")):
            return await self._refresh_marketplace_channel_cache(channel_id, actor)
        if provider != "woocommerce" or bool(meta.get("placeholder")):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product cache refresh is not available for this channel.")
        instance = self.db.get(IntegrationConnectorInstance, meta["id"])
        if instance is None or not instance.enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "CHANNEL_DISABLED", "message": "WooCommerce channel is disabled."},
            )

        started = datetime.now(timezone.utc).replace(tzinfo=None)
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
                before_cache_write=before_cache_write,
            )
            warnings = list(adapter.warnings)
            result_status = "completed_with_warnings" if warnings else "completed"
            completed = datetime.now(timezone.utc).replace(tzinfo=None)
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
            completed = datetime.now(timezone.utc).replace(tzinfo=None)
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

    async def _refresh_marketplace_channel_cache(self, channel_id: str, actor: str) -> dict:
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        if instance is None or not instance.enabled:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "CHANNEL_DISABLED", "message": "Marketplace channel is disabled."},
            )
        if not self._instance_configured(instance):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "CHANNEL_NOT_CONFIGURED",
                    "message": "Marketplace credentials must be saved before refreshing products.",
                },
            )
        connector = (
            self._tapsishop_connector()
            if instance.connector_type == "tapsishop"
            else self._technolife_connector()
        )
        if connector is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Marketplace configuration is incomplete.")

        result = await MarketplaceProductSyncService(self.db).run(
            connector,
            actor=actor,
            page_size=_env_int(
                f"FLOWHUB_{connector.connector_type.upper()}_PRODUCT_SYNC_PAGE_SIZE",
                20 if connector.connector_type == "technolife" else 10,
                minimum=1,
                maximum=100 if connector.connector_type == "technolife" else 500,
            ),
            max_pages=_env_int(
                f"FLOWHUB_{connector.connector_type.upper()}_PRODUCT_SYNC_MAX_PAGES",
                250,
                minimum=1,
                maximum=5_000,
            ),
            retry_attempts=_env_int(
                f"FLOWHUB_{connector.connector_type.upper()}_PRODUCT_SYNC_RETRIES",
                2,
                minimum=0,
                maximum=5,
            ),
            page_delay_seconds=_env_float(
                f"FLOWHUB_{connector.connector_type.upper()}_PRODUCT_SYNC_PAGE_DELAY_SECONDS",
                1.0,
                minimum=0.0,
                maximum=10.0,
            ),
            rate_limit_backoff_seconds=_env_float(
                f"FLOWHUB_{connector.connector_type.upper()}_PRODUCT_SYNC_RATE_LIMIT_BACKOFF_SECONDS",
                30.0,
                minimum=1.0,
                maximum=60.0,
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
            category = (
                str((latest.meta or {}).get("error_category") or "unexpected_response")
                if latest
                else "unexpected_response"
            )
            ConnectorHealthService(self.db).upsert(
                channel_id,
                connector.connector_type,
                "unhealthy",
                detail="Marketplace product synchronization failed.",
                error_class=category,
            )
        else:
            ConnectorHealthService(self.db).upsert(
                channel_id,
                connector.connector_type,
                "healthy",
                detail="Marketplace product reads completed successfully.",
            )
        return payload

    async def test_source_connection(self, source_id: str, body: dict | None = None) -> dict:
        meta = self._source_meta(source_id)
        item = self._source_contract(meta)
        configured = item["credential_status"] == "configured"
        placeholder = bool(meta["placeholder"])
        if placeholder:
            message = f"{meta['name']} is a read-only planned source. No external call was performed."
        elif str(meta["provider"]) == "nextcloud":
            return await self._test_nextcloud_source_connection(body)
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
            trusted_private_networks=parse_trusted_private_networks(
                self.integration.config.get("nextcloud.trusted_private_networks")
            ),
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
            source_profile_id=(
                self.db.query(SourceProfile)
                .filter(SourceProfile.external_source_id == source_id)
                .with_entities(SourceProfile.id)
                .scalar()
            ),
        )
        return reader.manual_read_response(result)

    def update_source_settings(
        self, source_id: str, body: dict, *, user: FlowHubUser | None = None
    ) -> dict:
        meta = self._source_meta(source_id)
        provider = str(meta["provider"])
        if registry.get_definition(provider) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source settings are not available.")
        previous_nextcloud_identity = (
            self._nextcloud_configuration_identity({}, allow_stored=True)
            if provider == "nextcloud"
            else None
        )
        if provider == "nextcloud":
            self._validate_nextcloud_source_body(body)
        self._ensure_instance(meta)
        self._update_instance_state(meta, body, access_mode=ACCESS_MODE_READ_ONLY)
        if provider == "nextcloud":
            self._persist_nextcloud_app_config(body)
        result = self.integration.update_settings_contract(source_id, self._settings_body(body))
        currency_profile = self._save_currency_declaration(
            scope="source", scope_reference=source_id, body=body, user=user
        )
        if provider == "nextcloud" and previous_nextcloud_identity != (
            self._nextcloud_configuration_identity({}, allow_stored=True)
        ):
            self._clear_source_health(source_id)
        instance = self.db.get(IntegrationConnectorInstance, source_id)
        connection_configured = (
            self._nextcloud_connection_configured(instance)
            if provider == "nextcloud"
            else self._instance_configured(instance)
        )
        setup_configured = self._source_setup_configured(source_id, provider, instance)
        return {
            **result,
            "source_id": source_id,
            "configured": setup_configured,
            "connection_configured": connection_configured,
            "configuration_state": self._source_configuration_state(
                meta,
                connection_configured=connection_configured,
                configured=setup_configured,
            ),
            "access_mode": ACCESS_MODE_READ_ONLY,
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
            "write_pipeline_eligible": False,
            "credentials_returned": False,
            "currency_profile": currency_profile,
        }

    async def update_channel_settings(
        self,
        channel_id: str,
        body: dict,
        *,
        actor: str = "system",
        user: FlowHubUser | None = None,
    ) -> dict:
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
        if provider in {"snappshop", "tapsishop", "technolife", "digikala"}:
            result = self._update_marketplace_channel_settings(
                channel_id,
                meta,
                body,
                actor=actor,
                access_mode=access_mode,
            )
            return {
                **result,
                "currency_profile": self._save_currency_declaration(
                    scope="channel", scope_reference=channel_id, body=body, user=user
                ),
            }
        self._ensure_instance(meta)
        if provider == "woocommerce":
            self._persist_woocommerce_app_config(body)
        result = self._public_channel_settings_result(
            self.integration.update_settings_contract(channel_id, self._settings_body(body))
        )
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
        currency_profile = self._save_currency_declaration(
            scope="channel", scope_reference=channel_id, body=body, user=user
        )
        return {
            **result,
            "channel_id": channel_id,
            "access_mode": effective_access_mode,
            "read_only": effective_access_mode == ACCESS_MODE_READ_ONLY,
            "runtime_write_blocked": True,
            "write_blocked": not write_pipeline_eligible,
            "write_pipeline_eligible": write_pipeline_eligible,
            "currency_profile": currency_profile,
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
            elif provider == "tapsishop":
                self._persist_tapsishop_app_config(body, commit=False)
            elif provider == "technolife":
                self._persist_technolife_app_config(body, commit=False)
            else:
                self._persist_digikala_app_config(body, commit=False)
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

        result = self._public_channel_settings_result(
            self.integration.get_settings_contract(channel_id)
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

    @staticmethod
    def _public_channel_settings_result(result: dict) -> dict:
        settings = dict(result.get("settings") or {})
        settings.pop(_CHANNEL_DISPLAY_NAME_CUSTOM_KEY, None)
        return {**result, "settings": settings}

    def _configuration_changed_fields(self, body: dict) -> list[str]:
        changed = set((body.get("settings") or {}).keys()) if isinstance(body.get("settings"), dict) else set()
        changed.update(
            key
            for key in ("display_name", "enabled", "access_mode", "description")
            if key in body
        )
        return sorted(str(key) for key in changed)

    def get_source_configuration(self, source_id: str) -> dict:
        meta = self._source_meta(source_id)
        definition = registry.get_definition(str(meta["provider"]))
        if bool(meta.get("placeholder")) or definition is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source settings are not available.")
        if meta["provider"] == "nextcloud":
            self.integration.bootstrap_from_app_config()
        instance = self.db.get(IntegrationConnectorInstance, source_id)
        health = self._health(source_id)
        settings: dict[str, object] = {
            item.key: item.default
            for item in definition.settings_schema
            if not item.secret and item.default is not None
        }
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
        connection_configured = (
            self._nextcloud_connection_configured(instance)
            if meta["provider"] == "nextcloud"
            else self._instance_configured(instance)
        )
        setup_configured = self._source_setup_configured(
            source_id, str(meta["provider"]), instance
        )
        return {
            "source_id": source_id,
            "provider": meta["provider"],
            "display_name": instance.name if instance else meta["name"],
            "configured": setup_configured,
            "connection_configured": connection_configured,
            "configuration_state": self._source_configuration_state(
                meta,
                connection_configured=connection_configured,
                configured=setup_configured,
            ),
            "enabled": bool(instance and instance.enabled),
            "access_mode": ACCESS_MODE_READ_ONLY,
            "settings": settings,
            "secrets": secret_status,
            "settings_schema": [item.model_dump() for item in definition.settings_schema],
            "credentials_returned": False,
            "last_test": {
                **self._health_contract(health),
                "checked_at": self._iso(health.checked_at) if health else None,
            },
            "currency_profile": PricingMatrixService(self.db).unit_declaration(
                "source", source_id
            ),
        }

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
                elif item.key != _CHANNEL_DISPLAY_NAME_CUSTOM_KEY:
                    settings[item.key] = self._configuration_setting_value(
                        str(meta["provider"]), item.key, item.value_json
                    )
        display_name, display_name_custom = self._channel_display_name(meta, instance)
        return {
            "channel_id": channel_id,
            "provider": meta["provider"],
            "display_name": display_name,
            "display_name_custom": display_name_custom,
            "configured": self._instance_configured(instance),
            "enabled": bool(instance and instance.enabled),
            "access_mode": self._access_mode(instance),
            "settings": settings,
            "secrets": secret_status,
            "token_configured": secret_status.get("token", {}).get("status") == "configured",
            "webhook_token_configured": secret_status.get("webhook_token", {}).get("status") == "configured",
            "access_token_configured": secret_status.get("access_token", {}).get("status") == "configured",
            "refresh_token_configured": secret_status.get("refresh_token", {}).get("status") == "configured",
            "settings_schema": [item.model_dump() for item in definition.settings_schema] if definition else [],
            "webhook_path": f"/api/v2/webhooks/tapsishop/{channel_id}" if meta["provider"] == "tapsishop" else None,
            "credentials_returned": False,
            "currency_profile": PricingMatrixService(self.db).unit_declaration(
                "channel", channel_id
            ),
        }

    def _save_currency_declaration(
        self,
        *,
        scope: str,
        scope_reference: str,
        body: dict,
        user: FlowHubUser | None,
    ) -> dict:
        currency = str(body.get("currency") or "").strip().upper()
        currency_unit = str(
            body.get("currency_unit") or body.get("currencyUnit") or ""
        ).strip().upper()
        service = PricingMatrixService(self.db)
        if not currency and not currency_unit:
            return service.unit_declaration(scope, scope_reference)
        if not currency or not currency_unit:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Both currency and currency_unit are required.",
            )
        if user is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "An authenticated actor is required to declare monetary units.",
            )
        connector_version = str(body.get("configuration_version") or "commerce-v1")
        declaration = service.declare_unit(
            scope=scope,
            scope_reference=scope_reference,
            currency=currency,
            unit=currency_unit,
            user=user,
            connector_config_version=connector_version,
            commit=False,
        )
        if scope == "source":
            managed_source = (
                self.db.query(SourceProfile)
                .filter_by(external_source_id=scope_reference)
                .one_or_none()
            )
            if managed_source is not None:
                service.declare_unit(
                    scope="source",
                    scope_reference=managed_source.id,
                    currency=currency,
                    unit=currency_unit,
                    user=user,
                    connector_config_version=connector_version,
                    commit=False,
                )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return declaration

    def _configuration_setting_value(self, provider: str, key: str, value: object) -> object:
        if provider == "tapsishop" and key in {"token_refresh_enabled", "revoke_current_token"}:
            return parse_config_bool(value)
        if provider == "snappshop":
            if key == "request_timeout":
                return _safe_integer_timeout(value)
            if key == "agent_header_name":
                return str(value or SNAPPSHOP_DEFAULT_AGENT_HEADER)
        if provider in {"technolife", "digikala"} and key == "request_timeout":
            return _safe_integer_timeout(value)
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
        connection_configured = (
            self._nextcloud_connection_configured(instance)
            if provider == "nextcloud"
            else configured
        )
        secret_status = self._secret_status(instance)
        setup_configured = self._source_setup_configured(
            str(meta["id"]), provider, instance
        )
        read_status = SpreadsheetSourceReadService(self.db).read_status() if provider == "nextcloud" else None
        body = {
            **meta,
            "status": self._status(meta, instance, health),
            # Nextcloud connection credentials are complete before the later
            # spreadsheet setup is complete. Keep those states distinct so
            # clients do not have to infer persisted setup from health or UI
            # draft values.
            "credential_status": (
                "configured" if connection_configured else "not_configured"
            ),
            "connection_configured": connection_configured,
            "configuration_state": self._source_configuration_state(
                meta,
                connection_configured=connection_configured,
                configured=setup_configured,
            ),
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

    @staticmethod
    def _source_configuration_state(
        meta: dict, *, connection_configured: bool, configured: bool
    ) -> str:
        """Describe persisted Source setup without relying on health evidence."""
        if bool(meta.get("placeholder")) or not connection_configured:
            return "not_configured"
        if not configured:
            return "setup_required"
        return "configured"

    def _source_setup_configured(
        self,
        source_id: str,
        provider: str,
        instance: IntegrationConnectorInstance | None,
    ) -> bool:
        """Return complete persisted setup state for Source status presentation."""
        if provider != "nextcloud":
            return self._instance_configured(instance)
        if not self._instance_configured(instance):
            return False

        settings = {item.key: item for item in instance.settings} if instance else {}
        worksheet_mode = str(
            settings.get("worksheet_mode").value_json
            if settings.get("worksheet_mode") is not None
            else "all"
        ).strip().lower()
        if worksheet_mode not in {"all", "selected"}:
            return False
        if worksheet_mode == "selected":
            worksheet_name = settings.get("worksheet_name")
            if worksheet_name is None or not str(worksheet_name.value_json or "").strip():
                return False

        currency = PricingMatrixService(self.db).unit_declaration("source", source_id)
        if currency.get("status") != "resolved":
            return False

        managed_source = (
            self.db.query(SourceProfile)
            .filter_by(external_source_id=source_id, status="active")
            .one_or_none()
        )
        if managed_source is None:
            return False
        return (
            self.db.query(SourceMappingRevision.id)
            .filter(SourceMappingRevision.source_id == managed_source.id)
            .first()
            is not None
        )

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
        if provider == "technolife":
            cached_products = len(
                {str(row.parent_id) for row in cache_rows if row.parent_id not in (None, "")}
            )
        elif provider == "snappshop":
            cached_products = len(cache_rows)
        else:
            cached_products = len(cache_rows) - cached_variations
        latest_refresh = self._latest_product_refresh(str(meta["id"]))
        configuration_state = self._channel_configuration_state(instance, health, latest_refresh)
        display_name, display_name_custom = self._channel_display_name(meta, instance)
        body = {
            "id": meta["id"],
            "provider": provider,
            "name": display_name,
            "display_name_custom": display_name_custom,
            "type": "Channel",
            "status": self._status(meta, instance, health),
            "implemented": meta["implemented"],
            "implementation_status": meta.get("implementation_status"),
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
            "access_token_configured": secret_status.get("access_token", {}).get("status") == "configured",
            "refresh_token_configured": secret_status.get("refresh_token", {}).get("status") == "configured",
            "last_health_check": self._iso(health.checked_at) if health else None,
            "health": self._health_contract(health),
            "capabilities": capabilities.model_dump(),
            "capabilities_summary": self._capabilities_summary(capabilities),
            "settings_available": definition is not None,
            "cached_products": cached_products,
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

    @staticmethod
    def _channel_display_name(
        meta: dict, instance: IntegrationConnectorInstance | None
    ) -> tuple[str, bool]:
        """Return a canonical system label or a persisted Owner custom name."""

        provider = str(meta["provider"])
        persisted = str(instance.name or "").strip() if instance is not None else ""
        aliases = _CHANNEL_SYSTEM_NAME_ALIASES.get(provider, frozenset())
        explicitly_custom = bool(
            instance
            and any(
                setting.key == _CHANNEL_DISPLAY_NAME_CUSTOM_KEY
                and setting.configured
                and setting.value_json is True
                for setting in instance.settings
            )
        )
        custom = bool(persisted) and (
            explicitly_custom or persisted.casefold() not in aliases
        )
        return (persisted, True) if custom else (str(meta["name"]), False)

    @staticmethod
    def channel_display_name_for_instance(
        instance: IntegrationConnectorInstance,
    ) -> tuple[str, bool]:
        """Resolve one persisted instance for non-Commerce channel surfaces."""

        meta = next(
            (
                item
                for item in _CHANNELS
                if str(item["provider"]) == instance.connector_type
            ),
            None,
        )
        if meta is None:
            definition = registry.get_definition(instance.connector_type)
            meta = {
                "provider": instance.connector_type,
                "name": (
                    definition.connector.identity.name
                    if definition is not None
                    else instance.connector_type
                ),
            }
        return CommerceHubService._channel_display_name(meta, instance)

    @staticmethod
    def _set_channel_display_name_custom(
        instance: IntegrationConnectorInstance,
        *,
        custom: bool,
    ) -> None:
        """Persist explicit Owner-name provenance without a schema migration."""

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        marker = next(
            (
                setting
                for setting in instance.settings
                if setting.key == _CHANNEL_DISPLAY_NAME_CUSTOM_KEY
            ),
            None,
        )
        if marker is None:
            if not custom:
                return
            instance.settings.append(
                IntegrationConnectorSetting(
                    key=_CHANNEL_DISPLAY_NAME_CUSTOM_KEY,
                    value_json=custom,
                    secret=False,
                    configured=True,
                    updated_at=now,
                )
            )
            return
        marker.value_json = custom
        marker.secret = False
        marker.configured = True
        marker.updated_at = now

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
            "technolife": {"api_key", "encryption_secret"},
            "digikala": {"access_token"},
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
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
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
            if str(meta.get("id")) in _CHANNEL_IDS:
                self._set_channel_display_name_custom(
                    row,
                    custom=(
                        display_name.casefold()
                        != str(meta.get("name") or "").strip().casefold()
                    ),
                )
        enabled = body.get("enabled") if isinstance(body, dict) else None
        if enabled is not None:
            row.enabled = bool(enabled) and not bool(meta.get("placeholder"))
        elif access_mode == ACCESS_MODE_WRITE_ENABLED:
            row.enabled = not bool(meta.get("placeholder"))
        row.read_only = access_mode != ACCESS_MODE_WRITE_ENABLED
        row.status = "disabled" if not row.enabled else "configured"
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def _settings_body(self, body: dict) -> dict:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        access_mode = body.get("access_mode", body.get("accessMode")) if isinstance(body, dict) else None
        if access_mode not in (None, ""):
            settings["access_mode"] = access_mode
        if isinstance(body, dict) and "description" in body:
            settings["description"] = str(body.get("description") or "").strip()
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
        return (
            str(meta.get("id")) in {
                "woocommerce:primary",
                "snappshop:main",
                "tapsishop:main",
                "technolife:main",
            }
            and not bool(meta.get("placeholder"))
        )

    def _write_pipeline_eligible(self, meta: dict, instance: IntegrationConnectorInstance | None) -> bool:
        if str(meta.get("id")) == "snappshop:main" and not self._instance_configured(instance):
            return False
        return (
            self._write_pipeline_supported(meta)
            and instance is not None
            and instance.enabled
            and self._access_mode(instance) == ACCESS_MODE_WRITE_ENABLED
        )

    def channel_write_enabled(self, channel_id: str) -> bool:
        """Return the authoritative server-side write-mode state for a channel."""

        meta = self._channel_meta(channel_id)
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        return self._write_pipeline_eligible(meta, instance)

    def _has_submitted_credentials(self, meta: dict, body: dict | None) -> bool:
        if not isinstance(body, dict):
            return False
        settings = body.get("settings") if isinstance(body.get("settings"), dict) else {}
        secrets = body.get("secrets") if isinstance(body.get("secrets"), dict) else {}
        provider = str(meta["provider"])
        if provider == "woocommerce":
            values = self._woocommerce_values(body)
            return bool(values["url"] and values["key"] and values["secret"])
        if provider == "snappshop":
            return bool(str(settings.get("agent_identifier") or self.integration.config.get("snappshop.agent_identifier") or "").strip()) and bool(
                str(secrets.get("token") or self.integration.config.get("snappshop.token") or "").strip()
            )
        if provider == "tapsishop":
            return bool(str(secrets.get("token") or self.integration.config.get("tapsishop.token") or "").strip())
        if provider == "technolife":
            return bool(
                str(secrets.get("api_key") or self.integration.config.get("technolife.api_key") or "").strip()
            ) and bool(
                str(
                    secrets.get("encryption_secret")
                    or self.integration.config.get("technolife.encryption_secret")
                    or ""
                ).strip()
            )
        if provider == "digikala":
            return bool(
                str(
                    secrets.get("access_token")
                    or self.integration.config.get("digikala.access_token")
                    or ""
                ).strip()
            )
        return False

    def _channel_test_matches_stored_configuration(
        self, meta: dict, body: dict | None
    ) -> bool:
        """Persist health only when the probe represents the saved connector."""
        provider = str(meta["provider"])
        if provider == "woocommerce":
            return self._woocommerce_values(body) == self._woocommerce_values({})
        if provider not in {"snappshop", "tapsishop", "technolife", "digikala"}:
            return False
        tested_settings, tested_secrets = self._connector_values(provider, body)
        stored_settings, stored_secrets = self._connector_values(provider, {})
        return (
            tested_settings == stored_settings
            and tested_secrets == stored_secrets
        )

    def _validate_channel_configuration(self, meta: dict, body: dict) -> None:
        provider = str(meta["provider"])
        if provider == "woocommerce":
            url = self._woocommerce_values(body)["url"]
            if url:
                try:
                    self._normalize_woocommerce_url(url)
                except ValueError as exc:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
            return
        if provider not in {"snappshop", "tapsishop", "technolife", "digikala"}:
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
            elif provider == "tapsishop":
                TapsiShopConfig.from_values(settings=settings, secrets=secrets)
            elif provider == "technolife":
                TechnolifeConfig.from_values(settings=settings, secrets=secrets)
            else:
                DigikalaConfig.from_values(settings=settings, secrets=secrets)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    def _connector_values(self, provider: str, body: dict | None) -> tuple[dict, dict]:
        submitted_settings = body.get("settings") if isinstance(body, dict) and isinstance(body.get("settings"), dict) else {}
        submitted_secrets = body.get("secrets") if isinstance(body, dict) and isinstance(body.get("secrets"), dict) else {}
        setting_keys = {
            "snappshop": ("base_url", "agent_identifier", "agent_header_name", "request_timeout", "vendor_id"),
            "tapsishop": (
                "base_url", "request_timeout", "selected_vendor_id", "token_refresh_enabled",
                "token_refresh_name", "revoke_current_token",
            ),
            "technolife": ("base_url", "request_timeout"),
            "digikala": ("base_url", "request_timeout"),
        }.get(provider, ())
        secret_keys = {
            "snappshop": ("token",),
            "tapsishop": ("token", "webhook_token"),
            "technolife": ("api_key", "encryption_secret"),
            "digikala": ("access_token", "refresh_token"),
        }.get(provider, ())
        defaults = {
            "snappshop": {"base_url": SNAPPSHOP_BASE_URL, "agent_header_name": "User-Agent", "request_timeout": 30},
            "tapsishop": {"base_url": TAPSISHOP_BASE_URL, "request_timeout": 30},
            "technolife": {"base_url": TECHNOLIFE_BASE_URL, "request_timeout": 30},
            "digikala": {"base_url": DIGIKALA_BASE_URL, "request_timeout": 30},
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
        elif provider == "technolife":
            settings["base_url"] = str(
                settings.get("base_url") or TECHNOLIFE_BASE_URL
            ).strip().rstrip("/")
            if "request_timeout" not in submitted_settings:
                settings["request_timeout"] = _safe_integer_timeout(settings.get("request_timeout"))
        elif provider == "digikala":
            settings["base_url"] = str(
                settings.get("base_url") or DIGIKALA_BASE_URL
            ).strip().rstrip("/")
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
            # Credentials may be saved before vendor discovery. The channel
            # remains in Setup Required until an active vendor is selected.
            return
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

    async def _test_woocommerce_channel_connection(
        self, configured: bool, body: dict | None = None
    ) -> dict:
        try:
            creds = self._woocommerce_credentials(body)
        except ValueError as exc:
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status": "error",
                "http_status": None,
                "latency_ms": None,
                "checked_at": self._checked_at(),
                "message": str(exc),
                "code": "CHANNEL_INVALID_URL",
                "external_call_performed": False,
            }
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
    def _woocommerce_credentials(self, body: dict | None = None) -> WooCommerceCredentials | None:
        values = self._woocommerce_values(body)
        url = values["url"]
        key = values["key"]
        secret = values["secret"]
        if not url or not key or not secret:
            return None
        return WooCommerceCredentials(url=self._normalize_woocommerce_url(url), key=key, secret=secret)

    def _woocommerce_values(self, body: dict | None = None) -> dict[str, str]:
        settings = body.get("settings") if isinstance(body, dict) and isinstance(body.get("settings"), dict) else {}
        secrets = body.get("secrets") if isinstance(body, dict) and isinstance(body.get("secrets"), dict) else {}
        return {
            "url": str(settings.get("url") or self.integration.config.get("woocommerce.url") or "").strip(),
            "key": str(secrets.get("key") or self.integration.config.get("woocommerce.key") or "").strip(),
            "secret": str(secrets.get("secret") or self.integration.config.get("woocommerce.secret") or "").strip(),
        }

    def _normalize_woocommerce_url(self, value: str) -> str:
        message = "WooCommerce Store URL must be an absolute HTTP or HTTPS URL."
        url = str(value or "").strip().rstrip("/")
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            parsed.port
        except ValueError as exc:
            raise ValueError(message) from exc
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
            raise ValueError(message)
        return url

    def _record_channel_test_health(self, meta: dict, result: dict) -> None:
        if not result.get("external_call_performed") and result.get("code") != "CHANNEL_INVALID_URL":
            return
        ok = bool(result.get("ok"))
        result_status = str(result.get("status") or "")
        code = str(result.get("code") or "")
        http_status = result.get("http_status")
        if ok:
            error_class = None
        elif result_status == "authentication_failed" or result.get("authenticated") is False and http_status in {401, 403}:
            error_class = "authentication_failed"
        elif code == "CHANNEL_INVALID_URL":
            error_class = "invalid_url"
        elif http_status == 429:
            error_class = "rate_limited"
        else:
            error_class = "connection_failed"
        ConnectorHealthService(self.db).upsert(
            connector_id=str(meta["id"]),
            connector_type=str(meta["provider"]),
            status="healthy" if ok else "unhealthy",
            latency_ms=result.get("latency_ms"),
            detail=str(result.get("message") or "")[:500],
            error_class=error_class,
        )

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
        # A connection test is observational: it must never rotate, revoke, or
        # persist marketplace credentials. Token refresh remains available to
        # normal connector operations after explicit configuration Save.
        connector = self._tapsishop_connector(body, allow_token_refresh=False)
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

    def _tapsishop_connector(
        self, body: dict | None = None, *, allow_token_refresh: bool = True
    ) -> TapsiShopConnector | None:
        settings, secrets = self._connector_values("tapsishop", body)
        try:
            config = TapsiShopConfig.from_values(
                settings=settings,
                secrets=secrets,
            )
        except (TypeError, ValueError):
            return None

        if not allow_token_refresh and config.refresh_enabled:
            config = replace(config, refresh_enabled=False)

        def update_token(new_token: str) -> None:
            self.integration.config.set("tapsishop.token", new_token, updated_by="tapsishop_refresh")

        return TapsiShopConnector(
            channel_id="tapsishop:main",
            config=config,
            token_updater=update_token if allow_token_refresh else None,
        )

    async def _test_technolife_channel_connection(
        self, configured: bool, body: dict | None = None
    ) -> dict:
        connector = self._technolife_connector(body)
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
                "message": "Technolife is not configured. No external call was performed.",
                "external_call_performed": False,
            }
        started = monotonic()
        health = await connector.test_connection()
        latency_ms = health.latency_ms or round((monotonic() - started) * 1000, 2)
        if health.status != "healthy":
            error = health.error
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": bool(
                    error
                    and error.category.value not in {"authentication", "authorization"}
                ),
                "status": (
                    "authentication_failed"
                    if error and error.category.value == "authentication"
                    else "error"
                ),
                "http_status": error.http_status if error else None,
                "latency_ms": latency_ms,
                "checked_at": self._checked_at(),
                "message": error.message if error else "Technolife connection failed.",
                "external_call_performed": True,
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
            "message": "Connected to Technolife. Product probe succeeded.",
            "external_call_performed": True,
        }

    def _technolife_connector(self, body: dict | None = None) -> TechnolifeConnector | None:
        settings, secrets = self._connector_values("technolife", body)
        try:
            config = TechnolifeConfig.from_values(settings=settings, secrets=secrets)
        except (TypeError, ValueError):
            return None
        return TechnolifeConnector(channel_id="technolife:main", config=config)

    async def _test_digikala_channel_connection(
        self, configured: bool, body: dict | None = None
    ) -> dict:
        # This test must remain an observational, authenticated GET /orders.
        # In particular it may not refresh or replace either submitted/stored
        # token, because a connection test is not credential rotation.
        connector = self._digikala_connector(body, allow_token_refresh=False)
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
                "message": "Digikala is not configured. No external call was performed.",
                "code": "DIGIKALA_NOT_CONFIGURED",
                "error_class": "not_configured",
                "retryable": False,
                "retry_after_seconds": None,
                "external_call_performed": False,
            }
        started = monotonic()
        health = await connector.test_connection()
        latency_ms = health.latency_ms or round((monotonic() - started) * 1000, 2)
        if health.status != "healthy":
            error = health.error
            return {
                **self._connection_base(),
                "ok": False,
                "connected": False,
                "authenticated": bool(
                    error
                    and error.category.value not in {"authentication", "authorization"}
                ),
                "status": (
                    "authentication_failed"
                    if error and error.category.value == "authentication"
                    else "error"
                ),
                "http_status": error.http_status if error else None,
                "latency_ms": latency_ms,
                "checked_at": self._checked_at(),
                "message": error.message if error else "Digikala connection failed.",
                # Never surface the provider error body or provider code: it
                # can contain echoed credentials.  The category and retry
                # metadata are sufficient structured diagnostic evidence.
                "code": (
                    f"DIGIKALA_{error.category.value.upper()}"
                    if error
                    else "DIGIKALA_CONNECTION_FAILED"
                ),
                "error_class": error.category.value if error else "connection_failed",
                "retryable": bool(error and error.retry.retryable),
                "retry_after_seconds": (
                    error.retry.retry_after_seconds if error else None
                ),
                "external_call_performed": True,
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
            "message": "Connected to Digikala. Read-only orders probe succeeded.",
            "external_call_performed": True,
        }

    def _digikala_connector(
        self,
        body: dict | None = None,
        *,
        allow_token_refresh: bool = True,
    ) -> DigikalaConnector | None:
        settings, secrets = self._connector_values("digikala", body)
        try:
            config = DigikalaConfig.from_values(settings=settings, secrets=secrets)
        except (TypeError, ValueError):
            return None
        return DigikalaConnector(
            channel_id="digikala:main",
            config=config,
            token_updater=(
                self._persist_digikala_refreshed_tokens
                if allow_token_refresh
                else None
            ),
            allow_token_refresh=allow_token_refresh,
        )

    def _persist_digikala_refreshed_tokens(
        self, access_token: str, refresh_token: str
    ) -> None:
        """Persist rotated tokens securely and update Integration Platform metadata."""

        try:
            self.integration.config.set_many(
                {
                    "digikala.access_token": access_token,
                    "digikala.refresh_token": refresh_token,
                },
                updated_by="digikala_refresh",
                commit=False,
            )
            row = self.db.get(IntegrationConnectorInstance, "digikala:main")
            if row is not None:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                existing = {setting.key: setting for setting in row.settings}
                for key in ("access_token", "refresh_token"):
                    setting = existing.get(key)
                    if setting is None:
                        row.settings.append(
                            IntegrationConnectorSetting(
                                key=key,
                                # Integration Platform settings carry only
                                # write-only secret state.  The rotated value
                                # itself lives in AppConfig's secret store.
                                value_json=None,
                                secret=True,
                                configured=True,
                                updated_at=now,
                            )
                        )
                    else:
                        setting.value_json = None
                        setting.secret = True
                        setting.configured = True
                        setting.updated_at = now
                self.integration.record_event(
                    connector_id="digikala:main",
                    event_name="digikala_tokens_refreshed",
                    message="Digikala credentials were refreshed; replacement values remain write-only.",
                    metadata={"secret_values_returned": False},
                    commit=False,
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    async def _test_nextcloud_source_connection(self, body: dict | None = None) -> dict:
        request_body = body or {}
        values = self._nextcloud_values(request_body, allow_stored=True)
        record_health = self._nextcloud_test_matches_stored_configuration(request_body)
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
                "code": "not_configured",
                "error_class": "not_configured",
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
                record_health=record_health,
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
                "code": "not_configured",
                "error_class": "not_configured",
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
            trusted_private_networks=parse_trusted_private_networks(
                self.integration.config.get("nextcloud.trusted_private_networks")
            ),
        )
        try:
            await client.browse_directory("/")
            spreadsheet_path = values.get("spreadsheet_path") or ""
            spreadsheet_found: bool | None = None
            if spreadsheet_path:
                try:
                    item = await client.get_resource_info(spreadsheet_path)
                except IntegrationError as exc:
                    error_class = self._nextcloud_error_class(exc)
                    if error_class != "resource_not_found":
                        return self._nextcloud_test_failure(
                            started,
                            checked_at,
                            self._safe_nextcloud_error_message(exc),
                            normalized_base_url=normalized["server_root_url"],
                            normalized_webdav_url=normalized_webdav_url,
                            webdav_reachable=True,
                            spreadsheet_found=None,
                            external=True,
                            http_status=exc.status_code,
                            error_class=error_class,
                            record_health=record_health,
                        )
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
                        error_class="resource_not_found",
                        record_health=record_health,
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
                        error_class="invalid_webdav_path",
                        record_health=record_health,
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
                        record_health=record_health,
                    )
                spreadsheet_found = True
                provider = NextcloudWebDavAcquisitionProvider(
                    webdav_files_root_url=normalized_webdav_url,
                    spreadsheet_path=spreadsheet_path,
                    username=normalized["username"],
                    app_password=values["password"],
                    capture_contract="connection-preflight",
                )
                try:
                    await SourceHttpClient().with_allowed_private_networks(
                        parse_trusted_private_networks(
                            self.integration.config.get("nextcloud.trusted_private_networks")
                        )
                    ).preflight(provider.resource_url)
                except SourceHttpError as exc:
                    safety_code, safety_message = self._nextcloud_source_http_failure(
                        exc
                    )
                    return self._nextcloud_test_failure(
                        started,
                        checked_at,
                        safety_message,
                        normalized_base_url=normalized["server_root_url"],
                        normalized_webdav_url=normalized_webdav_url,
                        webdav_reachable=True,
                        spreadsheet_found=True,
                        external=True,
                        error_class=safety_code,
                        code=safety_code,
                        record_health=record_health,
                    )
            latency_ms = round((monotonic() - started) * 1000, 2)
            message = (
                "Connection successful. Spreadsheet found."
                if spreadsheet_found is True
                else "Connection successful. Select a spreadsheet file to enable preview."
            )
            if record_health:
                self._record_source_health(
                    "nextcloud:primary", "healthy", latency_ms, message, None
                )
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
                record_health=record_health,
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
                error_class="connection_failed",
                record_health=record_health,
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
        record_health: bool = False,
    ) -> dict:
        latency_ms = round((monotonic() - started) * 1000, 2)
        stable_error_class = error_class or "connection_failed"
        response_code = code or stable_error_class
        if record_health:
            self._record_source_health(
                "nextcloud:primary",
                "unhealthy",
                latency_ms,
                message,
                stable_error_class,
            )
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
            "code": response_code,
            "error_class": stable_error_class,
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

    def _clear_source_health(self, source_id: str) -> None:
        health = self._health(source_id)
        if health is None:
            return
        self.db.delete(health)
        self.db.commit()

    def _safe_nextcloud_error_message(self, exc: IntegrationError) -> str:
        code = self._nextcloud_error_class(exc)
        messages = {
            "authentication_failed": "Authentication failed.",
            "permission_denied": "Nextcloud rejected access to the WebDAV path.",
            "resource_not_found": "The configured WebDAV path was not found.",
            "invalid_webdav_path": "The configured WebDAV path is invalid.",
            "timeout": "The Nextcloud server did not respond in time.",
            "unsafe_destination": "The configured source destination is blocked by the Source network safety policy.",
            "dns_resolution_failed": "The Nextcloud server hostname could not be resolved.",
            "tls_error": "A secure connection to the Nextcloud server could not be established.",
            "network_unreachable": "The Nextcloud server could not be reached.",
        }
        return messages.get(
            code,
            str(normalize_upstream_error(exc, source="nextcloud")["message"]),
        )

    def _nextcloud_source_http_failure(
        self, exc: SourceHttpError
    ) -> tuple[str, str]:
        raw_code = str(exc.code or "").strip().lower()
        if raw_code in {"unsafe_destination", "unsafe_redirect"}:
            return (
                "unsafe_destination",
                "The configured source destination is blocked by the Source network safety policy.",
            )
        if raw_code in {
            "timeout",
            "total_timeout",
            "connect_timeout",
            "read_timeout",
        }:
            return "timeout", "The Nextcloud server did not respond in time."
        if raw_code == "dns_resolution_failed":
            return (
                "dns_resolution_failed",
                "The Nextcloud server hostname could not be resolved.",
            )
        if raw_code == "tls_error":
            return (
                "tls_error",
                "A secure connection to the Nextcloud server could not be established.",
            )
        if raw_code in {"invalid_url", "credentials_in_url", "unsupported_scheme"}:
            return "invalid_webdav_path", "The configured WebDAV path is invalid."
        return "network_unreachable", "The Nextcloud server could not be reached."

    def _nextcloud_error_class(self, exc: IntegrationError) -> str:
        code = str(getattr(exc, "code", "") or "").strip().lower()
        if code in {
            "authentication_failed",
            "permission_denied",
            "resource_not_found",
            "invalid_webdav_path",
            "timeout",
            "unsafe_destination",
            "dns_resolution_failed",
            "tls_error",
            "network_unreachable",
        }:
            return code
        message = (exc.message or "").lower()
        if "authentication failed" in message or "access denied" in message:
            return "authentication_failed"
        if "not found" in message:
            return "resource_not_found"
        if "invalid nextcloud path" in message or "invalid webdav path" in message:
            return "invalid_webdav_path"
        if "timed out" in message:
            return "timeout"
        if "could not connect" in message or "connection" in message:
            return "network_unreachable"
        return "connection_failed"

    def _nextcloud_configuration_identity(
        self, body: dict, *, allow_stored: bool
    ) -> tuple[str, str, str, str, str] | None:
        """Return an internal-only identity for the values exercised by Test."""
        values = self._nextcloud_values(body, allow_stored=allow_stored)
        if not values["url"] or not values["password"]:
            return None
        try:
            normalized = self._normalize_nextcloud_url(
                values["url"], values["username"]
            )
        except HTTPException:
            return (
                values["url"],
                "",
                values["username"],
                values["password"],
                values["spreadsheet_path"],
            )
        return (
            normalized["server_root_url"],
            normalized["webdav_files_root_url"],
            normalized["username"],
            values["password"],
            values["spreadsheet_path"],
        )

    def _nextcloud_test_matches_stored_configuration(self, body: dict) -> bool:
        stored = self._nextcloud_configuration_identity({}, allow_stored=True)
        candidate = self._nextcloud_configuration_identity(body, allow_stored=True)
        return stored is not None and candidate == stored

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
        values = self._nextcloud_values(body, allow_stored=True)
        if values["url"]:
            normalized = self._normalize_nextcloud_url(values["url"], values["username"])
            values["username"] = values["username"] or normalized["username"]
        # Connection credentials can be saved before the user chooses a workbook.
        # Reading and worksheet discovery still require spreadsheet_path.
        required = ("url", "username", "password")
        missing = [key for key in required if not values[key]]
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "NEXTCLOUD_REQUIRED_SETTINGS_MISSING",
                    "message": f"Missing required Nextcloud setting(s): {', '.join(missing)}.",
                    "fields": missing,
                },
            )
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

    def _persist_technolife_app_config(self, body: dict, *, commit: bool = True) -> None:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        pairs: dict[str, str] = {
            "technolife.base_url": str(
                settings.get("base_url") or TECHNOLIFE_BASE_URL
            ).strip().rstrip("/"),
            "technolife.request_timeout": str(
                _safe_integer_timeout(settings.get("request_timeout"))
            ),
        }
        if secrets.get("api_key"):
            pairs["technolife.api_key"] = str(secrets["api_key"])
        if secrets.get("encryption_secret"):
            pairs["technolife.encryption_secret"] = str(secrets["encryption_secret"])
        self.integration.config.set_many(
            pairs, updated_by="commerce_hub", commit=commit
        )

    def _persist_digikala_app_config(self, body: dict, *, commit: bool = True) -> None:
        settings = dict(body.get("settings") or {}) if isinstance(body, dict) else {}
        secrets = dict(body.get("secrets") or {}) if isinstance(body, dict) else {}
        pairs: dict[str, str] = {
            "digikala.base_url": str(
                settings.get("base_url") or DIGIKALA_BASE_URL
            ).strip().rstrip("/"),
            "digikala.request_timeout": str(
                _safe_integer_timeout(settings.get("request_timeout"))
            ),
        }
        if secrets.get("access_token"):
            pairs["digikala.access_token"] = str(secrets["access_token"])
        if secrets.get("refresh_token"):
            pairs["digikala.refresh_token"] = str(secrets["refresh_token"])
        self.integration.config.set_many(
            pairs, updated_by="commerce_hub", commit=commit
        )

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
            "implementation_status": meta.get("implementation_status"),
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
        elif instance.connector_type == "technolife":
            required = {"api_key", "encryption_secret"}
        elif instance.connector_type == "digikala":
            required = {"access_token"}
        elif instance.connector_type == "shopify":
            required = {"api_token"}
        elif instance.connector_type == "nextcloud":
            required = {"url", "username", "password", "spreadsheet_path"}
        elif instance.connector_type == "csv":
            required = {"file_path"}
        elif instance.connector_type == "gsheets":
            required = {"sheet_ref"}
        elif instance.connector_type == "erp":
            required = {"api_token"}
        else:
            required = set()
        return bool(required) and all(settings.get(key) and settings[key].configured for key in required)

    def _nextcloud_connection_configured(
        self, instance: IntegrationConnectorInstance | None
    ) -> bool:
        """Return persisted Step-2 state without requiring a spreadsheet selection."""
        if instance is None or instance.connector_type != "nextcloud":
            return False
        settings = {item.key: item for item in instance.settings}
        return all(
            settings.get(key) is not None and settings[key].configured
            for key in ("url", "username", "password")
        )

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
        return self._iso(datetime.now(timezone.utc).replace(tzinfo=None)) or ""

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
