#!/usr/bin/env python3
"""
Constants and enums for image generation and upscaling

@date: 2026-01-08
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

from enum import Enum

# 临界尺寸：1.5M像素
CRITICAL_SIZE = 1.5 * 1024 * 1024

# 4 standard resolution buckets
BUCKET_RESOLUTIONS = [
    (896, 1920),    # Bucket 0: Very tall/narrow (ar < 0.6)
    (1088, 1472),   # Bucket 1: Portrait (0.6 ≤ ar < 1.15)
    (1536, 1024),   # Bucket 2: Landscape (1.15 ≤ ar < 1.65)
    (1728, 960),    # Bucket 3: Wide (ar ≥ 1.65)
]

# Aspect ratio boundaries for bucket selection
AR_THRESHOLDS = [0.6, 1.15, 1.65]


class UpscaleMode(Enum):
    """超分模式枚举"""

    AUTO = "auto"  # 智能控制：factor<=2使用upscale2x，factor>2使用aurasr4x
    UPSCALE2X = "upscale2x"  # 锁定使用upscale + RealESRGAN_x2.pth
    UPSCALE4X = "upscale4x"  # 锁定使用upscale + RealESRGAN_x4.pth
    AURASR = "aurasr"  # 锁定使用aurasr (4x)
    USDU = "usdu"  # 锁定使用usdu
    NONE = "none"  # 禁用超分，直接生成目标图片


def get_bucket_for_device(width: int, height: int) -> tuple[int, int, int]:
    """
    Map device resolution to appropriate bucket based on aspect ratio.

    Args:
        width: Target device width
        height: Target device height

    Returns:
        (bucket_width, bucket_height, bucket_index): Bucket resolution and index (0-3)
    """
    aspect_ratio = width / height

    # Determine bucket index based on aspect ratio
    if aspect_ratio < AR_THRESHOLDS[0]:
        bucket_index = 0
    elif aspect_ratio < AR_THRESHOLDS[1]:
        bucket_index = 1
    elif aspect_ratio < AR_THRESHOLDS[2]:
        bucket_index = 2
    else:
        bucket_index = 3

    bucket_width, bucket_height = BUCKET_RESOLUTIONS[bucket_index]
    return bucket_width, bucket_height, bucket_index


def round_to_bucket(value: int, bucket_size: int = 64) -> int:
    """
    将分辨率向上取整到最近的桶大小

    DEPRECATED: This function is no longer used in the 4-bucket system.
    Kept for backward compatibility with test code.

    Args:
        value: 原始分辨率值
        bucket_size: 桶大小，默认64

    Returns:
        向上取整后的分辨率值
    """
    return ((value + bucket_size - 1) // bucket_size) * bucket_size


def calculate_base_resolution(target_width: int, target_height: int) -> tuple[int, int, float]:
    """
    根据目标分辨率计算基础图片分辨率和放大倍率

    DEPRECATED: This function is no longer used in the 4-bucket system.
    Use get_bucket_for_device() instead. Kept for backward compatibility with test code.

    使用临界尺寸等比例缩放，并应用分辨率桶规约。

    Args:
        target_width: 目标宽度
        target_height: 目标高度

    Returns:
        (gen_width, gen_height, factor): 基础图片宽度、高度和放大倍率
    """
    import math

    # 等比例缩放到临界尺寸：width * height = CRITICAL_SIZE
    aspect_ratio = target_width / target_height
    gen_width = int(math.sqrt(CRITICAL_SIZE * aspect_ratio))
    gen_height = int(math.sqrt(CRITICAL_SIZE / aspect_ratio))

    # 分辨率桶：向上取整到64的倍数
    gen_width = round_to_bucket(gen_width)
    gen_height = round_to_bucket(gen_height)

    # 计算放大倍率：取宽度和高度放大比例的最大值
    factor = max(target_width / gen_width, target_height / gen_height)

    return gen_width, gen_height, factor


