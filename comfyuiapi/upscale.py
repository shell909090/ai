#!/usr/bin/env python3
"""
@date: 2026-01-08
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps

# Import libs modules directly to avoid triggering libs/__init__.py
# which would import workflow modules requiring comfy_api_simplified
_constants_spec = importlib.util.spec_from_file_location("libs.constants", "libs/constants.py")
_constants_module = importlib.util.module_from_spec(_constants_spec)
sys.modules["libs.constants"] = _constants_module
_constants_spec.loader.exec_module(_constants_module)

_device_spec = importlib.util.spec_from_file_location("libs.device", "libs/device.py")
_device_module = importlib.util.module_from_spec(_device_spec)
sys.modules["libs.device"] = _device_module
_device_spec.loader.exec_module(_device_module)

from libs.constants import CRITICAL_SIZE, calculate_base_resolution
from libs.device import get_all_devices, get_devices_with_upscale_info, print_devices_table


def discover_base_images(output_dir: Path) -> list[tuple[Path, int, int, int, int]]:
    """
    扫描输出目录中的base images并从文件名提取元数据

    文件名格式: {counter:03d}_{batch:02d}_base_{width}x{height}.png

    Args:
        output_dir: 输出目录路径

    Returns:
        (filepath, counter, batch, width, height) 元组列表，按文件名排序
    """
    pattern = re.compile(r"(\d{3})_(\d{2})_base_(\d+)x(\d+)\.png")
    base_images = []

    for filepath in sorted(output_dir.glob("*_base_*.png")):
        match = pattern.match(filepath.name)
        if match:
            counter = int(match.group(1))
            batch = int(match.group(2))
            width = int(match.group(3))
            height = int(match.group(4))
            base_images.append((filepath, counter, batch, width, height))
            logging.debug(f"Found base image: {filepath.name} -> counter={counter}, batch={batch}, {width}x{height}")

    return base_images


def reconstruct_upscale_tasks(
    output_dir: Path,
    base_images: list[tuple],
    pixels_csv: str | None,
    convert_jpg: bool,
    upscale_mode_str: str,
) -> list[dict]:
    """
    从base images和目标分辨率重建任务字典

    核心逻辑：
    1. 从发现的base images中提取(counter, batch)组合
    2. 对每个(counter, batch)，遍历所有设备
    3. 计算该设备是否需要超分，以及应该使用哪个base image
    4. 只为存在对应base image的设备创建任务

    Args:
        output_dir: 输出目录
        base_images: discover_base_images()返回的元组列表
        pixels_csv: 设备分辨率CSV文件路径（可选）
        convert_jpg: 是否转换为JPG格式
        upscale_mode_str: 超分模式字符串 ("auto"/"upscale"/"usdu")

    Returns:
        与process_all_upscale_tasks()兼容的任务字典列表
    """
    # 加载设备列表
    devices = []
    if pixels_csv:
        devices = get_all_devices(pixels_csv)
        logging.info(f"Loaded {len(devices)} devices from {pixels_csv}")
    else:
        # 默认分辨率
        devices = [{"device_id": "", "width": 1024, "height": 1024}]
        logging.info("Using default resolution: 1024x1024")

    # 构建base image索引: {(counter, batch, gen_width, gen_height): filepath}
    base_image_map = {}
    counter_batch_set = set()
    for base_filepath, counter, batch, gen_width, gen_height in base_images:
        base_image_map[(counter, batch, gen_width, gen_height)] = base_filepath
        counter_batch_set.add((counter, batch))

    logging.info(f"Found {len(counter_batch_set)} unique (counter, batch) combinations")

    tasks = []

    # 对每个(counter, batch)组合，遍历所有设备
    for counter, batch in sorted(counter_batch_set):
        for device in devices:
            target_width = device["width"]
            target_height = device["height"]

            # 确定目标文件名
            if device["device_id"]:
                target_filepath = output_dir / f"{counter:03d}_{batch:02d}_{device['device_id']}.png"
            else:
                target_filepath = output_dir / f"{counter:03d}_{batch:02d}.png"

            # 如果目标文件已存在，跳过
            if target_filepath.exists():
                logging.debug(f"Skipping {target_filepath.name}: file already exists")
                continue

            # 判断是否需要超分（复制gen_images.py的逻辑）
            total_pixels = target_width * target_height
            if total_pixels <= CRITICAL_SIZE:
                # 不需要超分，直接生成的图片，跳过
                logging.debug(
                    f"Skipping {target_filepath.name}: resolution {target_width}x{target_height} "
                    f"({total_pixels/1e6:.2f}M) <= critical size, should be generated directly"
                )
                continue

            # 需要超分：计算应该使用的base image尺寸
            gen_width, gen_height, factor = calculate_base_resolution(target_width, target_height)

            # 检查是否存在对应的base image
            base_key = (counter, batch, gen_width, gen_height)
            if base_key not in base_image_map:
                logging.warning(
                    f"Missing base image for {target_filepath.name}: "
                    f"expected {counter:03d}_{batch:02d}_base_{gen_width}x{gen_height}.png"
                )
                continue

            base_filepath = base_image_map[base_key]

            # 根据upscale_mode确定使用哪个超分方法
            if upscale_mode_str == "auto":
                upscale_method = "upscale" if factor <= 2 else "usdu"
            elif upscale_mode_str == "upscale":
                upscale_method = "upscale"
            elif upscale_mode_str == "usdu":
                upscale_method = "usdu"
            else:
                raise ValueError(f"Unknown upscale mode: {upscale_mode_str}")

            # 计算放大后的尺寸
            if upscale_method == "upscale":
                # RealESRGAN_x2 固定放大2倍
                upscaled_width = gen_width * 2
                upscaled_height = gen_height * 2
            else:
                # USDU根据factor放大
                upscaled_width = int(gen_width * factor)
                upscaled_height = int(gen_height * factor)

            # 创建任务字典
            task = {
                "base_filepath": base_filepath,
                "target_filepath": target_filepath,
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
            tasks.append(task)

            logging.debug(
                f"Task: {target_filepath.name}, base={base_filepath.name}, "
                f"method={upscale_method}, factor={factor:.2f}, upscaled={upscaled_width}x{upscaled_height}"
            )

    return tasks


def process_upscale_task(api: ComfyApiWrapper, task: dict, upscale_cache: dict) -> Path:
    """
    处理单个超分任务，使用缓存避免重复计算

    Args:
        api: ComfyUI API wrapper
        task: 超分任务字典
        upscale_cache: 缓存字典，key为缓存文件路径，value为已完成标记

    Returns:
        缓存的放大图文件路径
    """
    from libs import upscale, usdu
    from libs.image import save_image

    base_filepath = task["base_filepath"]
    upscale_method = task["upscale_method"]
    counter = task["counter"]
    batch = task["batch"]
    factor = task["factor"]
    upscaled_width = task["upscaled_width"]
    upscaled_height = task["upscaled_height"]

    # 生成缓存文件名
    output_dir = base_filepath.parent
    upscaled_filepath = (
        output_dir / f"{counter:03d}_{batch:02d}_upscaled_{upscale_method}_{upscaled_width}x{upscaled_height}.png"
    )

    # 检查缓存：如果已经存在，直接返回
    if upscaled_filepath in upscale_cache or upscaled_filepath.exists():
        if upscaled_filepath not in upscale_cache:
            logging.info(f"Using cached upscaled image: {upscaled_filepath}")
            upscale_cache[upscaled_filepath] = True
        return upscaled_filepath

    # 未缓存，需要执行超分
    logging.info(f"Upscaling {base_filepath} using {upscale_method}")

    if upscale_method == "upscale":
        # 使用RealESRGAN_x2进行2倍放大
        upscaled_data = upscale.upscale(api, str(base_filepath))
    elif upscale_method == "usdu":
        # 使用USDU进行超分
        logging.info(f"USDU upscale factor: {factor:.2f}")
        upscaled_data = usdu.usdu(api, str(base_filepath), factor)
    else:
        raise ValueError(f"Unknown upscale method: {upscale_method}")

    # 保存到缓存
    save_image(upscaled_data, upscaled_filepath)
    logging.info(f"Saved upscaled image to {upscaled_filepath}")
    upscale_cache[upscaled_filepath] = True

    return upscaled_filepath


def process_crop_task(task: dict, upscaled_filepath: Path) -> None:
    """
    处理裁切任务：将放大图裁切到目标尺寸

    Args:
        task: 超分任务字典
        upscaled_filepath: 放大图文件路径
    """
    from libs.image import convert_to_jpg

    target_filepath = task["target_filepath"]
    target_width = task["target_width"]
    target_height = task["target_height"]
    convert_jpg = task["convert_jpg"]

    # 读取放大后的图片
    img = Image.open(upscaled_filepath)
    actual_width, actual_height = img.size
    logging.info(f"Cropping from {actual_width}x{actual_height} to {target_width}x{target_height}")

    # 使用 ImageOps.fit 裁切/适应到目标尺寸
    # 保持放大图长宽比，缩放至能覆盖目标尺寸的最小尺寸，然后居中裁切
    if actual_width != target_width or actual_height != target_height:
        logging.info(f"Fitting from {actual_width}x{actual_height} to {target_width}x{target_height}")
        img = ImageOps.fit(img, (target_width, target_height), Image.LANCZOS, centering=(0.5, 0.5))

    # 保存最终图片
    img.save(target_filepath, "PNG")
    logging.info(f"Saved to {target_filepath}")

    # 如果需要转换为JPG
    if convert_jpg:
        logging.info(f"Converting {target_filepath} to JPG")
        convert_to_jpg(target_filepath)


def process_all_upscale_tasks(api: ComfyApiWrapper, all_upscale_tasks: list[dict], keep_intermediates: bool) -> None:
    """
    统一处理所有超分任务，按方法分组以避免频繁切换模型，使用缓存避免重复计算

    Args:
        api: ComfyUI API wrapper
        all_upscale_tasks: 所有超分任务列表
        keep_intermediates: 是否保留中间文件（原图和放大图）
    """
    if not all_upscale_tasks:
        logging.warning("No upscale tasks found. Nothing to do.")
        return

    logging.info(f"Processing {len(all_upscale_tasks)} upscale tasks")

    # 缓存字典：记录已经生成的upscaled图片
    upscale_cache = {}

    # 按超分方法分组
    upscale_tasks = [task for task in all_upscale_tasks if task["upscale_method"] == "upscale"]
    usdu_tasks = [task for task in all_upscale_tasks if task["upscale_method"] == "usdu"]

    # Phase 2: 先处理所有upscale任务（生成放大图）
    task_to_upscaled = {}  # 记录每个任务对应的放大图路径
    if upscale_tasks:
        logging.info(f"Processing {len(upscale_tasks)} RealESRGAN upscale tasks")
        for i, task in enumerate(upscale_tasks, 1):
            logging.info(f"RealESRGAN task {i}/{len(upscale_tasks)}")
            upscaled_filepath = process_upscale_task(api, task, upscale_cache)
            task_to_upscaled[id(task)] = upscaled_filepath

    # Phase 3: 再处理所有usdu任务（生成放大图）
    if usdu_tasks:
        logging.info(f"Processing {len(usdu_tasks)} USDU upscale tasks")
        for i, task in enumerate(usdu_tasks, 1):
            logging.info(f"USDU task {i}/{len(usdu_tasks)}")
            upscaled_filepath = process_upscale_task(api, task, upscale_cache)
            task_to_upscaled[id(task)] = upscaled_filepath

    # Phase 4: 处理所有裁切任务（将放大图裁切到目标尺寸）
    logging.info(f"Processing {len(all_upscale_tasks)} crop tasks")
    for i, task in enumerate(all_upscale_tasks, 1):
        upscaled_filepath = task_to_upscaled[id(task)]
        logging.info(f"Crop task {i}/{len(all_upscale_tasks)}")
        process_crop_task(task, upscaled_filepath)

    # Phase 5: 清理中间文件（如果需要）
    _cleanup_intermediate_files(all_upscale_tasks, upscale_cache, keep_intermediates)


def _cleanup_intermediate_files(all_upscale_tasks: list[dict], upscale_cache: dict, keep_intermediates: bool) -> None:
    """
    清理中间文件（原图和放大图）

    Args:
        all_upscale_tasks: 所有超分任务列表
        upscale_cache: 缓存字典
        keep_intermediates: 是否保留中间文件
    """
    if not keep_intermediates:
        # 收集所有唯一的基础图片和放大图文件路径
        base_files = set()
        upscaled_files = set()
        for task in all_upscale_tasks:
            base_files.add(task["base_filepath"])
        for upscaled_filepath in upscale_cache:
            upscaled_files.add(upscaled_filepath)

        # 删除所有临时基础图片文件
        logging.info(f"Cleaning up {len(base_files)} base images and {len(upscaled_files)} upscaled images")
        for base_filepath in base_files:
            if base_filepath.exists():
                os.unlink(base_filepath)
                logging.debug(f"Deleted base image {base_filepath}")
        for upscaled_filepath in upscaled_files:
            if upscaled_filepath.exists():
                os.unlink(upscaled_filepath)
                logging.debug(f"Deleted upscaled image {upscaled_filepath}")
    else:
        logging.info("Keeping intermediate files (base images and upscaled images)")


def main() -> None:
    """
    批量超分放大主函数 (Phases 2-4: Upscaling)

    扫描输出目录中的基础图片（base images），执行超分和裁切。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="批量超分放大图片")
    parser.add_argument(
        "--url",
        "-u",
        default=os.environ.get("COMFYUI_API_URL"),
        help="ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)",
    )
    parser.add_argument("--output-dir", "-o", help="输出目录（包含base images）")
    parser.add_argument("--pixels-csv", "-p", help="像素分辨率CSV文件")
    parser.add_argument("--jpg", "-j", action="store_true", help="转换为JPG格式")
    parser.add_argument(
        "--upscale-mode",
        choices=["auto", "upscale", "usdu"],
        default="auto",
        help="超分模式: auto=智能选择(默认), upscale=锁定RealESRGAN, usdu=锁定USDU",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="保留中间文件（原图和放大图）",
    )
    parser.add_argument(
        "--show-table",
        action="store_true",
        help="只显示设备信息表格，不执行超分",
    )
    args = parser.parse_args()

    # 如果只显示表格，不需要 API URL
    if args.show_table:
        if not args.pixels_csv:
            logging.error("Error: --pixels-csv is required when using --show-table")
            sys.exit(1)

        logging.info(f"Loading device information from {args.pixels_csv}")
        devices = get_devices_with_upscale_info(args.pixels_csv, args.upscale_mode)
        print_devices_table(devices)
        sys.exit(0)

    if not args.url:
        logging.error(
            "Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable"
        )
        sys.exit(1)

    if not args.output_dir:
        logging.error("Error: --output-dir is required for upscaling operations")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        logging.error(f"Output directory does not exist: {output_dir}")
        sys.exit(1)

    # 1. 发现base images
    logging.info(f"Scanning for base images in {output_dir}")
    base_images = discover_base_images(output_dir)

    if not base_images:
        logging.warning(f"No base images found in {output_dir}. Nothing to do.")
        logging.info("Tip: Run gen_images.py first to generate base images.")
        sys.exit(0)

    logging.info(f"Found {len(base_images)} base images")

    # 2. 重建任务
    logging.info("Reconstructing upscale tasks")
    tasks = reconstruct_upscale_tasks(
        output_dir,
        base_images,
        args.pixels_csv,
        args.jpg,
        args.upscale_mode,
    )

    if not tasks:
        logging.info("All target images already exist. Nothing to do.")
        sys.exit(0)

    logging.info(f"Created {len(tasks)} upscale tasks")

    # 3. 初始化API
    from comfy_api_simplified import ComfyApiWrapper

    api = ComfyApiWrapper(args.url)

    # 4. 处理所有超分任务 (Phases 2-4)
    process_all_upscale_tasks(api, tasks, args.keep_intermediates)

    logging.info("All upscaling tasks completed successfully.")


if __name__ == "__main__":
    main()
