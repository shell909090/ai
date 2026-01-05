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
from os import path

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper


def outpaint(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, image_filepath: str, left: int, top: int, right: int, bottom: int) -> bytes:
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt['subfolder'], rslt['name'])
    print(f'server side filepath: {server_filepath}')

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("外补画板", "left", left)
    wf.set_node_param("外补画板", "top", top)
    wf.set_node_param("外补画板", "right", right)
    wf.set_node_param("外补画板", "bottom", bottom)

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
    parser = argparse.ArgumentParser(description='使用sdxl-outpaint扩图')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='sdxl-outpaint.json',
                        help='ComfyUI Workflow文件 (默认: sdxl-outpaint.json)')
    parser.add_argument('--input', '-i',
                        required=True,
                        help='输入图像文件路径')
    parser.add_argument('--output', '-o',
                        required=True,
                        help='输出图像文件路径')
    parser.add_argument('--left',
                        type=int,
                        default=0,
                        help='左侧扩展像素 (默认: 0)')
    parser.add_argument('--top',
                        type=int,
                        default=0,
                        help='顶部扩展像素 (默认: 0)')
    parser.add_argument('--right',
                        type=int,
                        default=0,
                        help='右侧扩展像素 (默认: 0)')
    parser.add_argument('--bottom',
                        type=int,
                        default=0,
                        help='底部扩展像素 (默认: 0)')
    args = parser.parse_args()

    if not args.url:
        print("错误: 必须通过--url参数或COMFYUI_API_URL环境变量指定ComfyUI API URL", file=sys.stderr)
        sys.exit(1)

    # 初始化ComfyUI API和Workflow
    api = ComfyApiWrapper(args.url)
    wf = ComfyWorkflowWrapper(args.workflow)

    # 生成图片
    image_data = outpaint(api, wf, args.input, args.left, args.top, args.right, args.bottom)

    # 保存PNG文件
    save_image(image_data, Path(args.output))


if __name__ == '__main__':
    main()
