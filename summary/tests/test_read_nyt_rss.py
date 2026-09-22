"""Tests for the NYT RSS summarizer."""

import unittest
from unittest.mock import Mock, call, patch

import litellm

from read_nyt_rss import (
    create_summarizer,
    process_rss_articles,
    read_article,
    strip_think_blocks,
)


class ProcessRssArticlesTest(unittest.TestCase):
    def setUp(self) -> None:
        """隔离网络、模型、文件和标准输出并准备文章数据。"""
        self.mocks: dict[str, Mock] = {}
        for name in (
            "load_seen_links_raw", "load_seen_links", "fetch_rss_feed",
            "filter_recent_entries", "get_article", "read_article",
            "write_to_file", "save_seen_links", "send_telegram_message",
            "send_article_to_telegram", "print",
        ):
            patcher = patch(f"read_nyt_rss.{name}")
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self.entries = [
            {"title": title, "link": f"https://example.com/{title}",
             "published": "2026-01-01 12:00:00"}
            for title in ("old", "first", "second", "third")
        ]
        self.raw = [{"link": self.entries[0]["link"], "sent_at": "original"}]
        self.mocks["load_seen_links_raw"].return_value = self.raw
        self.mocks["load_seen_links"].return_value = {self.entries[0]["link"]}
        self.mocks["filter_recent_entries"].return_value = self.entries
        self.mocks["get_article"].side_effect = lambda url: {
            "title": url.rsplit("/", 1)[-1], "content": "article text"
        }
        self.mocks["read_article"].return_value = "summary text"
        self.summarizer = Mock()

    def run_process(
        self, token: str | None = "token", chats: str | None = " 1, ,2 "
    ) -> None:
        """使用指定Telegram配置执行真实文章处理流程。"""
        process_rss_articles(
            "https://example.com/rss", self.summarizer, "output.txt",
            hours=24, telegram_bot_token=token, telegram_chat_id=chats,
            seen_links_file="seen.json",
        )

    def test_no_recent_articles_only_notifies(self) -> None:
        self.mocks["filter_recent_entries"].return_value = []
        self.run_process()
        self.mocks["send_telegram_message"].assert_has_calls([
            call("token", "1", "📰 纽约时报中文网 - 最近24小时无新闻"),
            call("token", "2", "📰 纽约时报中文网 - 最近24小时无新闻"),
        ])
        self.assertEqual(self.mocks["send_telegram_message"].call_count, 2)
        self.mocks["get_article"].assert_not_called()
        self.mocks["write_to_file"].assert_not_called()
        self.mocks["save_seen_links"].assert_not_called()

    def test_all_seen_articles_skip_processing_and_state_save(self) -> None:
        self.mocks["filter_recent_entries"].return_value = self.entries[:1]
        self.run_process(token=None)
        self.mocks["get_article"].assert_not_called()
        self.mocks["write_to_file"].assert_not_called()
        self.mocks["save_seen_links"].assert_not_called()
        self.mocks["send_telegram_message"].assert_not_called()

    def test_success_preserves_order_output_and_seen_state(self) -> None:
        self.run_process()
        self.mocks["get_article"].assert_has_calls([
            call(entry["link"]) for entry in self.entries[1:]
        ])
        self.assertEqual(self.mocks["get_article"].call_count, 3)
        self.mocks["save_seen_links"].assert_called_once_with(
            "seen.json", {entry["link"] for entry in self.entries}, self.raw
        )
        writes = self.mocks["write_to_file"].call_args_list
        self.assertEqual(writes[0].kwargs, {"mode": "w"})
        self.assertIn("文章总数: 3", writes[0].args[0])
        self.assertIn("summary text", writes[1].args[0])
        self.assertIn("成功: 3/3", writes[-1].args[0])
        self.assertEqual(len(writes), 5)
        self.assertEqual(self.mocks["send_article_to_telegram"].call_count, 6)
        self.assertEqual(self.mocks["send_telegram_message"].call_count, 2)
        self.mocks["filter_recent_entries"].assert_called_once_with(
            self.mocks["fetch_rss_feed"].return_value.entries, 24
        )

    def test_failure_continues_and_saves_only_successes(self) -> None:
        self.mocks["read_article"].side_effect = [
            "first summary", RuntimeError("model failed"), "third summary"
        ]
        with self.assertLogs(level="ERROR"):
            self.run_process()
        self.assertEqual(self.mocks["get_article"].call_count, 3)
        self.mocks["save_seen_links"].assert_called_once_with(
            "seen.json", {self.entries[i]["link"] for i in (0, 1, 3)}, self.raw
        )
        writes = self.mocks["write_to_file"].call_args_list
        self.assertIn("处理失败: model failed", writes[2].args[0])
        self.assertIn("成功: 2/3", writes[-1].args[0])
        notifications = self.mocks["send_telegram_message"].call_args_list
        self.assertEqual(len(notifications), 4)
        self.assertIn("成功: 2/3", notifications[2].args[2])
        self.assertIn("second", notifications[2].args[2])
        self.assertEqual(self.mocks["send_article_to_telegram"].call_count, 4)

    def test_incomplete_telegram_config_still_writes_and_saves(self) -> None:
        for token, chats in ((None, "1"), ("token", None), ("token", " , ")):
            with self.subTest(token=token, chats=chats):
                self.mocks["load_seen_links"].return_value = set()
                self.mocks["filter_recent_entries"].return_value = self.entries[:1]
                self.mocks["write_to_file"].reset_mock()
                self.mocks["save_seen_links"].reset_mock()
                self.run_process(token, chats)
                self.assertEqual(self.mocks["write_to_file"].call_count, 3)
                self.mocks["save_seen_links"].assert_called_once_with(
                    "seen.json", {self.entries[0]["link"]}, self.raw
                )
                self.mocks["send_telegram_message"].assert_not_called()
                self.mocks["send_article_to_telegram"].assert_not_called()

    def test_telegram_delivery_failure_keeps_successful_article_seen(self) -> None:
        self.mocks["send_article_to_telegram"].return_value = False
        self.run_process()
        self.mocks["save_seen_links"].assert_called_once_with(
            "seen.json", {entry["link"] for entry in self.entries}, self.raw
        )
        self.assertEqual(self.mocks["send_telegram_message"].call_count, 2)


