"""Tests for shared LLM request configuration."""

import unittest
from uuid import UUID

from llm_config import get_llm_extra_headers


class LlmConfigTest(unittest.TestCase):
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
