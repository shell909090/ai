"""HTTP boundary tests for the supported providers."""

import os
import unittest
from unittest.mock import patch

import httpx

import llm_transport
from llm_config import SummaryClient


class TransportTests(unittest.TestCase):
    def test_provider_requests(self) -> None:
        messages = [{"role": "system", "content": "system"}, {"role": "user", "content": "article"}]
        cases = [
            ("openai", "chat/completions", {"choices": [{"message": {"content": "summary"}}]}),
            ("groq", "chat/completions", {"choices": [{"message": {"content": "summary"}}]}),
            ("gemini", "chat/completions", {"choices": [{"message": {"content": "summary"}}]}),
            ("anthropic", "messages", {"content": [{"type": "text", "text": "summary"}]}),
            ("cohere", "chat", {"message": {"content": [{"type": "text", "text": "summary"}]}}),
        ]
        for provider, path, body in cases:
            with (
                self.subTest(provider=provider),
                patch.dict(
                    os.environ,
                    {
                        f"{provider.upper()}_API_KEY": "secret",
                        f"{provider.upper()}_API_BASE": "https://example.test/api/",
                    },
                    clear=True,
                ),
                patch("llm_transport.httpx.post") as post,
            ):
                post.return_value = httpx.Response(
                    200, json=body, request=httpx.Request("POST", "https://example.test")
                )
                result = llm_transport.completion(
                    f"{provider}/org/model", messages, 0, {"x-opencode-session": "session"}
                )
                self.assertEqual(result.choices[0].message.content, "summary")
                self.assertEqual(post.call_args.args[0], f"https://example.test/api/{path}")
                kwargs = post.call_args.kwargs
                self.assertEqual(kwargs["json"]["model"], "org/model")
                self.assertEqual(kwargs["headers"]["x-opencode-session"], "session")
                self.assertEqual(kwargs["timeout"], 60)
                if provider == "anthropic":
                    self.assertEqual(kwargs["json"]["system"], "system")
                    self.assertEqual(kwargs["json"]["messages"], messages[1:])
                    self.assertEqual(kwargs["headers"]["x-api-key"], "secret")
                else:
                    self.assertEqual(kwargs["json"]["messages"], messages)
                    self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")

    def test_http_errors(self) -> None:
        for status, error in [
            (429, llm_transport.RateLimitError),
            (401, httpx.HTTPStatusError),
            (500, httpx.HTTPStatusError),
        ]:
            with (
                self.subTest(status=status),
                patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
                patch("llm_transport.httpx.post") as post,
            ):
                post.return_value = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
                with self.assertRaises(error):
                    llm_transport.completion("openai/model", [], 0, {})

    def test_invalid_configuration_prevents_network(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch("llm_transport.httpx.post") as post:
            for model in ["", "model", "unknown/model", "openai/model"]:
                with self.subTest(model=model), self.assertRaises((ValueError, EnvironmentError)):
                    SummaryClient(model, "system")
            post.assert_not_called()

    def test_google_key_alias(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "secret"}, clear=True):
            self.assertTrue(llm_transport.validate_environment("gemini/model")["keys_in_environment"])
