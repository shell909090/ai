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


class UpscaleMode(Enum):
    """超分模式枚举"""

    AUTO = "auto"  # 智能控制：根据factor自动选择upscale或usdu
    UPSCALE = "upscale"  # 锁定使用upscale
    USDU = "usdu"  # 锁定使用usdu
    NONE = "none"  # 禁用超分，直接生成目标图片


def round_to_bucket(value: int, bucket_size: int = 64) -> int:
    """
    将分辨率向上取整到最近的桶大小

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
