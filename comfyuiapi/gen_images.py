#!/usr/bin/env python3
"""
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import argparse
import logging
import os
import random
import sys
from pathlib import Path

from comfy_api_simplified import ComfyApiWrapper

from libs import CRITICAL_SIZE, UpscaleMode, calculate_base_resolution, convert_to_jpg, get_all_devices, save_image, zit


def _create_upscale_task(
    counter: int,
    batch: int,
    base_filepath: Path,
    output_filepath: Path,
    target_width: int,
    target_height: int,
    gen_width: int,
    gen_height: int,
    factor: float,
    upscale_method: str,
    convert_jpg: bool,
) -> dict:
    """
    创建超分任务字典

    Args:
        counter: 序列ID
        batch: 批次ID
        base_filepath: 基础图片路径
        output_filepath: 目标输出路径
        target_width: 目标宽度
        target_height: 目标高度
        gen_width: 生成宽度
        gen_height: 生成高度
        factor: 放大倍率
        upscale_method: 超分方法
        convert_jpg: 是否转换为JPG

    Returns:
        超分任务字典
    """
    # 计算放大后的目标尺寸（根据method名称推断放大倍数）
    if upscale_method == "upscale2x":
        # upscale2x 固定放大2倍
        upscaled_width = gen_width * 2
        upscaled_height = gen_height * 2
    elif upscale_method == "upscale4x":
        # upscale4x 固定放大4倍
        upscaled_width = gen_width * 4
        upscaled_height = gen_height * 4
    elif upscale_method == "aurasr":
        # aurasr 固定放大4倍
        upscaled_width = gen_width * 4
        upscaled_height = gen_height * 4
    elif upscale_method == "usdu":
        # USDU根据factor放大
        upscaled_width = int(gen_width * factor)
        upscaled_height = int(gen_height * factor)
    else:
        raise ValueError(f"Unknown upscale method: {upscale_method}")

    return {
        "base_filepath": base_filepath,
        "target_filepath": output_filepath,
        "target_width": target_width,
        "target_height": target_height,
        "convert_jpg": convert_jpg,
        "upscale_method": upscale_method,
        "factor": factor,
        "upscaled_width": upscaled_width,
        "upscaled_height": upscaled_height,
        "counter": counter,
        "batch": batch,
    }


def gen_image_for_device(
    api: ComfyApiWrapper,
    output_dir: Path,
    counter: int,
    batch: int,
    prompt: str,
    seed: int,
    device: dict | None,
    convert_jpg: bool = False,
    upscale_mode: UpscaleMode = UpscaleMode.AUTO,
) -> dict | None:
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
        upscale_mode: 超分模式（AUTO/UPSCALE/USDU/NONE）

    Returns:
        如果需要超分，返回包含超分信息的字典；否则返回None
        字典格式: {
            'base_filepath': Path,  # 基础图片路径
            'target_filepath': Path,  # 目标图片路径
            'target_width': int,
            'target_height': int,
            'convert_jpg': bool,
            'upscale_method': str  # 'upscale' 或 'usdu'
        }
    """
    # 确定输出文件名和目标分辨率
    if device:
        output_filepath = output_dir / f"{counter:03d}_{batch:02d}_{device['device_id']}.png"
        target_width, target_height = device["width"], device["height"]
    else:
        output_filepath = output_dir / f"{counter:03d}_{batch:02d}.png"
        target_width, target_height = 1024, 1024  # 默认分辨率

    # 检查目标文件是否已存在
    if output_filepath.exists():
        logging.info(f"Skipping {output_filepath.name}: file already exists")
        return None

    total_pixels = target_width * target_height
    need_upscale = False
    upscale_method = None

    # 计算生成分辨率
    gen_width, gen_height = target_width, target_height

    # 如果upscale_mode不是NONE且总像素超过临界尺寸，需要缩放
    if upscale_mode != UpscaleMode.NONE and total_pixels > CRITICAL_SIZE:
        need_upscale = True

        # 计算基础图片分辨率和放大倍率
        gen_width, gen_height, factor = calculate_base_resolution(target_width, target_height)

        # 根据upscale_mode决定使用哪个超分方法
        if upscale_mode == UpscaleMode.AUTO:
            # 智能模式：factor<=2使用upscale2x，factor>2使用aurasr
            upscale_method = "upscale2x" if factor <= 2 else "aurasr"
        elif upscale_mode == UpscaleMode.UPSCALE2X:
            upscale_method = "upscale2x"
        elif upscale_mode == UpscaleMode.UPSCALE4X:
            upscale_method = "upscale4x"
        elif upscale_mode == UpscaleMode.AURASR:
            upscale_method = "aurasr"
        elif upscale_mode == UpscaleMode.USDU:
            upscale_method = "usdu"

        logging.info(
            f"Target: {target_width}x{target_height}, Generation: {gen_width}x{gen_height}, "
            f"Factor: {factor:.2f}, Method: {upscale_method}, Mode: {upscale_mode.value}"
        )
    else:
        logging.info(
            f"Target: {target_width}x{target_height}, Generation: {gen_width}x{gen_height}, "
            f"Mode: {upscale_mode.value}, Direct generation (no upscale needed)"
        )

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
        return _create_upscale_task(
            counter,
            batch,
            base_filepath,
            output_filepath,
            target_width,
            target_height,
            gen_width,
            gen_height,
            factor,
            upscale_method,
            convert_jpg,
        )
    # 不需要超分，直接生成并保存最终图片
    image_data = zit.zit(api, prompt, seed, gen_width, gen_height)
    save_image(image_data, output_filepath)
    logging.info(f"Saved to {output_filepath}")

    # 如果需要转换为JPG
    if convert_jpg:
        logging.info(f"Converting {output_filepath} to JPG")
        convert_to_jpg(output_filepath)

    return None


