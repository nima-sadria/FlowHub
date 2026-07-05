"""Commerce Hub service.

Presents product-facing Sources and Channels while reusing Integration Platform
records for local settings, health, and capability metadata. Commerce Hub never
executes external marketplace writes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlConnectorHealth
from app.flowhub.integration_platform.contracts import ConnectorCapabilities
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integration_platform.registry import registry
from app.flowhub.integration_platform.service import IntegrationPlatformService


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

    def test_channel_connection(self, channel_id: str) -> dict:
        meta = self._channel_meta(channel_id)
        item = self._channel_contract(meta)
        configured = item["credential_status"] == "configured"
        placeholder = bool(meta["placeholder"])
        ok = configured and not placeholder
        if placeholder:
            message = f"{meta['name']} is a read-only future channel placeholder. No external call was performed."
        elif configured:
            message = "Local channel configuration is present. No external call was performed."
        else:
            message = "Channel is not configured. No external call was performed."
        return {
            "ok": ok,
            "status": "configured" if configured else "not_configured",
            "message": message,
            "external_call_performed": False,
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
            "correlation_id": self._correlation_id(),
        }

    def test_source_connection(self, source_id: str) -> dict:
        meta = self._source_meta(source_id)
        item = self._source_contract(meta)
        configured = item["credential_status"] == "configured"
        placeholder = bool(meta["placeholder"])
        if placeholder:
            message = f"{meta['name']} is a read-only future source placeholder. No external call was performed."
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

    def update_source_settings(self, source_id: str, body: dict) -> dict:
        meta = self._source_meta(source_id)
        provider = str(meta["provider"])
        if registry.get_definition(provider) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source settings are not available.")
        self._ensure_instance(meta)
        self._update_instance_state(meta, body)
        result = self.integration.update_settings_contract(source_id, self._settings_body(body))
        return {
            **result,
            "source_id": source_id,
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
        }

    def update_channel_settings(self, channel_id: str, body: dict) -> dict:
        meta = self._channel_meta(channel_id)
        provider = str(meta["provider"])
        if registry.get_definition(provider) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel settings are not available.")
        self._ensure_instance(meta)
        self._update_instance_state(meta, body)
        result = self.integration.update_settings_contract(channel_id, self._settings_body(body))
        return {
            **result,
            "channel_id": channel_id,
            "read_only": True,
            "runtime_write_blocked": True,
            "write_blocked": True,
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
        capabilities = definition.connector.capabilities if definition else ConnectorCapabilities()
        body = {
            "id": meta["id"],
            "provider": provider,
            "name": meta["name"],
            "type": "Channel",
            "status": self._status(meta, instance, health),
            "implemented": meta["implemented"],
            "placeholder": meta["placeholder"],
            "read_only": True,
            "write_blocked": True,
            "runtime_write_blocked": True,
            "credential_status": "configured" if configured else "not_configured",
            "last_health_check": self._iso(health.checked_at) if health else None,
            "health": self._health_contract(health),
            "capabilities": capabilities.model_dump(),
            "capabilities_summary": self._capabilities_summary(capabilities),
            "settings_available": definition is not None,
        }
        if detail:
            body["settings_schema"] = [
                item.model_dump() for item in definition.settings_schema
            ] if definition else []
            body["secrets"] = self._secret_status(instance)
        return body

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

    def _update_instance_state(self, meta: dict, body: dict) -> None:
        row = self.db.get(IntegrationConnectorInstance, meta["id"])
        if row is None:
            return
        display_name = str(body.get("display_name") or "").strip() if isinstance(body, dict) else ""
        if display_name:
            row.name = display_name
        enabled = body.get("enabled") if isinstance(body, dict) else None
        row.enabled = bool(enabled) and not bool(meta.get("placeholder"))
        row.read_only = True
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
        return enabled or ["Future channel placeholder"]

    def _correlation_id(self) -> str:
        return f"corr_{uuid.uuid4().hex[:12]}"

    def _iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat() + "Z"
