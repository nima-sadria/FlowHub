"""FlowHub - Secret provider abstraction.

Secrets flow exclusively through environment variables. This abstraction
decouples callers from the secret source, enabling future migration to
Vault, AWS Secrets Manager, or other backends without code changes.
"""

import os
from abc import ABC, abstractmethod

SECRET_FIELDS: frozenset[str] = frozenset({
    "FLOWHUB_JWT_SECRET",
    "FLOWHUB_REST_API_SECRET",
    "FLOWHUB_POSTGRES_PASSWORD",
    "FLOWHUB_NEXTCLOUD_PASSWORD",
    "FLOWHUB_WOOCOMMERCE_KEY",
    "FLOWHUB_WOOCOMMERCE_SECRET",
})


class SecretProvider(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None:
        """Return the secret value for the given variable name, or None if absent."""
        ...

    @abstractmethod
    def names(self) -> list[str]:
        """Return all known secret variable names for this provider."""
        ...

    def is_secret(self, name: str) -> bool:
        """Return True if this variable name is a secret field."""
        return name in SECRET_FIELDS


class EnvSecretProvider(SecretProvider):
    """Reads secrets from environment variables. Default implementation."""

    def get(self, name: str) -> str | None:
        return os.environ.get(name)

    def names(self) -> list[str]:
        return sorted(SECRET_FIELDS)
