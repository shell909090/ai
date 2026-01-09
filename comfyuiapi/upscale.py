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
from typing import TYPE_CHECKING

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

from libs.constants import get_bucket_for_device
from libs.device import get_all_devices

if TYPE_CHECKING:
    from comfy_api_simplified import ComfyApiWrapper


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
    devices: list[dict],
    upscale_mode_str: str,
) -> list[dict]:
    """
    从base images和设备列表重建任务字典（使用4-bucket映射）

    Args:
        output_dir: 输出目录
        base_images: discover_base_images()返回的元组列表
        devices: 设备列表（从get_all_devices获取）
        upscale_mode_str: 超分模式字符串 ("auto"/"upscale2x"/"upscale4x"/"aurasr"/"usdu")

    Returns:
        任务字典列表

    Raises:
        FileNotFoundError: 如果设备所需的base image不存在
    """
    tasks = []

    # 提取唯一的(counter, batch)组合
    counter_batch_set = set()
    for _, counter, batch, _, _ in base_images:
        counter_batch_set.add((counter, batch))

    # 构建base image索引: {(counter, batch, width, height): filepath}
    base_image_map = {}
    for base_filepath, counter, batch, width, height in base_images:
        base_image_map[(counter, batch, width, height)] = base_filepath

    # 对每个(counter, batch)组合，遍历所有设备
    for counter, batch in sorted(counter_batch_set):
        for device in devices:
            # 确定目标文件名（裁剪后直接存为JPG）
            target_filepath = output_dir / f"{counter:03d}_{batch:02d}_{device['device_id']}.jpg"

            # 如果目标文件已存在，跳过（断点续传）
            if target_filepath.exists():
                logging.debug(f"Skipping {target_filepath.name}: file already exists")
                continue

            # 将设备映射到bucket
            bucket_w, bucket_h, bucket_idx = get_bucket_for_device(device["width"], device["height"])

            # 检查所需的base image是否存在
            base_key = (counter, batch, bucket_w, bucket_h)
            if base_key not in base_image_map:
                raise FileNotFoundError(
                    f"Required base image not found: {counter:03d}_{batch:02d}_base_{bucket_w}x{bucket_h}.png\n"
                    f"Device '{device['device_id']}' ({device['width']}x{device['height']}) requires bucket {bucket_idx} "
                    f"({bucket_w}x{bucket_h}), but this base image is missing.\n"
                    f"Please generate the missing bucket using gen_images.py --buckets {bucket_idx}"
                )

            base_filepath = base_image_map[base_key]

            # 计算放大倍率
            factor = max(device["width"] / bucket_w, device["height"] / bucket_h)

            # 根据upscale_mode确定使用哪个超分方法
            if upscale_mode_str == "auto":
                # 智能模式：factor<=2使用upscale2x，factor>2使用aurasr
                upscale_method = "upscale2x" if factor <= 2 else "aurasr"
            elif upscale_mode_str == "upscale2x":
                upscale_method = "upscale2x"
            elif upscale_mode_str == "upscale4x":
                upscale_method = "upscale4x"
            elif upscale_mode_str == "aurasr":
                upscale_method = "aurasr"
            elif upscale_mode_str == "usdu":
                upscale_method = "usdu"
            else:
                raise ValueError(f"Unknown upscale mode: {upscale_mode_str}")

            # 计算放大后的尺寸
            if upscale_method == "upscale2x":
                upscaled_w, upscaled_h = bucket_w * 2, bucket_h * 2
            elif upscale_method == "upscale4x":
                upscaled_w, upscaled_h = bucket_w * 4, bucket_h * 4
            elif upscale_method == "aurasr":
                upscaled_w, upscaled_h = bucket_w * 4, bucket_h * 4
            elif upscale_method == "usdu":
                upscaled_w = int(bucket_w * factor)
                upscaled_h = int(bucket_h * factor)
            else:
                raise ValueError(f"Unknown upscale method: {upscale_method}")

            # 生成upscaled文件路径（新命名：移除"upscaled"词）
            upscaled_filepath = output_dir / f"{counter:03d}_{batch:02d}_{upscale_method}_{upscaled_w}x{upscaled_h}.png"

            # 创建任务字典
            task = {
                "base_filepath": base_filepath,
                "target_filepath": target_filepath,
                "target_width": device["width"],
                "target_height": device["height"],
                "upscale_method": upscale_method,
                "upscaled_filepath": upscaled_filepath,
                "bucket_width": bucket_w,
                "bucket_height": bucket_h,
                "factor": factor,
                "device_id": device["device_id"],
                "counter": counter,
                "batch": batch,
            }
            tasks.append(task)

            logging.debug(
                f"Task: {target_filepath.name}, base={base_filepath.name}, "
                f"bucket={bucket_w}x{bucket_h}, method={upscale_method}, factor={factor:.2f}"
            )

    return tasks


