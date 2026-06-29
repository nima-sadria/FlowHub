"""FlowHub Beta — integration error types (BU5).

All external integration clients raise IntegrationError instead of leaking
httpx or stdlib exceptions into routers.  Routers map IntegrationError to
HTTP 502 Bad Gateway with the provider-prefixed message.
"""

from __future__ import annotations


class IntegrationError(Exception):
    """Raised by an integration client when an external service fails."""

    def __init__(
        self,
        provider: str,
        endpoint: str,
        message: str,
        status_code: int | None = None,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")

    @property
    def detail(self) -> str:
        """Human-readable error for API responses.  Never leaks raw internals."""
        return f"{self.provider}: {self.message}"
