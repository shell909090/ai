"""Shared LLM request configuration."""

from uuid import uuid4


OPENCODE_SESSION_ID = str(uuid4())


def get_llm_extra_headers() -> dict[str, str]:
    """Return headers shared by LLM requests in the current process."""
    return {"x-opencode-session": OPENCODE_SESSION_ID}
