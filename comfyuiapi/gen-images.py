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
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image
from comfy_api_simplified import ComfyApiWrapper

import zit
import upscale
from libs import save_image, get_all_devices, read_img_from_byte, convert_to_jpg


def gen_image_for_device(
    api: ComfyApiWrapper,
    output_dir: Path,
    counter: int,
    batch: int,
    prompt: str,
    seed: int,
    device: Optional[dict],
    convert_jpg: bool = False
) -> Optional[dict]:
    """
    为单个设备生成基础图片（不进行超分）

    Args:
        api: ComfyUI API wrapper
        output_dir: 输出目录
        counter: 序列ID (从0开始)
        batch: 批次ID (从0开始)
        prompt: 提示词
        seed: 随机数种子
        device: 设备信息字典，包含 device_id, width, height；如果为None则不指定设备
        convert_jpg: 是否将生成的PNG转换为JPG格式

    Returns:
        如果需要超分，返回包含超分信息的字典；否则返回None
        字典格式: {
            'base_filepath': Path,  # 基础图片路径
            'target_filepath': Path,  # 目标图片路径
            'target_width': int,
            'target_height': int,
            'convert_jpg': bool
        }
    """
    # 确定输出文件名和目标分辨率
    if device:
        output_filepath = output_dir / f"{counter:03d}_{batch:02d}_{device['device_id']}.png"
        target_width, target_height = device['width'], device['height']
    else:
        output_filepath = output_dir / f"{counter:03d}_{batch:02d}.png"
        target_width, target_height = 1024, 1024  # 默认分辨率

    # 检查目标文件是否已存在
    if output_filepath.exists():
        logging.info(f"Skipping {output_filepath.name}: file already exists")
        return None

    # 计算生成分辨率：如果总像素超过1.5*1024*1024，需要缩放
    gen_width, gen_height = target_width, target_height
    total_pixels = gen_width * gen_height
    need_upscale = False

    # 如果超过1.5*1024*1024，循环乘以2/3直到不超过1024*1024
    if total_pixels > 1.5 * 1024 * 1024:
        need_upscale = True
        gen_width = int(gen_width * 2 / 3)
        gen_height = int(gen_height * 2 / 3)
        total_pixels = gen_width * gen_height

        # 循环缩放直到不超过1024*1024
        while total_pixels > 1024 * 1024:
            gen_width = int(gen_width * 2 / 3)
            gen_height = int(gen_height * 2 / 3)
            total_pixels = gen_width * gen_height

    logging.info(f"Target: {target_width}x{target_height}, Generation: {gen_width}x{gen_height}, Need upscale: {need_upscale}")

    # 如果需要超分，先检查临时文件是否已存在
    if need_upscale:
        # 生成基础图片的临时文件名
        base_filepath = output_dir / f"{counter:03d}_{batch:02d}_base_{gen_width}x{gen_height}.png"

        # 检查临时文件是否已存在（断点续传）
        if base_filepath.exists():
            logging.info(f"Base image already exists: {base_filepath}, skipping generation")
        else:
            # 调用 zit.zit 生成基础图片
            image_data = zit.zit(api, prompt, seed, gen_width, gen_height)
            save_image(image_data, base_filepath)
            logging.info(f"Saved base image to {base_filepath}")

        # 返回超分任务信息
        return {
            'base_filepath': base_filepath,
            'target_filepath': output_filepath,
            'target_width': target_width,
            'target_height': target_height,
            'convert_jpg': convert_jpg
        }
    else:
        # 不需要超分，直接生成并保存最终图片
        image_data = zit.zit(api, prompt, seed, gen_width, gen_height)
        save_image(image_data, output_filepath)
        logging.info(f"Saved to {output_filepath}")

        # 如果需要转换为JPG
        if convert_jpg:
            logging.info(f"Converting {output_filepath} to JPG")
            convert_to_jpg(output_filepath)

        return None


