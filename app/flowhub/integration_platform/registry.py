"""Canonical Integration Platform connector registry."""

from __future__ import annotations

from app.flowhub.integration_platform.contracts import (
    ConnectorCapabilities,
    ConnectorDefinition,
    ConnectorDescriptor,
    ConnectorDiagnosticsContract,
    ConnectorHealthStatus,
    ConnectorIdentity,
    ConnectorSettingDefinition,
    DiagnosticCheckContract,
)


def _diagnostics(*checks: tuple[str, str]) -> ConnectorDiagnosticsContract:
    return ConnectorDiagnosticsContract(
        checks=[DiagnosticCheckContract(name=name, category=category) for name, category in checks]
    )


_DEFINITIONS: dict[str, ConnectorDefinition] = {
    "woocommerce": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="woocommerce",
                name="WooCommerce",
                type="woocommerce",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=True,
                read_inventory=True,
                read_orders=True,
                write_prices=True,
                write_inventory=True,
                webhook=True,
                polling=True,
                oauth=False,
                api_key=True,
                supports_modified_since=True,
                supports_delta_sync=True,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="url", label="Store URL", required=True),
            ConnectorSettingDefinition(key="key", label="Consumer key", required=True, secret=True),
            ConnectorSettingDefinition(key="secret", label="Consumer secret", required=True, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("health_record", "health"),
            ("capabilities", "capability_detection"),
            ("telemetry", "telemetry"),
        ),
    ),
    "nextcloud": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="nextcloud",
                name="Nextcloud",
                type="nextcloud",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=False,
                read_inventory=False,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=True,
                oauth=False,
                api_key=False,
                supports_modified_since=True,
                supports_delta_sync=True,
                supports_updated_after=False,
                supports_pagination=False,
                supports_batch_read=False,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="url", label="Nextcloud URL", required=True),
            ConnectorSettingDefinition(key="username", label="Username", required=True),
            ConnectorSettingDefinition(key="password", label="Password", required=True, secret=True),
            ConnectorSettingDefinition(key="spreadsheet_path", label="Spreadsheet path", required=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("health_record", "health"),
            ("source_snapshot", "data_layer"),
            ("telemetry", "telemetry"),
        ),
    ),
    "csv": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="csv",
                name="CSV",
                type="csv",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=False,
                read_inventory=False,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=False,
                supports_modified_since=False,
                supports_delta_sync=False,
                supports_updated_after=False,
                supports_pagination=False,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="file_path", label="File path", required=False),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
            ("health_record", "health"),
        ),
    ),
    "gsheets": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="gsheets",
                name="Google Sheets",
                type="gsheets",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=False,
                read_inventory=False,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=False,
                supports_modified_since=False,
                supports_delta_sync=False,
                supports_updated_after=False,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="sheet_ref", label="Sheet URL or Sheet ID", required=False),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
            ("health_record", "health"),
        ),
    ),
    "erp": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="erp",
                name="ERP / API Import",
                type="erp",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=False,
                read_inventory=False,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=True,
                supports_modified_since=True,
                supports_delta_sync=True,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="base_url", label="Base URL", required=False),
            ConnectorSettingDefinition(key="api_token", label="API token", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
            ("health_record", "health"),
        ),
    ),
    "snappshop": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="snappshop",
                name="Snapp Shop",
                type="snappshop",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=False,
                read_inventory=True,
                read_orders=True,
                write_prices=True,
                write_inventory=True,
                webhook=False,
                polling=True,
                oauth=False,
                api_key=True,
                supports_modified_since=False,
                supports_delta_sync=False,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="base_url", label="Base URL", required=False, default="https://apix.snappshop.ir/automation/v1"),
            ConnectorSettingDefinition(key="agent_identifier", label="Agent identifier", required=True),
            ConnectorSettingDefinition(key="agent_header_name", label="Agent header name", required=False, default="User-Agent"),
            ConnectorSettingDefinition(key="request_timeout", label="Request timeout seconds", required=False, default=30),
            ConnectorSettingDefinition(key="vendor_id", label="Vendor ID", required=False),
            ConnectorSettingDefinition(key="token", label="Bearer token", required=True, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("vendor_probe", "health"),
            ("health_record", "health"),
        ),
    ),
    "tapsishop": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="tapsishop",
                name="Tapsi Shop",
                type="tapsishop",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=False,
                read_inventory=True,
                read_orders=True,
                write_prices=True,
                write_inventory=True,
                webhook=True,
                polling=False,
                oauth=False,
                api_key=True,
                supports_modified_since=False,
                supports_delta_sync=False,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="base_url", label="Base URL", required=False, default="https://vendorgw.tapsi.shop/Web/Hub/vendors/v1"),
            ConnectorSettingDefinition(key="request_timeout", label="Request timeout seconds", required=False, default=30),
            ConnectorSettingDefinition(key="selected_vendor_id", label="Selected vendor/store ID", required=False),
            ConnectorSettingDefinition(key="token_refresh_enabled", label="Token refresh enabled", required=False, default=False),
            ConnectorSettingDefinition(key="token_refresh_name", label="Token refresh name", required=False, default="FlowHub"),
            ConnectorSettingDefinition(key="revoke_current_token", label="Revoke current token on refresh", required=False, default=False),
            ConnectorSettingDefinition(key="token_refresh_expired_at", label="Token refresh expiration", required=False),
            ConnectorSettingDefinition(key="token", label="Authorization token", required=True, secret=True),
            ConnectorSettingDefinition(key="webhook_token", label="Webhook token", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("vendor_information_probe", "health"),
            ("health_record", "health"),
        ),
    ),
    "digikala": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="digikala",
                name="Digikala",
                type="digikala",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=True,
                read_inventory=True,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=True,
                supports_modified_since=True,
                supports_delta_sync=True,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="seller_id", label="Seller/store ID", required=False),
            ConnectorSettingDefinition(key="api_token", label="API key/token", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
            ("health_record", "health"),
        ),
    ),
    "technolife": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="technolife",
                name="Technolife",
                type="technolife",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=True,
                read_inventory=True,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=True,
                supports_modified_since=True,
                supports_delta_sync=True,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="seller_id", label="Seller/store ID", required=False),
            ConnectorSettingDefinition(key="api_token", label="API key/token", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
            ("health_record", "health"),
        ),
    ),
    "shopify": ConnectorDefinition(
        connector=ConnectorDescriptor(
            identity=ConnectorIdentity(
                id="shopify",
                name="Shopify",
                type="shopify",
                version="1.0.0",
                enabled=False,
                read_only=True,
            ),
            capabilities=ConnectorCapabilities(
                read_products=True,
                read_categories=True,
                read_inventory=True,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=True,
                supports_modified_since=True,
                supports_delta_sync=True,
                supports_updated_after=True,
                supports_pagination=True,
                supports_batch_read=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="seller_id", label="Seller/store ID", required=False),
            ConnectorSettingDefinition(key="api_token", label="API key/token", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
            ("health_record", "health"),
        ),
    ),
}


class ConnectorRegistry:
    def list_definitions(self) -> list[ConnectorDefinition]:
        return list(_DEFINITIONS.values())

    def get_definition(self, connector_type: str) -> ConnectorDefinition | None:
        return _DEFINITIONS.get(connector_type)


registry = ConnectorRegistry()