def gen_images_for_variation(
    api: ComfyApiWrapper,
    output_dir: Path,
    counter: int,
    prompt: str,
    devices: list[dict],
    batch_size: int = 1,
    convert_jpg: bool = False,
    upscale_mode: UpscaleMode = UpscaleMode.AUTO,
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
        upscale_mode: 超分模式（AUTO/UPSCALE/USDU/NONE）

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
            task = gen_image_for_device(api, output_dir, counter, batch, prompt, seed, None, convert_jpg, upscale_mode)
            if task:
                upscale_tasks.append(task)
        else:
            # 为每个设备生成图片
            for device in devices:
                task = gen_image_for_device(
                    api, output_dir, counter, batch, prompt, seed, device, convert_jpg, upscale_mode
                )
                if task:
                    upscale_tasks.append(task)

    return upscale_tasks


def main() -> None:
    """
    批量生成图片主函数 (Phase 1: Generation)

    从命令行参数读取配置，为每个变奏生成多个批次的图片。
    支持设备模式和默认模式。

    对于分辨率超过临界尺寸的图片，生成base images供upscale.py处理。
    对于分辨率未超过临界尺寸的图片，直接生成最终图片。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="使用z-image-turbo流程生成图片")
    parser.add_argument(
        "--url",
        "-u",
        default=os.environ.get("COMFYUI_API_URL"),
        help="ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)",
    )
    parser.add_argument("--theme", "-t", required=True, help="主题文件路径")
    parser.add_argument("--variations", "-v", required=True, help="变奏文件路径 (每行一个变奏)")
    parser.add_argument("--output-dir", "-o", required=True, help="输出目录")
    parser.add_argument("--pixels-csv", "-p", help="像素分辨率CSV文件。如果指定，则为所有设备生成图片")
    parser.add_argument("--batches", "-b", type=int, default=1, help="每个变奏生成的批次数 (默认: 1)")
    parser.add_argument("--jpg", "-j", action="store_true", help="将生成的PNG图片转换为JPG格式")
    parser.add_argument(
        "--upscale-mode",
        choices=["auto", "upscale2x", "upscale4x", "aurasr", "usdu", "none"],
        default="auto",
        help=(
            "超分模式: auto=智能选择(默认，factor<=2用upscale2x，factor>2用aurasr), "
            "upscale2x/upscale4x=锁定RealESRGAN 2x/4x, aurasr=锁定AuraSR(4x), usdu=锁定USDU, none=禁用超分"
        ),
    )
    args = parser.parse_args()

    if not args.url:
        logging.error(
            "Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable"
        )
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
    with open(args.theme, encoding="utf-8") as f:
        theme = f.read().strip()

    # 初始化ComfyUI API
    api = ComfyApiWrapper(args.url)

    # 解析超分模式
    upscale_mode = UpscaleMode(args.upscale_mode)
    logging.info(f"Upscale mode: {upscale_mode.value}")

    # 读取变奏并生成基础图片
    counter = 0
    with open(args.variations, encoding="utf-8") as fi:
        for line in fi:
            v = line.strip()
            if not v:
                continue

            prompt = f"{theme}\n{v}"
            logging.info(f"Processing counter {counter}")

            # 为该变奏生成所有批次的基础图片或最终图片
            gen_images_for_variation(
                api, output_dir, counter, prompt, devices, args.batches, args.jpg, upscale_mode
            )

            counter += 1

    logging.info("All images generated. Use upscale.py to process base images if needed.")


if __name__ == "__main__":
    main()
