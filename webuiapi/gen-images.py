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

from comfy_api_simplified import ComfyApiWrapper

import zit
from libs import save_image, calculate_generation_size, get_all_devices


def gen_image_for_device(api, output_dir, counter, batch, prompt, seed, device):
    """
    为单个设备生成图片

    Args:
        api: ComfyUI API wrapper
        output_dir: 输出目录
        counter: 序列ID (从0开始)
        batch: 批次ID (从0开始)
        prompt: 提示词
        seed: 随机数种子
        device: 设备信息字典，包含 device_id, width, height；如果为None则不指定设备
    """
    # 确定输出文件名
    if device:
        output_filepath = output_dir / f"{counter:03d}_{batch:02d}_{device['device_id']}.png"
        width, height = device['width'], device['height']
    else:
        output_filepath = output_dir / f"{counter:03d}_{batch:02d}.png"
        width, height = 1024, 1024  # 默认分辨率

    # 检查目标文件是否已存在
    if output_filepath.exists():
        logging.info(f"Skipping {output_filepath.name}: file already exists")
        return

    # 调用 zit.zit 生成图片
    image_data = zit.zit(api, prompt, seed, width, height)

    # 保存图片
    save_image(image_data, output_filepath)


def gen_images_for_variation(api, output_dir, counter, prompt, devices, batch_size=1):
    """
    为一个变奏生成所有批次的图片

    Args:
        api: ComfyUI API wrapper
        output_dir: 输出目录
        counter: 序列ID
        prompt: 提示词
        devices: 设备信息列表，每个设备包含 device_id, width, height
        batch_size: 批次数量
    """
    for batch in range(batch_size):
        # 同一个counter和batch使用相同的seed，确保不同设备的图片内容一致
        seed = random.randint(2**20, 2**64)
        logging.info(f"Batch {batch}, seed: {seed}")

        # 为所有设备生成图片
        if not devices:
            # 没有指定设备，生成默认分辨率
            gen_image_for_device(api, output_dir, counter, batch, prompt, seed, None)
        else:
            # 为每个设备生成图片
            for device in devices:
                gen_image_for_device(api, output_dir, counter, batch, prompt, seed, device)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    parser = argparse.ArgumentParser(description='使用z-image-turbo流程生成图片')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
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
                        help='像素分辨率CSV文件。如果指定，则为所有设备生成图片')
    parser.add_argument('--batches', '-b',
                        type=int,
                        default=1,
                        help='每个变奏生成的批次数 (默认: 1)')
    args = parser.parse_args()

    if not args.url:
        logging.error("Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable")
        sys.exit(1)

    # 确定生成模式和尺寸列表
    devices = []

    if args.pixels_csv:
        # 设备模式：为所有设备生成
        all_devices = get_all_devices(args.pixels_csv)
        logging.info(f"Device mode: {len(all_devices)} devices")

        for device in all_devices:
            gen_width, gen_height = calculate_generation_size(device['width'], device['height'])
            devices.append({
                'device_id': device['device_id'],
                'width': gen_width,
                'height': gen_height
            })
            logging.info(f"  {device['device_id']}: {device['width']}x{device['height']} -> {gen_width}x{gen_height}")
    else:
        # 默认模式：不指定设备，生成默认分辨率
        logging.info("Default mode: generating 1024x1024 images")

    # 检查输出目录
    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    # 读取主题
    with open(args.theme, 'r', encoding='utf-8') as f:
        theme = f.read().strip()

    # 初始化ComfyUI API
    api = ComfyApiWrapper(args.url)

    # 读取变奏并生成图片
    counter = 0
    with open(args.variations, 'r', encoding='utf-8') as fi:
        for line in fi:
            v = line.strip()
            if not v:
                continue

            prompt = f"{theme}\n{v}"
            logging.info(f"Processing counter {counter}")

            # 为该变奏生成所有批次
            gen_images_for_variation(api, output_dir, counter, prompt, devices, args.batches)

            counter += 1


if __name__ == '__main__':
    main()
