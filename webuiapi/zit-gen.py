#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
'''
import os
import sys
import random
import logging
import argparse
from pathlib import Path

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper

from libs import zit_generate_image, save_image


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='使用z-image-turbo流程生成图片')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='z-image-turbo.json',
                        help='ComfyUI Workflow文件 (默认: z-image-turbo.json)')
    parser.add_argument('--theme', '-t',
                        required=True,
                        help='主题文件路径')
    parser.add_argument('--variations', '-v',
                        required=True,
                        help='变奏文件路径 (每行一个变奏)')
    parser.add_argument('--output-dir', '-o',
                        required=True,
                        help='输出目录')
    parser.add_argument('--width',
                        type=int,
                        default=1024,
                        help='图像宽度 (默认: 1024)')
    parser.add_argument('--height',
                        type=int,
                        default=1024,
                        help='图像高度 (默认: 1024)')
    args = parser.parse_args()

    if not args.url:
        logging.error("Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable")
        sys.exit(1)

    # 检查输出目录
    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    # 读取主题
    with open(args.theme, 'r', encoding='utf-8') as f:
        theme = f.read().strip()

    # 初始化ComfyUI API和Workflow
    api = ComfyApiWrapper(args.url)
    wf = ComfyWorkflowWrapper(args.workflow)

    # 读取变奏并生成图片
    counter = 0
    with open(args.variations, 'r', encoding='utf-8') as fi:
        for line in fi:
            v = line.strip()
            if not v:
                continue

            prompt = f"{theme}\n{v}"
            seed = random.randint(2**20, 2**64)

            # 检查目标文件是否已存在
            output_filepath = output_dir / f"{counter:03d}_{args.width}x{args.height}.png"
            if output_filepath.exists():
                logging.info(f"Skipping {output_filepath.name}: file already exists")
                counter += 1
                continue

            image_data = zit_generate_image(api, wf, prompt, seed, args.width, args.height)

            # 保存PNG文件
            save_image(image_data, output_filepath)

            counter += 1


if __name__ == '__main__':
    main()
