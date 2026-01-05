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
import math
import argparse
from pathlib import Path
from PIL import Image

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper

from libs import upscale, save_image, resize_image, convert_to_jpg, calculate_generation_size, get_all_devices, read_img_from_byte


def proc_device(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, device: dict, input_dir: Path, convert_jpg: bool = False) -> None:
    """处理单个设备的所有图片"""
    device_id = device['device_id']
    device_width = device['width']
    device_height = device['height']

    # 计算生成尺寸
    gen_width, gen_height = calculate_generation_size(device_width, device_height)
    gen_pixels = gen_width * gen_height
    device_pixels = device_width * device_height

    # 查找匹配的文件
    pattern = f"*_{gen_width}x{gen_height}.png"
    print(f"处理设备：{device_id} ({device_width}x{device_height})，文件模式：{pattern}")
    matching_files = sorted(input_dir.glob(pattern))

    if not matching_files:
        print(f"  未找到匹配文件，跳过")
        return

    print(f"  找到 {len(matching_files)} 个文件")

    # 处理每个匹配的文件
    for input_file in matching_files:
        # 生成输出文件名（包含device_id）
        base_name = input_file.stem.split('_')[0]  # 提取 "000" 部分
        output_file = input_dir / f"{base_name}_{device_width}x{device_height}_{device_id}.png"

        # 检查是否已存在
        if output_file.exists():
            print(f"    跳过 {output_file.name}: 已存在")
            continue

        # 判断是upscale还是downscale
        if device_pixels > gen_pixels:
            # 需要upscale
            print(f"    Upscale {input_file.name} -> {output_file.name}")
            image_data = upscale(api, wf, str(input_file))
            img = read_img_from_byte(image_data)
            img_resized = img.resize((device_width, device_height), Image.Resampling.LANCZOS)
            img_resized.save(output_file)
            img.close()
        else:
            # 需要downscale
            print(f"    Downscale {input_file.name} -> {output_file.name}")
            resize_image(input_file, output_file, device_width, device_height)

        # 转换为JPG（如果需要）
        if convert_jpg:
            convert_to_jpg(output_file)


def main():
    parser = argparse.ArgumentParser(description='根据设备分辨率，使用upscale流程提升分辨率')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='upscale.json',
                        help='ComfyUI Workflow文件 (默认: upscale.json)')
    parser.add_argument('--input-dir', '-d',
                        help='输入目录 (批量模式，与--pixels-csv配合使用)')
    parser.add_argument('--pixels-csv', '-p',
                        help='像素分辨率CSV文件 (批量模式)')
    parser.add_argument('--upscale-by',
                        type=float,
                        default=2.0,
                        help='放大倍数 (默认: 2.0, 单文件模式)')
    parser.add_argument('--jpg', '-j',
                        action='store_true',
                        help='同时生成JPG格式')
    args = parser.parse_args()

    if not args.url:
        print("错误: 必须通过--url参数或COMFYUI_API_URL环境变量指定ComfyUI API URL", file=sys.stderr)
        sys.exit(1)

    # 批量模式
    if args.pixels_csv and args.input_dir:
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            print(f"错误: 输入目录不存在: {args.input_dir}", file=sys.stderr)
            sys.exit(1)

        # 初始化API (仅在需要upscale时使用)
        api = ComfyApiWrapper(args.url)
        wf = ComfyWorkflowWrapper(args.workflow)

        # 读取所有设备（不过滤，允许同一模式匹配多个设备）
        all_devices = get_all_devices(args.pixels_csv)
        print(f"批量模式: {len(all_devices)} 个设备\n")

        # 处理每个设备
        for device in all_devices:
            proc_device(api, wf, device, input_dir, args.jpg)

    else:
        print("错误: 必须指定 (--input 和 --output) 或 (--input-dir 和 --pixels-csv)", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
