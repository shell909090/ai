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

from libs import save_image, zit
from libs.constants import BUCKET_RESOLUTIONS


def gen_base_image(
    api: ComfyApiWrapper,
    output_dir: Path,
    counter: int,
    batch: int,
    bucket_idx: int,
    width: int,
    height: int,
    prompt: str,
    seed: int,
) -> None:
    """
    Generate a single base image for a specific bucket.

    Args:
        api: ComfyUI API wrapper
        output_dir: Output directory
        counter: Sequence ID (from variation index)
        batch: Batch ID
        bucket_idx: Bucket index (0-3)
        width: Bucket width
        height: Bucket height
        prompt: Combined theme + variation prompt
        seed: Random seed for generation

    File naming: {counter:03d}_{batch:02d}_base_{width}x{height}.png
    """
    base_filepath = output_dir / f"{counter:03d}_{batch:02d}_base_{width}x{height}.png"

    # Checkpoint recovery: skip if exists
    if base_filepath.exists():
        logging.info(f"Base image already exists: {base_filepath.name}, skipping")
        return

    # Generate using zit
    logging.info(f"Generating bucket {bucket_idx} ({width}x{height}): {base_filepath.name}")
    image_data = zit.zit(api, prompt, seed, width, height)
    save_image(image_data, base_filepath)
    logging.info(f"Saved base image to {base_filepath.name}")


def gen_variation(
    api: ComfyApiWrapper,
    output_dir: Path,
    counter: int,
    prompt: str,
    batches: int,
    selected_buckets: list[int],
) -> None:
    """
    Generate all base images for a single variation across all batches and buckets.

    Args:
        api: ComfyUI API wrapper
        output_dir: Output directory
        counter: Sequence ID for this variation
        prompt: Combined theme + variation prompt
        batches: Number of batches to generate
        selected_buckets: List of bucket indices to generate (0-3)
    """
    logging.info(f"Processing variation {counter}: {prompt[:50]}...")

    # For each batch
    for batch in range(batches):
        # Generate same seed for all buckets in this (counter, batch) pair
        seed = random.randint(2**20, 2**64)
        logging.info(f"  Batch {batch}, seed: {seed}")

        # For each selected bucket
        for bucket_idx in selected_buckets:
            bucket_width, bucket_height = BUCKET_RESOLUTIONS[bucket_idx]
            gen_base_image(
                api,
                output_dir,
                counter,
                batch,
                bucket_idx,
                bucket_width,
                bucket_height,
                prompt,
                seed,
            )


def main() -> None:
    """
    批量生成图片主函数 (Phase 1: Generation)

    为每个变奏生成4张标准分辨率的母图。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="使用z-image-turbo流程生成母图")
    parser.add_argument(
        "--url",
        "-u",
        default=os.environ.get("COMFYUI_API_URL"),
        help="ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)",
    )
    parser.add_argument("--theme", "-t", required=True, help="主题文件路径")
    parser.add_argument("--variations", "-v", required=True, help="变奏文件路径 (每行一个变奏)")
    parser.add_argument("--output-dir", "-o", required=True, help="输出目录")
    parser.add_argument("--batches", "-b", type=int, default=1, help="每个变奏生成的批次数 (默认: 1)")
    parser.add_argument(
        "--buckets",
        type=str,
        default="0,1,2,3",
        help="选择生成哪些分辨率桶 (0=896x1920, 1=1088x1472, 2=1536x1024, 3=1728x960)，默认全部生成",
    )
    args = parser.parse_args()

    if not args.url:
        logging.error(
            "Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable"
        )
        sys.exit(1)

    # Parse bucket selection
    try:
        selected_buckets = [int(b.strip()) for b in args.buckets.split(",")]
        for bucket_idx in selected_buckets:
            if bucket_idx < 0 or bucket_idx >= len(BUCKET_RESOLUTIONS):
                logging.error(f"Error: Invalid bucket index {bucket_idx}. Must be 0-3.")
                sys.exit(1)
    except ValueError:
        logging.error(f"Error: Invalid bucket specification '{args.buckets}'. Use comma-separated numbers (e.g., '0,1,2,3').")
        sys.exit(1)

    # Log bucket selection
    logging.info(f"Selected buckets: {selected_buckets}")
    for bucket_idx in selected_buckets:
        width, height = BUCKET_RESOLUTIONS[bucket_idx]
        logging.info(f"  Bucket {bucket_idx}: {width}x{height}")

    # Check output directory
    output_dir = Path(args.output_dir)
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    # Read theme
    with open(args.theme, encoding="utf-8") as f:
        theme = f.read().strip()

    # Initialize ComfyUI API
    api = ComfyApiWrapper(args.url)

    # Read variations and generate base images
    counter = 0
    with open(args.variations, encoding="utf-8") as fi:
        for line in fi:
            v = line.strip()
            if not v:
                continue

            prompt = f"{theme}\n{v}"
            gen_variation(api, output_dir, counter, prompt, args.batches, selected_buckets)
            counter += 1

    logging.info(f"All base images generated. Total variations: {counter}, batches per variation: {args.batches}")
    logging.info(f"Generated {len(selected_buckets)} bucket(s) per (variation, batch) pair.")
    logging.info("Use upscale.py to upscale and adapt to specific device resolutions.")


if __name__ == "__main__":
    main()
