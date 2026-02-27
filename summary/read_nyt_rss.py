#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@date: 2026-02-09
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import os
import sys
import logging
import argparse
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone

import httpx
import feedparser
from bs4 import BeautifulSoup
import litellm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable
from langchain_litellm import ChatLiteLLM

# HTTP 请求默认配置
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def setup_logging() -> None:
    """设置日志记录器为INFO级别输出到stderr"""
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def validate_api_key(model: str) -> None:
    """验证LiteLLM模型所需API密钥是否存在，缺失时抛出异常"""
    logging.info(f"Validating environment for model: {model}")
    validation_result = litellm.validate_environment(model)
    if validation_result["keys_in_environment"] is False:
        missing = validation_result["missing_keys"]
        raise EnvironmentError(f"Don't have necessary environment {model}: {missing}")
    logging.info(f"Environment validation passed for model: {model}")


def fetch_rss_feed(rss_url: str, timeout: float = 30.0) -> feedparser.FeedParserDict:
    """使用httpx带超时获取并解析RSS feed内容"""
    try:
        logging.info(f"Fetching RSS feed from: {rss_url} (timeout: {timeout}s)")
        # 使用 httpx 带超时获取内容
        response = httpx.get(rss_url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()

        # 使用 feedparser 解析内容
        feed = feedparser.parse(response.text)
        if feed.bozo:
            logging.warning(f"RSS feed parsing warning: {feed.bozo_exception}")
        logging.info(f"Successfully fetched {len(feed.entries)} entries from RSS feed")
        return feed
    except httpx.TimeoutException as e:
        logging.error(f"Timeout fetching RSS feed from {rss_url}: {e}")
        raise
    except httpx.HTTPError as e:
        logging.error(f"HTTP error fetching RSS feed from {rss_url}: {e}")
        raise
    except Exception as e:
        logging.error(f"Failed to parse RSS feed from {rss_url}: {e}")
        raise


def filter_recent_entries(
    entries: List[feedparser.FeedParserDict], hours: int = 24
) -> List[Dict[str, str]]:
    """过滤指定时间范围内的RSS条目并按时间升序排序（最老的在前）"""
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(hours=hours)
    recent_entries = []

    for entry in entries:
        try:
            # RSS feed可能使用不同的时间字段
            published_time = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_time = datetime(
                    *entry.published_parsed[:6], tzinfo=timezone.utc
                )
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published_time = datetime(
                    *entry.updated_parsed[:6], tzinfo=timezone.utc
                )

            link = entry.get("link", "").strip()
            if published_time and published_time >= cutoff_time and link:
                recent_entries.append(
                    {
                        "title": entry.get("title", "No title"),
                        "link": link,
                        "published": published_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "published_timestamp": published_time,  # 保存时间戳用于排序
                    }
                )
                logging.info(f"Found recent article: {entry.get('title', 'No title')}")
            elif published_time and published_time >= cutoff_time and not link:
                logging.warning(
                    f"Skipping entry without link: {entry.get('title', 'No title')}"
                )
        except Exception as e:
            logging.warning(f"Failed to parse entry timestamp: {e}")
            continue

    # 按时间升序排序（最老的在前）
    recent_entries.sort(key=lambda x: x["published_timestamp"])

    # 移除临时的 timestamp 字段
    for entry in recent_entries:
        del entry["published_timestamp"]

    logging.info(f"Filtered {len(recent_entries)} articles within last {hours} hours (sorted oldest first)")
    return recent_entries


def get_article(url: str) -> Dict[str, str]:
    """从NYT网站获取文章标题和正文内容"""
    try:
        logging.info(f"Fetching article from: {url}")
        resp = httpx.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        logging.error(f"Failed to fetch article from {url}: {e}")
        raise

    try:
        doc = BeautifulSoup(resp.text, "lxml")
        content = ""
        for p in doc.select("section.article-body div.article-paragraph"):
            content += p.get_text().strip() + "\n"

        header_elements = doc.select(
            "div.article-area article div.article-header header"
        )
        if not header_elements:
            logging.error(f"Cannot find article header in {url}")
            raise ValueError("Article header not found")

        title = header_elements[0].get_text().strip()
        logging.info(f"Successfully fetched article: {title}")
        return {"title": title, "content": content.strip()}
    except Exception as e:
        logging.error(f"Failed to parse article from {url}: {e}")
        raise


def read_article(chain: Runnable, article: Dict[str, str]) -> Optional[str]:
    """使用LLM生成文章摘要"""
    content = article.get("content", "")
    if not content:
        logging.warning("Article content is empty")
        return None

    try:
        logging.info("Generating summary with LLM")
        result = chain.invoke({"content": content})
        return result
    except Exception as e:
        logging.error(f"Failed to generate summary: {e}")
        raise


def format_output(
    article: Dict[str, str], published: Optional[str] = None, url: Optional[str] = None
) -> str:
    """格式化文章为可读文本（标题、时间、链接、摘要）"""
    output = []
    output.append(f"\n{'=' * 80}")
    output.append(f"标题: {article.get('title', 'N/A')}")
    if published:
        output.append(f"发布时间: {published}")
    if url:
        output.append(f"原始链接: {url}")
    output.append(f"{'=' * 80}\n")
    if article.get("summary"):
        output.append(article["summary"])
    else:
        output.append("无法生成摘要")
    output.append(f"\n{'=' * 80}\n")
    return "\n".join(output)


def write_to_file(content: str, filepath: str, mode: str = "a") -> None:
    """将内容写入文件（默认追加模式）"""
    try:
        with open(filepath, mode, encoding="utf-8") as f:
            f.write(content)
        logging.info(f"Output written to {filepath}")
    except IOError as e:
        logging.error(f"Failed to write to file {filepath}: {e}")
        raise


def escape_markdown(text: str) -> str:
    """转义Telegram Markdown特殊字符防止解析错误"""
    # 重要：反斜杠必须第一个转义，避免二次转义
    escape_chars = ["\\", "_", "*", "[", "]", "(", ")", "`"]
    for char in escape_chars:
        text = text.replace(char, "\\" + char)
    return text


def send_telegram_message(
    bot_token: str, chat_id: str, text: str, parse_mode: str = "Markdown"
) -> bool:
    """发送消息到Telegram，失败时返回False"""
    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": int(chat_id), "text": text, "parse_mode": parse_mode}

    try:
        response = httpx.post(api_url, json=payload, timeout=10.0)
        response.raise_for_status()
        logging.info(f"Telegram message sent successfully (length: {len(text)})")
        return True
    except httpx.HTTPError as e:
        logging.error(f"Failed to send Telegram message: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error sending Telegram message: {e}")
        return False


def format_article_for_telegram(
    article: Dict[str, str], published: str, url: str
) -> str:
    """格式化文章为Telegram Markdown格式并转义特殊字符"""
    title = article.get("title", "无标题")
    summary = article.get("summary", "无摘要")

    # 转义标题和摘要中的 Markdown 特殊字符
    title_escaped = escape_markdown(title)
    summary_escaped = escape_markdown(summary)
    published_escaped = escape_markdown(published)

    # URL 不需要转义（在链接语法的括号内）
    message = f"📌 *{title_escaped}*\n"
    message += f"🕐 {published_escaped}\n"
    message += f"🔗 [阅读原文]({url})\n\n"
    message += summary_escaped

    return message


def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """智能分割长消息为多个片段（优先在段落边界分割）"""
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # 尝试在段落边界分割（双换行）
        split_pos = remaining.rfind("\n\n", 0, max_length)
        if split_pos == -1:
            # 尝试在单换行分割
            split_pos = remaining.rfind("\n", 0, max_length)
        if split_pos == -1:
            # 尝试在空格分割
            split_pos = remaining.rfind(" ", 0, max_length)
        if split_pos == -1:
            # 强制截断
            split_pos = max_length

        chunks.append(remaining[:split_pos].strip())
        remaining = remaining[split_pos:].strip()

    return chunks


def send_article_to_telegram(
    bot_token: str,
    chat_id: str,
    article: Dict[str, str],
    published: str,
    url: str,
) -> bool:
    """发送单篇文章到Telegram并自动分段（超长时分多条）"""
    # 预留空间给分页标记（最长约 30-40 字符），使用 3996 而不是 4096
    TELEGRAM_MAX_LENGTH = 4096
    PAGINATION_MARKER_RESERVE = 100  # 预留空间给分页标记
    max_chunk_size = TELEGRAM_MAX_LENGTH - PAGINATION_MARKER_RESERVE

    message = format_article_for_telegram(article, published, url)
    chunks = split_long_message(message, max_length=max_chunk_size)

    if len(chunks) > 1:
        logging.info(f"Article too long, splitting into {len(chunks)} parts")

    success = True
    for idx, chunk in enumerate(chunks, 1):
        if len(chunks) > 1:
            # 多段消息时添加页码标记
            if idx == 1:
                chunk_with_marker = chunk + f"\n\n_（续 {idx}/{len(chunks)}）_"
            elif idx == len(chunks):
                chunk_with_marker = f"_（{idx}/{len(chunks)}）_\n\n" + chunk
            else:
                chunk_with_marker = (
                    f"_（{idx}/{len(chunks)}）_\n\n" + chunk + "\n\n_（续）_"
                )
        else:
            chunk_with_marker = chunk

        # 最后的安全检查：确保添加标记后不超过限制
        if len(chunk_with_marker) > TELEGRAM_MAX_LENGTH:
            logging.warning(
                f"Chunk with marker exceeds limit: {len(chunk_with_marker)} > {TELEGRAM_MAX_LENGTH}, truncating"
            )
            chunk_with_marker = (
                chunk_with_marker[: TELEGRAM_MAX_LENGTH - 20] + "\n\n_（截断）_"
            )

        if not send_telegram_message(bot_token, chat_id, chunk_with_marker):
            success = False
            # 继续尝试发送剩余部分，不中断

    return success


def create_chain(model: str) -> Runnable:
    """创建LangChain处理链（验证API密钥 + 配置LLM和prompt）"""
    logging.info(f"Creating chain with model: {model}")

    # 验证环境变量
    validate_api_key(model)

    llm = ChatLiteLLM(model=model, temperature=0)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """你是一位善于深度解读新闻的分析师。请为读者提供完整、自足的摘要，让读者无需阅读原文即可充分理解事件全貌。

摘要要求：
1. 开篇：用1-2句话清晰说明"发生了什么事"
2. 展开：详细阐述关键事实、背景、相关人物和具体细节
3. 深化：解释事件的意义、影响或争议点
4. 补充：如有重要数据、引言或相关信息，务必包含

风格要求：
- 信息完整，确保读者看完摘要后无需查看原文
- 保留重要细节和具体事例，避免空泛概括
- 语言客观但生动，准确传达原文核心内容和语气
- 长度约400-500字（可根据原文复杂度适当调整）

记住：读者依赖这份摘要来替代原文，不要过度精简。""",
            ),
            ("user", "请总结以下文章：\n\n{content}"),
        ]
    )
    return prompt | llm | StrOutputParser()