def process_upscale_task(api: ComfyApiWrapper, task: dict) -> None:
    """
    处理单个超分任务

    Args:
        api: ComfyUI API wrapper
        task: 超分任务字典，包含 base_filepath, target_filepath, target_width, target_height, convert_jpg
    """
    base_filepath = task['base_filepath']
    target_filepath = task['target_filepath']
    target_width = task['target_width']
    target_height = task['target_height']
    convert_jpg = task['convert_jpg']

    try:
        # 调用upscale进行4倍放大
        logging.info(f"Upscaling {base_filepath}")
        upscaled_data = upscale.upscale(api, str(base_filepath))

        # 读取放大后的图片
        img = read_img_from_byte(upscaled_data)
        actual_width, actual_height = img.size
        logging.info(f"Upscaled size: {actual_width}x{actual_height}")

        # 如果尺寸不严格等于目标尺寸，用PIL进行小幅缩放
        if actual_width != target_width or actual_height != target_height:
            logging.info(f"Resizing from {actual_width}x{actual_height} to {target_width}x{target_height}")
            img = img.resize((target_width, target_height), Image.LANCZOS)

        # 保存最终图片
        img.save(target_filepath, 'PNG')
        logging.info(f"Saved to {target_filepath}")

        # 如果需要转换为JPG
        if convert_jpg:
            logging.info(f"Converting {target_filepath} to JPG")
            convert_to_jpg(target_filepath)

    finally:
        # 删除基础图片临时文件
        if base_filepath.exists():
            os.unlink(base_filepath)
            logging.debug(f"Deleted base image {base_filepath}")


def gen_images_for_variation(
    api: ComfyApiWrapper,
    output_dir: Path,
    counter: int,
    prompt: str,
    devices: list[dict],
    batch_size: int = 1,
    convert_jpg: bool = False
) -> list[dict]:
    """
    为一个变奏生成所有批次的基础图片

    Args:
        api: ComfyUI API wrapper
        output_dir: 输出目录
        counter: 序列ID
        prompt: 提示词
        devices: 设备信息列表，每个设备包含 device_id, width, height
        batch_size: 批次数量
        convert_jpg: 是否将生成的PNG转换为JPG格式

    Returns:
        需要超分的任务列表
    """
    # 收集所有需要超分的任务
    upscale_tasks = []

    for batch in range(batch_size):
        # 同一个counter和batch使用相同的seed，确保不同设备的图片内容一致
        seed = random.randint(2**20, 2**64)
        logging.info(f"Batch {batch}, seed: {seed}")

        # 为所有设备生成基础图片
        if not devices:
            # 没有指定设备，生成默认分辨率
            task = gen_image_for_device(api, output_dir, counter, batch, prompt, seed, None, convert_jpg)
            if task:
                upscale_tasks.append(task)
        else:
            # 为每个设备生成图片
            for device in devices:
                task = gen_image_for_device(api, output_dir, counter, batch, prompt, seed, device, convert_jpg)
                if task:
                    upscale_tasks.append(task)

    return upscale_tasks


def main() -> None:
    """
    批量生成图片主函数

    从命令行参数读取配置，为每个变奏生成多个批次的图片。
    支持设备模式和默认模式。
    """
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
    parser.add_argument('--jpg', '-j',
                        action='store_true',
                        help='将生成的PNG图片转换为JPG格式')
    args = parser.parse_args()

    if not args.url:
        logging.error("Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable")
        sys.exit(1)

    # 确定生成模式和尺寸列表
    devices = []

    if args.pixels_csv:
        # 设备模式：为所有设备生成
        devices = get_all_devices(args.pixels_csv)
        logging.info(f"Device mode: {len(devices)} devices")

        for device in devices:
            logging.info(f"  {device['device_id']}: {device['width']}x{device['height']}")
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

    # 收集所有超分任务
    all_upscale_tasks = []

    # 读取变奏并生成基础图片
    counter = 0
    with open(args.variations, 'r', encoding='utf-8') as fi:
        for line in fi:
            v = line.strip()
            if not v:
                continue

            prompt = f"{theme}\n{v}"
            logging.info(f"Processing counter {counter}")

            # 为该变奏生成所有批次的基础图片
            tasks = gen_images_for_variation(api, output_dir, counter, prompt, devices, args.batches, args.jpg)
            all_upscale_tasks.extend(tasks)

            counter += 1

    # 统一处理所有超分任务
    if all_upscale_tasks:
        logging.info(f"All base images generated. Processing {len(all_upscale_tasks)} upscale tasks")
        for i, task in enumerate(all_upscale_tasks, 1):
            logging.info(f"Upscaling task {i}/{len(all_upscale_tasks)}")
            process_upscale_task(api, task)


if __name__ == '__main__':
    main()
