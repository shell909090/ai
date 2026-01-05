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
from PIL import Image
from io import BytesIO
from os import path

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper


def generate_image(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, image_filepath: str, upscale_by: float) -> bytes:
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt['subfolder'], rslt['name'])
    print(f'server side filepath: {server_filepath}')

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("Ultimate SD Upscale", "upscale_by", upscale_by)

    # 生成图片
    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))


def save_image(image_data: bytes, output_filepath: Path) -> None:
    output_file_png = Path(output_filepath).with_suffix('.png')
    with open(output_file_png, "wb") as f:
        f.write(image_data)
    print(f"已保存PNG: {output_file_png}")


def convert_to_jpg(image_data: bytes, output_filepath: Path) -> None:
    img = Image.open(BytesIO(image_data))
    if img.mode in ('RGBA', 'LA', 'P'):
        # 转换为RGB模式（JPG不支持透明通道）
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = rgb_img
    img.save(output_filepath, 'JPEG', quality=95)


def main():
    parser = argparse.ArgumentParser(description='使用ultimate-sd-upscale流程提升分辨率')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='ultimate-sd-upscale.json',
                        help='ComfyUI Workflow文件 (默认: ultimate-sd-upscale.json)')
    parser.add_argument('--input', '-i',
                        required=True,
                        help='输入图像文件路径')
    parser.add_argument('--output', '-o',
                        required=True,
                        help='输出图像文件路径')
    parser.add_argument('--upscale-by',
                        type=float,
                        default=2.0,
                        help='放大倍数 (默认: 2.0)')
    parser.add_argument('--jpg', '-j',
                        action='store_true',
                        help='同时生成JPG格式')
    args = parser.parse_args()

    if not args.url:
        print("错误: 必须通过--url参数或COMFYUI_API_URL环境变量指定ComfyUI API URL", file=sys.stderr)
        sys.exit(1)

    # 初始化ComfyUI API和Workflow
    api = ComfyApiWrapper(args.url)
    wf = ComfyWorkflowWrapper(args.workflow)

    # 生成图片
    image_data = generate_image(api, wf, args.input, args.upscale_by)

    # 保存PNG文件
    save_image(image_data, Path(args.output))

    # 转换为JPG（如果需要）
    if args.jpg:
        output_file_jpg = Path(args.output).with_suffix('.jpg')
        convert_to_jpg(image_data, output_file_jpg)
        print(f"已保存JPG: {output_file_jpg}")


if __name__ == '__main__':
    main()
