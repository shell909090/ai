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
    """
    设置日志记录器，配置输出格式和日志级别。

    从环境变量 LOG_LEVEL 读取日志级别，默认为 INFO。
    日志输出到 stderr，格式包含时间戳、级别和消息内容。

    Args:
        无

    Returns:
        None

    Raises:
        无
    """
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def validate_api_key(model: str) -> None:
    """
    验证所需的API密钥是否已设置。

    使用 LiteLLM 的 validate_environment 函数检查模型所需的环境变量是否正确配置。
    如果缺少必需的API密钥，则抛出异常。

    Args:
        model: 模型名称，遵循LiteLLM格式（如 'groq/llama-3.3-70b-versatile'）

    Returns:
        None

    Raises:
        Exception: 当环境变量验证失败时抛出（如缺少API密钥）
    """
    logging.info(f"Validating environment for model: {model}")
    validation_result = litellm.validate_environment(model)
    if validation_result["keys_in_environment"] is False:
        missing = validation_result["missing_keys"]
        raise EnvironmentError(f"Don't have necessary environment {model}: {missing}")
    logging.info(f"Environment validation passed for model: {model}")


def fetch_rss_feed(rss_url: str, timeout: float = 30.0) -> feedparser.FeedParserDict:
    """
    获取RSS feed内容。

    使用 httpx 带超时地获取内容，防止挂起。

    Args:
        rss_url: RSS feed的URL
        timeout: 超时时间（秒），默认30秒

    Returns:
        feedparser.FeedParserDict: 解析后的RSS feed对象

    Raises:
        httpx.HTTPError: HTTP请求失败时抛出
        Exception: RSS解析失败时抛出
    """
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
    """
    过滤指定时间范围内的RSS条目。

    Args:
        entries: RSS feed条目列表
        hours: 时间范围（小时），默认24小时

    Returns:
        List[Dict[str, str]]: 过滤后的条目列表，每个条目包含title和link

    Raises:
        无
    """
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

            if published_time and published_time >= cutoff_time:
                recent_entries.append(
                    {
                        "title": entry.get("title", "No title"),
                        "link": entry.get("link", ""),
                        "published": published_time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                logging.info(f"Found recent article: {entry.get('title', 'No title')}")
        except Exception as e:
            logging.warning(f"Failed to parse entry timestamp: {e}")
            continue

    logging.info(f"Filtered {len(recent_entries)} articles within last {hours} hours")
    return recent_entries


def get_article(url: str) -> Dict[str, str]:
    """
    从New York Times网站获取文章内容。

    通过HTTP请求获取页面，解析HTML提取标题和正文内容。

    Args:
        url: 文章的完整URL

    Returns:
        Dict[str, str]: 包含两个键的字典
            - title: 文章标题
            - content: 文章正文内容（所有段落拼接）

    Raises:
        httpx.HTTPError: HTTP请求失败时抛出
        IndexError: 无法找到文章标题元素时抛出
        Exception: 其他解析错误
    """
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
    """
    使用LangChain处理文章内容，生成摘要。

    通过LLM处理文章正文，生成中文摘要，提取关键信息和主要观点。

    Args:
        chain: 配置好的LangChain处理链（prompt | llm | parser）
        article: 包含文章信息的字典，必须包含 'content' 键

    Returns:
        Optional[str]: 生成的摘要文本，如果内容为空则返回 None

    Raises:
        Exception: LLM调用失败时可能抛出异常
    """
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
    """
    格式化文章输出。

    将文章标题、发布时间、原始链接和摘要格式化为可读的文本格式。

    Args:
        article: 包含 'title' 和 'summary' 键的字典
        published: 可选的发布时间字符串
        url: 可选的原始文章链接

    Returns:
        str: 格式化后的输出文本

    Raises:
        无
    """
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
    """
    将内容写入到指定文件。

    Args:
        content: 要写入的内容
        filepath: 目标文件路径
        mode: 写入模式，默认为追加模式 'a'

    Returns:
        None

    Raises:
        IOError: 文件写入失败时抛出
    """
    try:
        with open(filepath, mode, encoding="utf-8") as f:
            f.write(content)
        logging.info(f"Output written to {filepath}")
    except IOError as e:
        logging.error(f"Failed to write to file {filepath}: {e}")
        raise


def escape_markdown(text: str) -> str:
    """
    转义 Telegram Markdown 特殊字符。

    Args:
        text: 要转义的文本

    Returns:
        str: 转义后的文本

    Raises:
        无
    """
    # Telegram Markdown 需要转义的字符
    escape_chars = ["_", "*", "[", "`", "\\"]
    for char in escape_chars:
        text = text.replace(char, "\\" + char)
    return text


def send_telegram_message(
    bot_token: str, chat_id: str, text: str, parse_mode: str = "Markdown"
) -> bool:
    """
    发送消息到 Telegram。

    Args:
        bot_token: Telegram Bot Token
        chat_id: 目标 Chat ID
        text: 消息内容
        parse_mode: 解析模式，默认为 Markdown

    Returns:
        bool: 发送成功返回 True，失败返回 False

    Raises:
        无（内部捕获异常）
    """
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
    """
    格式化文章为 Telegram Markdown 格式。

    正确转义 Markdown 特殊字符以防止解析错误和潜在的注入问题。

    Args:
        article: 包含 'title' 和 'summary' 键的字典
        published: 发布时间字符串
        url: 原始文章链接

    Returns:
        str: 格式化后的 Markdown 文本

    Raises:
        无
    """
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
    """
    将长消息分割为多个片段，确保每个片段不超过最大长度。

    智能分割，优先在段落边界分割。

    Args:
        text: 要分割的文本
        max_length: 单条消息最大长度，默认 4096

    Returns:
        List[str]: 分割后的消息列表

    Raises:
        无
    """
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
    """
    发送单篇文章到 Telegram，如果消息过长则自动分段。

    Args:
        bot_token: Telegram Bot Token
        chat_id: 目标 Chat ID
        article: 包含 'title' 和 'summary' 键的字典
        published: 发布时间字符串
        url: 原始文章链接

    Returns:
        bool: 所有消息发送成功返回 True，否则返回 False

    Raises:
        无（内部捕获异常）
    """
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
    """
    创建LangChain处理链。

    使用LiteLLM创建LLM实例，配置prompt模板和输出解析器，构建完整的处理链。
    在创建LLM之前会使用 litellm.validate_environment 验证环境变量是否正确配置。

    Args:
        model: 模型名称，遵循LiteLLM格式（如 'groq/llama-3.3-70b-versatile'、'openai/gpt-4o-mini'）

    Returns:
        Runnable: 配置好的处理链（prompt | llm | parser）

    Raises:
        Exception: 环境变量验证失败时抛出（如缺少API密钥）
    """
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
    """
    处理RSS feed中所有符合时间范围的文章。

    Args:
        rss_url: RSS feed的URL
        chain: LangChain处理链
        output_file: 输出文件路径
        hours: 时间范围（小时），默认24小时
        telegram_bot_token: 可选的 Telegram Bot Token
        telegram_chat_id: 可选的 Telegram Chat ID，支持多个ID用逗号分隔

    Returns:
        None

    Raises:
        Exception: RSS获取或文章处理失败时抛出
    """
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
            failure_msg += f"{idx}. {title}\n   错误: {error}\n\n"
        for chat_id in telegram_chat_ids:
            send_telegram_message(telegram_bot_token, chat_id, failure_msg)


def main() -> None:
    """
    主函数，处理命令行参数并执行RSS新闻摘要任务。

    从命令行读取参数，配置LLM和处理链，获取RSS feed并处理所有符合时间范围的文章。

    注意：使用前必须设置相应的API密钥环境变量（如GROQ_API_KEY、OPENAI_API_KEY等），
    程序会在启动时使用 litellm.validate_environment 验证环境变量，如果缺失会直接抛出异常。

    Args:
        无（从命令行读取）

    Returns:
        None

    Raises:
        Exception: 环境变量验证失败时抛出（如缺少API密钥）
        Exception: RSS获取或文章处理过程中的各种异常
    """
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
