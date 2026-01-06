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

from libs import zit_generate_image, save_image, get_device_resolution, calculate_generation_size, get_all_devices, filter_devices_by_ratio


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
    parser.add_argument('--pixels-csv', '-p',
                        help='像素分辨率CSV文件。如果指定但无--device，则为所有设备生成图片')
    parser.add_argument('--device', '-d',
                        help='设备ID (从pixels.csv读取分辨率并自动计算生成尺寸)')
    args = parser.parse_args()

    if not args.url:
        logging.error("Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable")
        sys.exit(1)

    # 确定生成模式和尺寸列表
    generation_sizes = []

    if args.pixels_csv and not args.device:
        # 批量模式：为所有设备生成
        all_devices = get_all_devices(args.pixels_csv)
        filtered_devices = filter_devices_by_ratio(all_devices)
        logging.info(f"Batch mode: {len(all_devices)} original devices, {len(filtered_devices)} after filtering by aspect ratio")

        for device in filtered_devices:
            gen_width, gen_height = calculate_generation_size(device['width'], device['height'])
            generation_sizes.append({
                'device_id': device['device_id'],
                'width': gen_width,
                'height': gen_height,
                'device_width': device['width'],
                'device_height': device['height']
            })
            logging.info(f"  {device['device_id']}: {device['width']}x{device['height']} -> {gen_width}x{gen_height}")
    elif args.device:
        # 单设备模式
        if not args.pixels_csv:
            logging.error("Error: --pixels-csv must be specified when using --device")
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
        logging.info(f"Single device mode: {args.device} {device_width}x{device_height} -> {gen_width}x{gen_height}")

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
                    logging.info(f"Skipping {output_filepath.name}: file already exists")
                    continue

                image_data = zit_generate_image(api, wf, prompt, seed, gen_width, gen_height)

                # 保存PNG文件
                save_image(image_data, output_filepath)

            counter += 1


if __name__ == '__main__':
    main()
