"""Backend exceptions."""


class BackendError(Exception):
    """Generic backend SDK error not otherwise classified."""


class BackendTimeoutError(Exception):
    """Raised when a backend API call exceeds the configured timeout."""


class BackendRateLimitError(BackendError):
    """Raised when the backend returns a rate-limit response."""


class ContextOverflowError(Exception):
    """Raised when the backend rejects a request: input exceeds the model's context window."""
