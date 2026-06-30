"""WooCommerce authentication helpers.

All credential extraction is isolated here. Connector and REST client modules
import from this file — they never receive raw credential dicts.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode


@dataclass(frozen=True)
class WooCommerceCredentials:
    url: str          # base store URL, trailing slash stripped
    key: str          # consumer key
    secret: str       # consumer secret


def extract_credentials(auth: AuthConfig) -> WooCommerceCredentials:
    """Extract and validate WooCommerce credentials from an AuthConfig.

    Raises ConnectorError(AUTH_FAILED) if required fields are missing.
    """
    if auth.auth_type not in ("api_key", "none"):
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message=f"WooCommerce connector requires auth_type 'api_key', got '{auth.auth_type}'",
            provider="woocommerce",
        )
    url = auth.get("url", "")
    key = auth.get("key", "")
    secret = auth.get("secret", "")

    if not url:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="WooCommerce auth missing 'url'",
            provider="woocommerce",
        )
    if not key:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="WooCommerce auth missing 'key'",
            provider="woocommerce",
        )
    if not secret:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="WooCommerce auth missing 'secret'",
            provider="woocommerce",
        )

    return WooCommerceCredentials(
        url=url.rstrip("/"),
        key=key,
        secret=secret,
    )
