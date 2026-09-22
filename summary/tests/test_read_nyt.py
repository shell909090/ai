"""Tests for the single-article LiteLLM summary workflow."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from llm_config import SummaryClient, get_llm_extra_headers
from read_nyt import create_summarizer, main, process_article, read_article


class ReadNytTest(unittest.TestCase):
    def test_process_article_with_litellm(self) -> None:
        with (
            patch("llm_config.litellm.validate_environment") as validate,
            patch("llm_config.litellm.completion") as completion,
            patch("read_nyt.get_article") as fetch,
            patch("read_nyt.write_to_file") as write,
            patch("builtins.print") as output,
        ):
            validate.return_value = {"keys_in_environment": True}
            completion.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))]
            )
            fetch.return_value = {"title": "title", "content": "article"}
            summarizer = create_summarizer("openai/test")
            self.assertIsInstance(summarizer, SummaryClient)
            process_article("https://example.com/article", summarizer, "out.txt")
            validate.assert_called_once_with("openai/test")
            completion.assert_called_once_with(
                model="openai/test",
                messages=[
                    {"role": "system", "content": summarizer.system_prompt},
                    {"role": "user", "content": "请总结以下文章：\n\narticle"},
                ],
                temperature=0,
                extra_headers=get_llm_extra_headers(),
            )
            self.assertIn("400-500", summarizer.system_prompt)
            fetch.assert_called_once_with("https://example.com/article")
            rendered = output.call_args.args[0]
            self.assertIn("title", rendered)
            self.assertIn("summary", rendered)
            write.assert_called_once_with(rendered, "out.txt")

    def test_empty_article_skips_summary(self) -> None:
        summarizer = Mock(spec=SummaryClient)
        self.assertIsNone(read_article(summarizer, {"content": ""}))
        summarizer.summarize.assert_not_called()

    def test_summary_failure_propagates(self) -> None:
        summarizer = Mock(spec=SummaryClient)
        summarizer.summarize.side_effect = RuntimeError("completion failed")
        with self.assertRaisesRegex(RuntimeError, "completion failed"):
            read_article(summarizer, {"content": "article"})

    def test_cli_continues_after_article_failure(self) -> None:
        with (
            patch("sys.argv", ["read_nyt.py", "-m", "openai/test", "one", "two"]),
            patch("read_nyt.setup_logging"),
            patch("read_nyt.create_summarizer") as create,
            patch("read_nyt.process_article") as process,
        ):
            process.side_effect = [RuntimeError("failed"), None]
            main()
            create.assert_called_once_with("openai/test")
            self.assertEqual(process.call_count, 2)
            process.assert_any_call("one", create.return_value, None)
            process.assert_any_call("two", create.return_value, None)


if __name__ == "__main__":
    unittest.main()
