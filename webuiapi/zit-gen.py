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
import argparse
from pathlib import Path

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper


def generate_image(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes:
    # 设置提示词和随机种子
    wf.set_node_param("CLIP文本编码", "text", prompt)
    wf.set_node_param("K采样器", "seed", seed)

    # 设置图像尺寸
    wf.set_node_param("空Latent图像（SD3）", "width", width)
    wf.set_node_param("空Latent图像（SD3）", "height", height)

    # 生成图片
    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))


def save_image(image_data: bytes, output_filepath: Path) -> None:
    output_file_png = Path(output_filepath).with_suffix('.png')
    with open(output_file_png, "wb") as f:
        f.write(image_data)
    print(f"已保存PNG: {output_file_png}")


def main():
    parser = argparse.ArgumentParser(description='使用z-image-turbo流程生成图片')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='z_image_turbo.json',
                        help='ComfyUI Workflow文件 (默认: z_image_turbo.json)')
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
        print("错误: 必须通过--url参数或COMFYUI_API_URL环境变量指定ComfyUI API URL", file=sys.stderr)
        sys.exit(1)

    # 检查输出目录
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        # 检查是否有png或jpg文件
        existing_images = list(output_dir.glob('*.png')) + list(output_dir.glob('*.jpg'))
        if existing_images:
            print(f"错误: 输出目录 {args.output_dir} 已包含图片文件，停止执行", file=sys.stderr)
            sys.exit(1)
    else:
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
            image_data = generate_image(api, wf, prompt, seed, args.width, args.height)

            # 保存PNG文件
            output_filepath = output_dir / f"{counter:03d}.png"
            save_image(image_data, output_filepath)

            counter += 1


if __name__ == '__main__':
    main()
