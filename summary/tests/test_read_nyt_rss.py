"""Tests for the NYT RSS summarizer."""

import unittest

from read_nyt_rss import strip_think_blocks


class StripThinkBlocksTest(unittest.TestCase):
    def test_removes_complete_think_block(self) -> None:
        text = "<think>internal reasoning\nwith details</think>\n最终摘要"

        self.assertEqual(strip_think_blocks(text), "最终摘要")

    def test_removes_multiple_case_insensitive_blocks(self) -> None:
        text = "前言<THINK type=\"reasoning\">secret</THINK>正文<think>x</think>"

        self.assertEqual(strip_think_blocks(text), "前言正文")

    def test_removes_unclosed_think_block(self) -> None:
        text = "最终摘要\n<think>unfinished reasoning"

        self.assertEqual(strip_think_blocks(text), "最终摘要")

    def test_removes_reasoning_before_orphaned_end_tag(self) -> None:
        text = "internal reasoning</think>\n最终摘要"

        self.assertEqual(strip_think_blocks(text), "最终摘要")

    def test_preserves_plain_summary(self) -> None:
        text = "第一段摘要。\n\n第二段摘要。"

        self.assertEqual(strip_think_blocks(text), text)


if __name__ == "__main__":
    unittest.main()
