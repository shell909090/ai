"""Backend exceptions."""


class BackendTimeoutError(Exception):
    """Raised when a backend API call exceeds the configured timeout."""


class ContextOverflowError(Exception):
    """Raised when the backend rejects a request: input exceeds the model's context window."""
