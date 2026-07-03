"""FlowHub - CLI API client.

HTTP client to the running FLOWHUB application. Used by operational CLI
commands (connected mode). Reads the JWT token from the local session store.

Implementation begins in B4.
"""


class FLOWHUBAPIClient:
    """HTTP client for communicating with the running FLOWHUB application.

    Implementation begins in B4.
    """

    def get(self, path: str, **params: object) -> dict:
        """Authenticated GET request to the running application.

        Implementation begins in B4.
        """
        raise NotImplementedError("Implementation begins in B4.")

    def post(self, path: str, body: dict) -> dict:
        """Authenticated POST request to the running application.

        Implementation begins in B4.
        """
        raise NotImplementedError("Implementation begins in B4.")

    def delete(self, path: str) -> dict:
        """Authenticated DELETE request to the running application.

        Implementation begins in B4.
        """
        raise NotImplementedError("Implementation begins in B4.")
