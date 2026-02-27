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
from typing import Dict, Optional

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
    """设置日志记录器为INFO级别输出到stderr"""
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))


def validate_api_key(model: str) -> None:
    """验证LiteLLM模型所需API密钥是否存在，缺失时抛出异常"""
    logging.info(f"Validating environment for model: {model}")
    validation_result = litellm.validate_environment(model)
    if validation_result["keys_in_environment"] is False:
        missing = validation_result["missing_keys"]
        raise EnvironmentError(f"Don't have necessary environment {model}: {missing}")
    logging.info(f"Environment validation passed for model: {model}")


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
    """使用LLM生成文章摘要"""
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
    """格式化文章为可读文本（标题和摘要）"""
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
    """追加内容到文件"""
    try:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(content)
        logging.info(f"Output appended to {filepath}")
    except IOError as e:
        logging.error(f"Failed to write to file {filepath}: {e}")
        raise


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


def process_article(url: str, chain: Runnable, output_file: Optional[str]) -> None:
    """处理单篇文章的完整流程（获取、摘要、输出、保存）"""
    article = get_article(url)
    article['summary'] = read_article(chain, article)

    output_text = format_output(article)
    print(output_text)

    if output_file:
        write_to_file(output_text, output_file)


def main() -> None:
    """主函数，处理命令行参数并循环处理所有文章URL"""
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
