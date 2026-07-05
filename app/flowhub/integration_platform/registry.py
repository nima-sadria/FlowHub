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
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="file_path", label="File/path placeholder", required=False),
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
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="sheet_ref", label="Sheet URL or Sheet ID placeholder", required=False),
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
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="base_url", label="Base URL placeholder", required=False),
            ConnectorSettingDefinition(key="api_token", label="API token placeholder", required=False, secret=True),
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
                read_categories=True,
                read_inventory=True,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="base_url", label="API URL", required=False),
            ConnectorSettingDefinition(key="merchant_id", label="Merchant ID", required=False),
            ConnectorSettingDefinition(key="api_key", label="API key", required=False, secret=True),
            ConnectorSettingDefinition(key="api_secret", label="API secret", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
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
                read_categories=True,
                read_inventory=True,
                read_orders=False,
                write_prices=False,
                write_inventory=False,
                webhook=False,
                polling=False,
                oauth=False,
                api_key=True,
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="base_url", label="API URL", required=False),
            ConnectorSettingDefinition(key="merchant_id", label="Merchant ID", required=False),
            ConnectorSettingDefinition(key="api_key", label="API key", required=False, secret=True),
            ConnectorSettingDefinition(key="api_secret", label="API secret", required=False, secret=True),
        ],
        diagnostics_contract=_diagnostics(
            ("settings", "configuration"),
            ("placeholder", "capability_detection"),
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
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="seller_id", label="Seller/store ID placeholder", required=False),
            ConnectorSettingDefinition(key="api_token", label="API key/token placeholder", required=False, secret=True),
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
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="seller_id", label="Seller/store ID placeholder", required=False),
            ConnectorSettingDefinition(key="api_token", label="API key/token placeholder", required=False, secret=True),
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
            ),
            status=ConnectorHealthStatus.DISABLED,
        ),
        settings_schema=[
            ConnectorSettingDefinition(key="seller_id", label="Seller/store ID placeholder", required=False),
            ConnectorSettingDefinition(key="api_token", label="API key/token placeholder", required=False, secret=True),
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
