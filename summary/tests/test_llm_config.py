"""Tests for shared LLM request configuration."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from llm_config import SummaryClient, get_llm_extra_headers


class LlmConfigTest(unittest.TestCase):
    def test_summary_request_and_revision_messages(self) -> None:
        revisions = [
            {"role": "assistant", "content": "draft"},
            {"role": "user", "content": "revise"},
        ]
        with (
            patch("llm_config.litellm.validate_environment") as validate,
            patch("llm_config.litellm.completion") as completion,
        ):
            validate.return_value = {"keys_in_environment": True}
            completion.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))]
            )
            client = SummaryClient("openai/test", "system prompt")
            for extra in (None, revisions):
                self.assertEqual(client.summarize("article", extra), "summary")
                completion.assert_called_with(
                    model="openai/test",
                    messages=[
                        {"role": "system", "content": "system prompt"},
                        {"role": "user", "content": "请总结以下文章：\n\narticle"},
                    ] + (extra or []),
                    temperature=0,
                    extra_headers=get_llm_extra_headers(),
                )
            validate.assert_called_once_with("openai/test")
        self.assertEqual(len(revisions), 2)

    def test_empty_and_invalid_output(self) -> None:
        with (
            patch("llm_config.litellm.validate_environment") as validate,
            patch("llm_config.litellm.completion") as completion,
        ):
            validate.return_value = {"keys_in_environment": True}
            client = SummaryClient("openai/test", "prompt")
            for content in (None, "", ["unexpected"]):
                with self.subTest(content=content):
                    completion.return_value = SimpleNamespace(
                        choices=[SimpleNamespace(
                            message=SimpleNamespace(content=content)
                        )]
                    )
                    if isinstance(content, list):
                        with self.assertRaises(TypeError):
                            client.summarize("article")
                    else:
                        self.assertEqual(client.summarize("article"), "")

    def test_validation_failure_prevents_completion(self) -> None:
        with (
            patch("llm_config.litellm.validate_environment") as validate,
            patch("llm_config.litellm.completion") as completion,
        ):
            validate.return_value = {
                "keys_in_environment": False,
                "missing_keys": ["OPENAI_API_KEY"],
            }
            with self.assertRaisesRegex(
                EnvironmentError,
                "Don't have necessary environment openai/test: .*OPENAI_API_KEY",
            ):
                SummaryClient("openai/test", "prompt")
            completion.assert_not_called()

    def test_opencode_session_is_stable_uuid_for_process(self) -> None:
        first = get_llm_extra_headers()
        second = get_llm_extra_headers()

        self.assertEqual(first, second)
        self.assertEqual(set(first), {"x-opencode-session"})
        self.assertEqual(str(UUID(first["x-opencode-session"])), first["x-opencode-session"])

    def test_returns_independent_header_dicts(self) -> None:
        first = get_llm_extra_headers()
        first["x-opencode-session"] = "changed"

        self.assertNotEqual(first, get_llm_extra_headers())


if __name__ == "__main__":
    unittest.main()
