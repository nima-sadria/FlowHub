"""Canonical Integration Platform connector registry."""

from __future__ import annotations

from app.beta.integration_platform.contracts import (
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
}


class ConnectorRegistry:
    def list_definitions(self) -> list[ConnectorDefinition]:
        return list(_DEFINITIONS.values())

    def get_definition(self, connector_type: str) -> ConnectorDefinition | None:
        return _DEFINITIONS.get(connector_type)


registry = ConnectorRegistry()
