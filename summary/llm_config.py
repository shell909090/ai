"""Shared LLM request configuration."""

import logging
from uuid import uuid4

import litellm


OPENCODE_SESSION_ID = str(uuid4())


def get_llm_extra_headers() -> dict[str, str]:
    """Return headers shared by LLM requests in the current process."""
    return {"x-opencode-session": OPENCODE_SESSION_ID}


class SummaryClient:
    """Generate summaries through LiteLLM with shared session headers."""

    def __init__(self, model: str, system_prompt: str) -> None:
        logging.info("Validating environment for model: %s", model)
        validation_result = litellm.validate_environment(model)
        if validation_result["keys_in_environment"] is False:
            missing = validation_result["missing_keys"]
            raise EnvironmentError(
                f"Don't have necessary environment {model}: {missing}"
            )
        logging.info("Environment validation passed for model: %s", model)
        self.model = model
        self.system_prompt = system_prompt

    def summarize(
        self,
        content: str,
        revision_messages: list[dict[str, str]] | None = None,
    ) -> str:
        """Summarize article content with optional revision conversation."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"请总结以下文章：\n\n{content}"},
        ]
        if revision_messages:
            messages.extend(revision_messages)
        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=0,
            extra_headers=get_llm_extra_headers(),
        )
        result = response.choices[0].message.content
        if result is None:
            return ""
        if not isinstance(result, str):
            raise TypeError("LLM message content must be a string or None")
        return result
