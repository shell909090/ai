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

import httpx
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


def setup_logging():
    """
    设置日志记录器。
    """
    logger = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))


def create_llm(model):
    """
    根据环境变量和模型名称创建相应的LLM实例。
    决策次序：
    1. 有GEMINI_API_KEY或GOOGLE_API_KEY -> 使用Google Gemini AI
    2. 有OPENAI_API_KEY -> 使用OpenAI
    """
    gemini_key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')

    if gemini_key:
        kwargs = {'model': model, 'temperature': 0}
        if base_url := os.getenv('GEMINI_BASE_URL'):
            kwargs['base_url'] = base_url
        return ChatGoogleGenerativeAI(**kwargs)
    elif openai_key:
        kwargs = {'model': model, 'temperature': 0}
        if base_url := os.getenv('OPENAI_BASE_URL'):
            kwargs['base_url'] = base_url
        return ChatOpenAI(**kwargs)
    else:
        raise ValueError('请设置 GEMINI_API_KEY/GOOGLE_API_KEY 或 OPENAI_API_KEY 环境变量')


def get_article(u):
    resp = httpx.get(u)
    resp.raise_for_status()
    doc = BeautifulSoup(resp.text, 'lxml')
    content = ''
    for p in doc.select('section.article-body div.article-paragraph'):
        content += p.get_text().strip()
    h = doc.select('div.article-area article div.article-header header')[0]
    return {'title': h.get_text().strip(), 'content': content}


def read_article(chain, article):
    """
    使用LangChain处理文章内容，生成摘要。
    """
    content = article.get('content', '')
    if not content:
        logging.warning('Article content is empty')
        return None

    result = chain.invoke({'content': content})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', '-m', default=os.getenv('MODEL', 'gpt-4o-mini'), help='model')
    parser.add_argument('--output', '-o', type=str, help='append output to file')
    parser.add_argument('rest', nargs='*', type=str)
    args = parser.parse_args()

    setup_logging()

    # 创建LangChain链
    llm = create_llm(args.model)

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个专业的文章摘要助手。请用中文对以下文章进行总结，提取关键信息和主要观点。"),
        ("user", "请总结以下文章：\n\n{content}")
    ])

    chain = prompt | llm | StrOutputParser()

    for u in args.rest:
        article = get_article(u)
        article['summary'] = read_article(chain, article)

        # Format output
        output = []
        output.append(f"\n{'='*80}")
        output.append(f"标题: {article.get('title', 'N/A')}")
        output.append(f"{'='*80}\n")
        if article.get('summary'):
            output.append(article['summary'])
        else:
            output.append("无法生成摘要")
        output.append(f"\n{'='*80}\n")

        output_text = '\n'.join(output)

        # Print to console
        print(output_text)

        # Append to file if specified
        if args.output:
            with open(args.output, 'a', encoding='utf-8') as f:
                f.write(output_text)


if __name__ == '__main__':
    main()
