#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@date: 2025-09-16
@author: Shell.Xu
@copyright: 2025, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
'''
import os
import sys
import logging
import argparse
from typing import Dict, Optional, Any

import httpx
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
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))


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
        doc = BeautifulSoup(resp.text, 'lxml')
        content = ''
        for p in doc.select('section.article-body div.article-paragraph'):
            content += p.get_text().strip() + '\n'

        header_elements = doc.select('div.article-area article div.article-header header')
        if not header_elements:
            logging.error(f"Cannot find article header in {url}")
            raise ValueError("Article header not found")

        title = header_elements[0].get_text().strip()
        logging.info(f"Successfully fetched article: {title}")
        return {'title': title, 'content': content.strip()}
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
    content = article.get('content', '')
    if not content:
        logging.warning('Article content is empty')
        return None

    try:
        logging.info("Generating summary with LLM")
        result = chain.invoke({'content': content})
        return result
    except Exception as e:
        logging.error(f"Failed to generate summary: {e}")
        raise


def format_output(article: Dict[str, str]) -> str:
    """
    格式化文章输出。

    将文章标题和摘要格式化为可读的文本格式。

    Args:
        article: 包含 'title' 和 'summary' 键的字典

    Returns:
        str: 格式化后的输出文本

    Raises:
        无
    """
    output = []
    output.append(f"\n{'='*80}")
    output.append(f"标题: {article.get('title', 'N/A')}")
    output.append(f"{'='*80}\n")
    if article.get('summary'):
        output.append(article['summary'])
    else:
        output.append("无法生成摘要")
    output.append(f"\n{'='*80}\n")
    return '\n'.join(output)


def write_to_file(content: str, filepath: str) -> None:
    """
    将内容追加到指定文件。

    Args:
        content: 要写入的内容
        filepath: 目标文件路径

    Returns:
        None

    Raises:
        IOError: 文件写入失败时抛出
    """
    try:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Output appended to {filepath}")
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

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的文章摘要助手。请用中文对以下文章进行总结，提取关键信息和主要观点。"),
        ("user", "请总结以下文章：\n\n{content}")
    ])
    return prompt | llm | StrOutputParser()


def process_article(url: str, chain: Runnable, output_file: Optional[str]) -> None:
    """
    处理单篇文章的完整流程。

    获取文章、生成摘要、格式化输出并保存。

    Args:
        url: 文章URL
        chain: LangChain处理链
        output_file: 可选的输出文件路径

    Returns:
        None

    Raises:
        Exception: 文章获取或处理失败时抛出
    """
    article = get_article(url)
    article['summary'] = read_article(chain, article)

    output_text = format_output(article)
    print(output_text)

    if output_file:
        write_to_file(output_text, output_file)


def main() -> None:
    """
    主函数，处理命令行参数并执行文章摘要任务。

    从命令行读取参数，配置LLM和处理链，循环处理所有文章URL。

    注意：使用前必须设置相应的API密钥环境变量（如GROQ_API_KEY、OPENAI_API_KEY等），
    程序会在启动时使用 litellm.validate_environment 验证环境变量，如果缺失会直接抛出异常。

    Args:
        无（从命令行读取）

    Returns:
        None

    Raises:
        Exception: 环境变量验证失败时抛出（如缺少API密钥）
        Exception: 文章处理过程中的各种异常
    """
    parser = argparse.ArgumentParser(
        description='使用LLM自动阅读New York Times新闻并生成中文摘要'
    )
    parser.add_argument(
        '--model', '-m',
        default=os.getenv('MODEL', 'groq/llama-3.3-70b-versatile'),
        help='LLM模型名称，默认从环境变量MODEL读取或使用groq/llama-3.3-70b-versatile'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='输出文件路径，内容将追加到文件末尾'
    )
    parser.add_argument(
        'rest',
        nargs='*',
        type=str,
        help='要处理的文章URL列表'
    )
    args = parser.parse_args()

    setup_logging()

    chain = create_chain(args.model)

    for url in args.rest:
        try:
            process_article(url, chain, args.output)
        except Exception as e:
            logging.error(f"Failed to process article {url}: {e}")
            continue


if __name__ == '__main__':
    main()
