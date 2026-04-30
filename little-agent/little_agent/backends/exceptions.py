"""Backend exceptions."""


class BackendTimeoutError(Exception):
    """Raised when a backend API call exceeds the configured timeout."""
