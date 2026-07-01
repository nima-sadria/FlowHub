from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthConfig:
    """Connector authentication configuration.

    auth_type values and their expected credentials keys:
      "basic"   - {"username": str, "password": str}
      "api_key" - {"key": str, "secret": str}
      "oauth2"  - {"access_token": str, "refresh_token": str, "expires_at": float}
      "none"    - credentials is empty
    """

    auth_type: str
    credentials: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.credentials.get(key, default)