class ReadArticleTest(unittest.TestCase):
    def test_does_not_rewrite_at_threshold(self) -> None:
        summarizer = Mock()
        summarizer.summarize.return_value = "摘" * 400

        self.assertEqual(read_article(summarizer, {"content": "原文"}), "摘" * 400)
        summarizer.summarize.assert_called_once_with("原文", None)

    def test_selects_shorter_nonempty_summary_with_one_rewrite(self) -> None:
        original = "摘" * 401
        for revised in ("新" * 250, "新" * 401, "新" * 500, "", "新" * 400):
            with self.subTest(length=len(revised)):
                summarizer = Mock()
                summarizer.summarize.side_effect = [original, revised]

                result = read_article(summarizer, {"content": "原文"})

                expected = revised if revised and len(revised) < len(original) else original
                self.assertEqual(result, expected)
                self.assertEqual(summarizer.summarize.call_count, 2)

    def test_rewrite_preserves_original_prompt_and_article(self) -> None:
        with (
            patch("llm_config.litellm.validate_environment", return_value={"keys_in_environment": True}),
            patch("llm_config.litellm.completion") as completion,
        ):
            completion.side_effect = [
                litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": text}}])
                for text in ("摘" * 401, "<think>分析</think>新摘要")
            ]
            summarizer = create_summarizer("test/model")
            result = read_article(summarizer, {"content": "原始文章{content}"})

        self.assertEqual(result, "新摘要")
        prompts = [call.kwargs["messages"] for call in completion.call_args_list]
        self.assertEqual([msg["role"] for msg in prompts[1]], ["system", "user", "assistant", "user"])
        self.assertEqual(prompts[1][:2], prompts[0])
        self.assertIn("原始文章{content}", prompts[1][1]["content"])
        self.assertEqual(prompts[1][2]["content"], "摘" * 401)
        self.assertIn("字数超过限制", prompts[1][3]["content"])
        self.assertIn("200-300", prompts[1][3]["content"])

    def test_thinking_does_not_count_toward_threshold(self) -> None:
        summarizer = Mock()
        summarizer.summarize.return_value = "<think>" + "思" * 500 + "</think>摘要"

        self.assertEqual(read_article(summarizer, {"content": "原文"}), "摘要")
        self.assertEqual(summarizer.summarize.call_count, 1)

    def test_keeps_original_when_rewrite_fails(self) -> None:
        summarizer = Mock()
        summarizer.summarize.side_effect = ["摘" * 401, RuntimeError("unavailable")]

        with self.assertLogs(level="WARNING"):
            result = read_article(summarizer, {"content": "原文"})

        self.assertEqual(result, "摘" * 401)

    @patch("read_nyt_rss.time.sleep")
    def test_rate_limit_retries_only_rewrite(self, sleep: Mock) -> None:
        summarizer = Mock()
        summarizer.summarize.side_effect = [
            "摘" * 401,
            litellm.RateLimitError("limited", llm_provider="test", model="test"),
            "新摘要",
        ]

        with self.assertLogs(level="WARNING"):
            result = read_article(summarizer, {"content": "原文"})

        self.assertEqual(result, "新摘要")
        self.assertEqual(summarizer.summarize.call_count, 3)
        self.assertEqual(summarizer.summarize.call_args_list[1], summarizer.summarize.call_args_list[2])
        sleep.assert_called_once_with(30)

    def test_empty_article_does_not_call_model(self) -> None:
        summarizer = Mock()
        with self.assertLogs(level="WARNING"):
            self.assertIsNone(read_article(summarizer, {"content": ""}))
        summarizer.summarize.assert_not_called()


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
