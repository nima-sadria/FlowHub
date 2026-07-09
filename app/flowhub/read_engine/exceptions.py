"""Read engine exception types."""


class IncrementalReadUnsupported(RuntimeError):
    """Raised when a connector cannot safely perform an incremental read."""

    code = "incremental_read_unsupported"

    def __init__(self, message: str = "incremental_read_unsupported") -> None:
        super().__init__(message)