def process_upscale_task(api: ComfyApiWrapper, task: dict, upscale_cache: dict) -> None:
    """
    执行单个超分任务，使用缓存避免重复计算

    Args:
        api: ComfyUI API wrapper
        task: 超分任务字典
        upscale_cache: 缓存字典，key为upscaled_filepath，value为True
    """
    from libs import aurasr, upscale, usdu
    from libs.image import save_image

    base_filepath = task["base_filepath"]
    upscaled_filepath = task["upscaled_filepath"]
    upscale_method = task["upscale_method"]
    factor = task["factor"]

    # 检查是否已经生成过（缓存或断点续传）
    if upscaled_filepath.exists():
        if upscaled_filepath not in upscale_cache:
            logging.debug(f"Using existing upscaled image: {upscaled_filepath.name}")
            upscale_cache[upscaled_filepath] = True
        return

    # 检查是否在本次运行中已经处理过
    if upscaled_filepath in upscale_cache:
        logging.debug(f"Using cached upscaled image: {upscaled_filepath.name}")
        return

    # 需要执行超分
    logging.info(f"Upscaling {base_filepath.name} using {upscale_method}")

    # 根据method调用对应workflow
    if upscale_method == "aurasr":
        logging.info("AuraSR upscale (4x)")
        upscaled_data = aurasr.aurasr(api, str(base_filepath))
    elif upscale_method == "upscale2x":
        logging.info("RealESRGAN upscale 2x")
        upscaled_data = upscale.upscale(api, str(base_filepath), "RealESRGAN_x2.pth")
    elif upscale_method == "upscale4x":
        logging.info("RealESRGAN upscale 4x")
        upscaled_data = upscale.upscale(api, str(base_filepath), "RealESRGAN_x4.pth")
    elif upscale_method == "usdu":
        logging.info(f"USDU upscale factor: {factor:.2f}")
        upscaled_data = usdu.usdu(api, str(base_filepath), factor)
    else:
        raise ValueError(f"Unknown upscale method: {upscale_method}")

    # 保存并缓存
    save_image(upscaled_data, upscaled_filepath)
    logging.info(f"Saved upscaled image to {upscaled_filepath.name}")
    upscale_cache[upscaled_filepath] = True


def process_crop_task(task: dict) -> None:
    """
    处理裁切任务：将放大图裁切到目标尺寸，直接保存为JPG

    Args:
        task: 超分任务字典
    """
    upscaled_filepath = task["upscaled_filepath"]
    target_filepath = task["target_filepath"]
    target_width = task["target_width"]
    target_height = task["target_height"]

    # 如果目标文件已存在，跳过
    if target_filepath.exists():
        logging.debug(f"Target already exists: {target_filepath.name}, skipping")
        return

    # 检查upscaled图片是否存在
    if not upscaled_filepath.exists():
        logging.warning(f"Upscaled image not found: {upscaled_filepath.name}, skipping crop")
        return

    # 读取放大后的图片
    img = Image.open(upscaled_filepath)
    actual_width, actual_height = img.size
    logging.info(f"Cropping {upscaled_filepath.name} from {actual_width}x{actual_height} to {target_width}x{target_height}")

    # 使用 ImageOps.fit 裁切/适应到目标尺寸
    # 保持放大图长宽比，缩放至能覆盖目标尺寸的最小尺寸，然后居中裁切
    if actual_width != target_width or actual_height != target_height:
        img = ImageOps.fit(img, (target_width, target_height), Image.LANCZOS, centering=(0.5, 0.5))

    # 转换为RGB（如果需要）
    if img.mode in ("RGBA", "LA", "P"):
        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = rgb_img
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # 直接保存为JPG（质量95）
    img.save(target_filepath, "JPEG", quality=95)
    logging.info(f"Saved to {target_filepath.name}")


