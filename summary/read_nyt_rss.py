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


def fetch_rss_feed(rss_url: str) -> feedparser.FeedParserDict:
    """
    获取RSS feed内容。

    Args:
        rss_url: RSS feed的URL

    Returns:
        feedparser.FeedParserDict: 解析后的RSS feed对象

    Raises:
        Exception: RSS获取或解析失败时抛出
    """
    try:
        logging.info(f"Fetching RSS feed from: {rss_url}")
        feed = feedparser.parse(rss_url)
        if feed.bozo:
            logging.warning(f"RSS feed parsing warning: {feed.bozo_exception}")
        logging.info(f"Successfully fetched {len(feed.entries)} entries from RSS feed")
        return feed
    except Exception as e:
        logging.error(f"Failed to fetch RSS feed from {rss_url}: {e}")
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
        resp = httpx.get(url, timeout=30.0)
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
                "你是一个专业的文章摘要助手。请用中文对以下文章进行总结，提取关键信息和主要观点。",
            ),
            ("user", "请总结以下文章：\n\n{content}"),
        ]
    )
    return prompt | llm | StrOutputParser()


def process_rss_articles(
    rss_url: str, chain: Runnable, output_file: str, hours: int = 24
) -> None:
    """
    处理RSS feed中所有符合时间范围的文章。

    Args:
        rss_url: RSS feed的URL
        chain: LangChain处理链
        output_file: 输出文件路径
        hours: 时间范围（小时），默认24小时

    Returns:
        None

    Raises:
        Exception: RSS获取或文章处理失败时抛出
    """
    # 获取RSS feed
    feed = fetch_rss_feed(rss_url)

    # 过滤24小时内的文章
    recent_entries = filter_recent_entries(feed.entries, hours)

    if not recent_entries:
        logging.info("No recent articles found in the RSS feed")
        return

    # 创建或清空输出文件，写入标题
    header = f"纽约时报中文网 - 最近{hours}小时新闻摘要\n"
    header += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    header += f"文章总数: {len(recent_entries)}\n"
    header += f"{'=' * 80}\n\n"
    write_to_file(header, output_file, mode="w")

    # 处理每篇文章
    success_count = 0
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

            success_count += 1
        except Exception as e:
            logging.error(f"Failed to process article '{entry['title']}': {e}")
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

    # 处理RSS文章
    try:
        process_rss_articles(args.rss_url, chain, args.output, args.hours)
    except Exception as e:
        logging.error(f"Failed to process RSS articles: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
