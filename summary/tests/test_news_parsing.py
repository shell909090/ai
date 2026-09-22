"""Check news parsing with the installed HTML and RSS dependencies."""

import unittest
from unittest.mock import Mock, patch

import read_nyt
import read_nyt_rss


class NewsParsingTest(unittest.TestCase):
    def test_article_parsing_in_both_entry_points(self) -> None:
        html = (
            '<div class="article-area"><article><div class="article-header">'
            '<header>Example title</header></div><section class="article-body">'
            '<div class="article-paragraph">First <b>paragraph</b>.</div>'
            '<div class="article-paragraph">Second paragraph.</div>'
            '</section></article></div>'
        )
        for module in (read_nyt, read_nyt_rss):
            with self.subTest(module=module.__name__):
                with patch.object(module.httpx, "get", return_value=Mock(text=html)):
                    article = module.get_article("https://example.com/article")
                self.assertEqual(article, {
                    "title": "Example title",
                    "content": "First paragraph.\nSecond paragraph.",
                })

    def test_rss_parser_preserves_article_metadata(self) -> None:
        xml = (
            '<?xml version="1.0"?><rss version="2.0"><channel>'
            '<title>News</title><link>https://example.com/</link><description>News</description>'
            '<item><title>Article &amp; update</title><link>https://example.com/article</link>'
            '<pubDate>Tue, 22 Sep 2026 01:00:00 GMT</pubDate></item></channel></rss>'
        )
        with patch("read_nyt_rss.httpx.get", return_value=Mock(text=xml)):
            feed = read_nyt_rss.fetch_rss_feed("https://example.com/rss")
        self.assertFalse(feed.bozo)
        self.assertEqual(len(feed.entries), 1)
        self.assertEqual(feed.entries[0].title, "Article & update")
        self.assertEqual(feed.entries[0].link, "https://example.com/article")
        self.assertEqual(feed.entries[0].published_parsed[:6], (2026, 9, 22, 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