def process_rss_articles(
    rss_url: str,
    chain: Runnable,
    output_file: str,
    hours: int = 24,
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> None:
    """处理RSS feed中所有符合时间范围的文章（获取、摘要、保存、推送Telegram）"""
    # 解析 Telegram Chat IDs（支持多个，逗号分隔）
    telegram_chat_ids = []
    if telegram_bot_token and telegram_chat_id:
        telegram_chat_ids = [
            chat_id.strip()
            for chat_id in telegram_chat_id.split(",")
            if chat_id.strip()
        ]

    telegram_enabled = bool(telegram_bot_token and telegram_chat_ids)
    if telegram_enabled:
        logging.info(
            f"Telegram notification enabled for {len(telegram_chat_ids)} chat(s)"
        )
    else:
        logging.info("Telegram notification disabled (missing token or chat_id)")

    # 获取RSS feed
    feed = fetch_rss_feed(rss_url)

    # 过滤24小时内的文章
    recent_entries = filter_recent_entries(feed.entries, hours)

    if not recent_entries:
        logging.info("No recent articles found in the RSS feed")
        if telegram_enabled:
            no_news_msg = f"📰 纽约时报中文网 - 最近{hours}小时无新闻"
            for chat_id in telegram_chat_ids:
                send_telegram_message(telegram_bot_token, chat_id, no_news_msg)
        return

    # 发送开始消息到 Telegram
    if telegram_enabled:
        start_msg = f"📰 *纽约时报中文网 - 最近{hours}小时新闻摘要*\n\n"
        start_msg += f"🕒 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        start_msg += f"📊 文章总数: {len(recent_entries)}\n"
        start_msg += "\n开始处理..."
        for chat_id in telegram_chat_ids:
            send_telegram_message(telegram_bot_token, chat_id, start_msg)

    # 创建或清空输出文件，写入标题
    header = f"纽约时报中文网 - 最近{hours}小时新闻摘要\n"
    header += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    header += f"文章总数: {len(recent_entries)}\n"
    header += f"{'=' * 80}\n\n"
    write_to_file(header, output_file, mode="w")

    # 处理每篇文章
    success_count = 0
    failed_articles = []  # 记录失败的文章
    for idx, entry in enumerate(recent_entries, 1):
        try:
            logging.info(
                f"Processing article {idx}/{len(recent_entries)}: {entry['title']}"
            )

            # 获取文章内容
            article = get_article(entry["link"])

            # 生成摘要
            article["summary"] = read_article(chain, article)

            # 格式化输出
            output_text = format_output(article, entry["published"], entry["link"])

            # 写入文件
            write_to_file(output_text, output_file)

            # 同时输出到控制台
            print(output_text)

            # 发送到 Telegram
            if telegram_enabled:
                for chat_id in telegram_chat_ids:
                    send_article_to_telegram(
                        telegram_bot_token,
                        chat_id,
                        article,
                        entry["published"],
                        entry["link"],
                    )

            success_count += 1
        except Exception as e:
            logging.error(f"Failed to process article '{entry['title']}': {e}")
            failed_articles.append({"title": entry["title"], "error": str(e)})
            # 写入错误信息到输出文件
            error_msg = f"\n{'=' * 80}\n标题: {entry['title']}\n处理失败: {str(e)}\n{'=' * 80}\n\n"
            write_to_file(error_msg, output_file)
            continue

    # 写入统计信息
    summary = f"\n\n{'=' * 80}\n"
    summary += f"处理完成！成功: {success_count}/{len(recent_entries)}\n"
    summary += f"{'=' * 80}\n"
    write_to_file(summary, output_file)
    print(summary)

    # 只在有失败时发送 Telegram 通知
    if telegram_enabled and failed_articles:
        failure_msg = "⚠️ *处理完成 - 有失败项*\n\n"
        failure_msg += f"📊 成功: {success_count}/{len(recent_entries)} 篇\n"
        failure_msg += f"❌ 失败: {len(failed_articles)} 篇\n\n"
        failure_msg += "*失败详情：*\n"
        for idx, failed in enumerate(failed_articles, 1):
            # 截断过长的标题和错误信息
            title = (
                failed["title"][:50] + "..."
                if len(failed["title"]) > 50
                else failed["title"]
            )
            error = (
                failed["error"][:100] + "..."
                if len(failed["error"]) > 100
                else failed["error"]
            )
            # 转义 Markdown 特殊字符，避免发送失败
            title_escaped = escape_markdown(title)
            error_escaped = escape_markdown(error)
            failure_msg += f"{idx}. {title_escaped}\n   错误: {error_escaped}\n\n"
        for chat_id in telegram_chat_ids:
            send_telegram_message(telegram_bot_token, chat_id, failure_msg)


def main() -> None:
    """主函数，处理命令行参数并执行RSS新闻摘要任务"""
    parser = argparse.ArgumentParser(
        description="自动读取纽约时报中文网RSS，提取24小时内新闻并生成中文摘要"
    )
    parser.add_argument(
        "--model",
        "-m",
        default=os.getenv("MODEL", "groq/llama-3.3-70b-versatile"),
        help="LLM模型名称，默认从环境变量MODEL读取或使用groq/llama-3.3-70b-versatile",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="nyt_summary.txt",
        help="输出文件路径，默认为 nyt_summary.txt",
    )
    parser.add_argument(
        "--hours", type=int, default=24, help="时间范围（小时），默认24小时"
    )
    parser.add_argument(
        "--rss-url",
        type=str,
        default="https://cn.nytimes.com/rss/",
        help="RSS feed URL，默认为纽约时报中文网RSS",
    )
    args = parser.parse_args()

    setup_logging()

    # 创建处理链
    chain = create_chain(args.model)

    # 读取 Telegram 配置（从环境变量）
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_bot_token and telegram_chat_id:
        logging.info("Telegram configuration found in environment variables")
    else:
        logging.info("Telegram configuration not found, notifications will be disabled")

    # 处理RSS文章
    try:
        process_rss_articles(
            args.rss_url,
            chain,
            args.output,
            args.hours,
            telegram_bot_token,
            telegram_chat_id,
        )
    except Exception as e:
        logging.error(f"Failed to process RSS articles: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
