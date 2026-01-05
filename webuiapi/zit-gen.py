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

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper


def zit_generate_image(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes:
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


def get_device_resolution(pixels_csv: str, device_id: str) -> tuple[int, int]:
    """从pixels.csv读取指定设备的分辨率"""
    with open(pixels_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['device_id'] == device_id:
                return int(row['width']), int(row['height'])
    raise ValueError(f"设备 '{device_id}' 未在 {pixels_csv} 中找到")


def calculate_generation_size(device_width: int, device_height: int, target_area: int = 1024 * 1024) -> tuple[int, int]:
    """
    根据设备分辨率计算生成图像尺寸。
    保持设备的纵横比，总像素数接近target_area (默认1024*1024)。
    """
    aspect_ratio = device_width / device_height
    # new_width * new_height = target_area
    # new_width / new_height = aspect_ratio
    # => new_width = sqrt(target_area * aspect_ratio)
    # => new_height = sqrt(target_area / aspect_ratio)
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


def filter_devices_by_ratio(devices: list[dict]) -> list[dict]:
    """
    过滤掉相同纵横比的设备，只保留最高分辨率。
    例如: 3840x2160 和 1920x1080 都是 16:9，只保留 3840x2160
    """
    ratio_groups = {}

    for device in devices:
        width = device['width']
        height = device['height']

        # 计算最简比例 (使用GCD)
        gcd = math.gcd(width, height)
        ratio = (width // gcd, height // gcd)

        # 按比例分组，保留分辨率最高的
        if ratio not in ratio_groups:
            ratio_groups[ratio] = device
        else:
            # 比较分辨率大小（使用实际像素数）
            current_pixels = width * height
            existing_pixels = ratio_groups[ratio]['width'] * ratio_groups[ratio]['height']
            if current_pixels > existing_pixels:
                ratio_groups[ratio] = device

    return list(ratio_groups.values())


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
    parser.add_argument('--pixels-csv',
                        help='像素分辨率CSV文件。如果指定但无--device，则为所有设备生成图片')
    parser.add_argument('--device', '-d',
                        help='设备ID (从pixels.csv读取分辨率并自动计算生成尺寸)')
    parser.add_argument('--width',
                        type=int,
                        default=1024,
                        help='图像宽度 (默认: 1024, 如果指定--device则忽略)')
    parser.add_argument('--height',
                        type=int,
                        default=1024,
                        help='图像高度 (默认: 1024, 如果指定--device则忽略)')
    args = parser.parse_args()

    if not args.url:
        print("错误: 必须通过--url参数或COMFYUI_API_URL环境变量指定ComfyUI API URL", file=sys.stderr)
        sys.exit(1)

    # 确定生成模式和尺寸列表
    generation_sizes = []

    if args.pixels_csv and not args.device:
        # 批量模式：为所有设备生成
        all_devices = get_all_devices(args.pixels_csv)
        filtered_devices = filter_devices_by_ratio(all_devices)
        print(f"批量模式: 原始设备数 {len(all_devices)}, 过滤后 {len(filtered_devices)} 个不同纵横比")

        for device in filtered_devices:
            gen_width, gen_height = calculate_generation_size(device['width'], device['height'])
            generation_sizes.append({
                'device_id': device['device_id'],
                'width': gen_width,
                'height': gen_height,
                'device_width': device['width'],
                'device_height': device['height']
            })
            print(f"  {device['device_id']}: {device['width']}x{device['height']} -> {gen_width}x{gen_height}")
    elif args.device:
        # 单设备模式
        if not args.pixels_csv:
            print("错误: 使用--device时必须指定--pixels-csv", file=sys.stderr)
            sys.exit(1)
        device_width, device_height = get_device_resolution(args.pixels_csv, args.device)
        gen_width, gen_height = calculate_generation_size(device_width, device_height)
        generation_sizes.append({
            'device_id': args.device,
            'width': gen_width,
            'height': gen_height,
            'device_width': device_width,
            'device_height': device_height
        })
        print(f"单设备模式: {args.device} {device_width}x{device_height} -> {gen_width}x{gen_height}")
    else:
        # 手动尺寸模式
        generation_sizes.append({
            'device_id': 'manual',
            'width': args.width,
            'height': args.height,
            'device_width': args.width,
            'device_height': args.height
        })
        print(f"手动尺寸模式: {args.width}x{args.height}")

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
            # 同一个prompt使用相同的seed，确保不同分辨率的图片内容一致
            seed = random.randint(2**20, 2**64)

            # 为每个尺寸生成图片
            for size_info in generation_sizes:
                gen_width = size_info['width']
                gen_height = size_info['height']

                # 检查目标文件是否已存在
                output_filepath = output_dir / f"{counter:03d}_{gen_width}x{gen_height}.png"
                if output_filepath.exists():
                    print(f"跳过 {output_filepath.name}: 文件已存在")
                    continue

                image_data = zit_generate_image(api, wf, prompt, seed, gen_width, gen_height)

                # 保存PNG文件
                save_image(image_data, output_filepath)

            counter += 1


if __name__ == '__main__':
    main()