def process_all_upscale_tasks(api: ComfyApiWrapper, all_upscale_tasks: list[dict]) -> None:
    """
    统一处理所有超分任务，按方法分组以避免频繁切换模型

    Args:
        api: ComfyUI API wrapper
        all_upscale_tasks: 所有超分任务列表
    """
    if not all_upscale_tasks:
        logging.warning("No upscale tasks found. Nothing to do.")
        return

    logging.info(f"Processing {len(all_upscale_tasks)} upscale tasks")

    # 缓存字典：记录已经生成的upscaled图片
    upscale_cache = {}

    # 按超分方法分组（避免频繁切换模型）
    upscale2x_tasks = [task for task in all_upscale_tasks if task["upscale_method"] == "upscale2x"]
    upscale4x_tasks = [task for task in all_upscale_tasks if task["upscale_method"] == "upscale4x"]
    aurasr_tasks = [task for task in all_upscale_tasks if task["upscale_method"] == "aurasr"]
    usdu_tasks = [task for task in all_upscale_tasks if task["upscale_method"] == "usdu"]

    # Phase 2a: 处理所有upscale2x任务
    if upscale2x_tasks:
        logging.info(f"Phase 2a: Processing {len(upscale2x_tasks)} upscale2x tasks")
        for i, task in enumerate(upscale2x_tasks, 1):
            logging.info(f"upscale2x task {i}/{len(upscale2x_tasks)}")
            process_upscale_task(api, task, upscale_cache)

    # Phase 2b: 处理所有upscale4x任务
    if upscale4x_tasks:
        logging.info(f"Phase 2b: Processing {len(upscale4x_tasks)} upscale4x tasks")
        for i, task in enumerate(upscale4x_tasks, 1):
            logging.info(f"upscale4x task {i}/{len(upscale4x_tasks)}")
            process_upscale_task(api, task, upscale_cache)

    # Phase 2c: 处理所有aurasr任务
    if aurasr_tasks:
        logging.info(f"Phase 2c: Processing {len(aurasr_tasks)} AuraSR upscale tasks")
        for i, task in enumerate(aurasr_tasks, 1):
            logging.info(f"AuraSR task {i}/{len(aurasr_tasks)}")
            process_upscale_task(api, task, upscale_cache)

    # Phase 3: 处理所有usdu任务
    if usdu_tasks:
        logging.info(f"Phase 3: Processing {len(usdu_tasks)} USDU upscale tasks")
        for i, task in enumerate(usdu_tasks, 1):
            logging.info(f"USDU task {i}/{len(usdu_tasks)}")
            process_upscale_task(api, task, upscale_cache)

    # Phase 4: 处理所有裁切任务（将放大图裁切到目标尺寸）
    logging.info(f"Phase 4: Processing {len(all_upscale_tasks)} crop tasks")
    for i, task in enumerate(all_upscale_tasks, 1):
        logging.info(f"Crop task {i}/{len(all_upscale_tasks)}")
        process_crop_task(task)

    # 不再清理中间文件（保留所有base和upscaled图片）
    logging.info("Upscaling complete. Intermediate files (base and upscaled images) are preserved.")


def main() -> None:
    """
    批量超分放大主函数 (Phases 2-4: Upscaling)

    扫描输出目录中的母图（base images），根据设备列表执行超分和裁切。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="批量超分放大图片")
    parser.add_argument(
        "--url",
        "-u",
        default=os.environ.get("COMFYUI_API_URL"),
        help="ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)",
    )
    parser.add_argument("--output-dir", "-o", required=True, help="输出目录（包含母图）")
    parser.add_argument("--pixels-csv", "-p", required=True, help="像素分辨率CSV文件（必需）")
    parser.add_argument(
        "--upscale-mode",
        choices=["auto", "upscale2x", "upscale4x", "aurasr", "usdu"],
        default="auto",
        help=(
            "超分模式: auto=智能选择(默认，factor<=2用upscale2x，factor>2用aurasr), "
            "upscale2x/upscale4x=锁定RealESRGAN 2x/4x, aurasr=锁定AuraSR(4x), usdu=锁定USDU"
        ),
    )
    parser.add_argument(
        "--show-table",
        action="store_true",
        help="只显示设备到分辨率桶的映射表，不执行超分（无需API URL）",
    )
    args = parser.parse_args()

    # 加载设备列表
    devices = get_all_devices(args.pixels_csv)
    logging.info(f"Loaded {len(devices)} devices from {args.pixels_csv}")

    # 如果只显示表格，打印映射后退出
    if args.show_table:
        from libs.device import print_bucket_mapping_table
        print_bucket_mapping_table(devices, args.upscale_mode)
        sys.exit(0)

    # 执行超分需要API URL
    if not args.url:
        logging.error(
            "Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable"
        )
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
    logging.info("Reconstructing upscale tasks using 4-bucket mapping")
    tasks = reconstruct_upscale_tasks(
        output_dir,
        base_images,
        devices,
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
    process_all_upscale_tasks(api, tasks)

    logging.info("All upscaling tasks completed successfully.")
    logging.info(f"Final images (JPG) are in {output_dir}")


if __name__ == "__main__":
    main()
