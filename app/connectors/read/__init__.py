"""ReadConnectorAdapter implementations for production manual reads."""

from .nextcloud import NextcloudSpreadsheetReadAdapter
from .woocommerce import WooCommerceProductReadAdapter

__all__ = ["NextcloudSpreadsheetReadAdapter", "WooCommerceProductReadAdapter"]
