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
import csv
import math
import random
import argparse
from pathlib import Path
from os import path
from PIL import Image
from io import BytesIO

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper


def usdu(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, image_filepath: str, upscale_by: float) -> bytes:
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


def resize_image(input_filepath: Path, output_filepath: Path, target_width: int, target_height: int) -> None:
    """使用PIL调整图片尺寸"""
    img = Image.open(input_filepath)
    img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    img_resized.save(output_filepath, 'PNG')
    img.close()


def convert_to_jpg(png_filepath: Path, quality: int = 95) -> None:
    """将PNG转换为JPG"""
    jpg_filepath = png_filepath.with_suffix('.jpg')
    img = Image.open(png_filepath)

    # 如果图片有透明通道，转换为RGB
    if img.mode in ('RGBA', 'LA', 'P'):
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = rgb_img
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    img.save(jpg_filepath, 'JPEG', quality=quality)
    print(f"      已转换为JPG: {jpg_filepath.name}")


def calculate_generation_size(device_width: int, device_height: int, target_area: int = 1024 * 1024) -> tuple[int, int]:
    """计算生成图像尺寸 (与zit-gen.py相同的逻辑)"""
    aspect_ratio = device_width / device_height
    gen_width = int(math.sqrt(target_area * aspect_ratio))
    gen_height = int(math.sqrt(target_area / aspect_ratio))
    return gen_width, gen_height


def get_all_devices(pixels_csv: str) -> list[dict]:
    """读取pixels.csv中的所有设备"""
    devices = []
    with open(pixels_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            devices.append({
                'device_id': row['device_id'],
                'width': int(row['width']),
                'height': int(row['height'])
            })
    return devices


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
            upscale_by = math.sqrt(device_pixels / gen_pixels)
            print(f"    Upscale {input_file.name} -> {output_file.name} (x{upscale_by:.2f})")
            image_data = usdu(api, wf, str(input_file), upscale_by)
            save_image(image_data, output_file)

            # 验证并调整尺寸到精确的目标分辨率
            img = Image.open(output_file)
            actual_width, actual_height = img.size
            img.close()
            if actual_width != device_width or actual_height != device_height:
                print(f"      调整尺寸: {actual_width}x{actual_height} -> {device_width}x{device_height}")
                resize_image(output_file, output_file, device_width, device_height)
        else:
            # 需要downscale
            print(f"    Downscale {input_file.name} -> {output_file.name}")
            resize_image(input_file, output_file, device_width, device_height)

        # 转换为JPG（如果需要）
        if convert_jpg:
            convert_to_jpg(output_file)


def main():
    parser = argparse.ArgumentParser(description='使用ultimate-sd-upscale流程提升分辨率')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='ultimate-sd-upscale.json',
                        help='ComfyUI Workflow文件 (默认: ultimate-sd-upscale.json)')
    parser.add_argument('--input', '-i',
                        help='输入图像文件路径 (单文件模式)')
    parser.add_argument('--output', '-o',
                        help='输出图像文件路径 (单文件模式)')
    parser.add_argument('--input-dir',
                        help='输入目录 (批量模式，与--pixels-csv配合使用)')
    parser.add_argument('--pixels-csv',
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

    # 单文件模式
    elif args.input and args.output:
        # 初始化ComfyUI API和Workflow
        api = ComfyApiWrapper(args.url)
        wf = ComfyWorkflowWrapper(args.workflow)

        # 生成图片
        image_data = usdu(api, wf, args.input, args.upscale_by)

        # 保存PNG文件
        output_path = Path(args.output)
        save_image(image_data, output_path)

        # 转换为JPG（如果需要）
        if args.jpg:
            convert_to_jpg(output_path)

    else:
        print("错误: 必须指定 (--input 和 --output) 或 (--input-dir 和 --pixels-csv)", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
