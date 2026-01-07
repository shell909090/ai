#!/usr/bin/env python3
"""
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import csv
import logging
import math
from io import BytesIO
from pathlib import Path

from comfy_api_simplified import ComfyWorkflowWrapper
from PIL import Image


class ComfyWorkflow(ComfyWorkflowWrapper):
    """
    ComfyUI workflow wrapper class

    Extends ComfyWorkflowWrapper from comfy-api-simplified to provide
    a dict-based initialization interface for workflow data.
    """

    def __init__(self, data: dict) -> None:
        """
        Initialize workflow with data dictionary

        Args:
            data: Workflow data as a dictionary (from JSON)
        """
        dict.__init__(self, data)


def read_img_from_byte(image_data: bytes) -> Image.Image:
    """
    从字节数据读取图片

    Args:
        image_data: 原始图片字节数据 (PNG, JPEG等格式)

    Returns:
        PIL Image对象
    """
    return Image.open(BytesIO(image_data))


def save_image(image_data: bytes, output_filepath: Path) -> None:
    """
    保存图片数据到PNG文件

    Args:
        image_data: 图片字节数据
        output_filepath: 输出文件路径，会自动转换为.png后缀
    """
    output_file_png = Path(output_filepath).with_suffix(".png")
    with open(output_file_png, "wb") as f:
        f.write(image_data)
    logging.info(f"Saved PNG: {output_file_png}")


def resize_image(input_filepath: Path, output_filepath: Path, target_width: int, target_height: int) -> None:
    """
    使用PIL调整图片尺寸

    Args:
        input_filepath: 输入图片路径
        output_filepath: 输出图片路径
        target_width: 目标宽度
        target_height: 目标高度
    """
    img = Image.open(input_filepath)
    img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    img_resized.save(output_filepath, "PNG")
    img.close()


def convert_to_jpg(png_filepath: Path, quality: int = 95) -> None:
    """
    将PNG图片转换为JPG格式

    Args:
        png_filepath: PNG文件路径
        quality: JPG质量 (1-100，默认95)
    """
    jpg_filepath = png_filepath.with_suffix(".jpg")
    img = Image.open(png_filepath)

    # 如果图片有透明通道，转换为RGB
    if img.mode in ("RGBA", "LA", "P"):
        rgb_img = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = rgb_img
    elif img.mode != "RGB":
        img = img.convert("RGB")

    img.save(jpg_filepath, "JPEG", quality=quality)
    logging.info(f"Converted to JPG: {jpg_filepath.name}")


def calculate_generation_size(device_width: int, device_height: int, target_area: int = 1024 * 1024) -> tuple[int, int]:
    """
    根据设备分辨率计算生成图像尺寸

    保持设备的纵横比，总像素数接近target_area (默认1024*1024，SDXL训练尺寸)

    Args:
        device_width: 设备宽度
        device_height: 设备高度
        target_area: 目标像素总数，默认1048576 (1024*1024)

    Returns:
        (生成宽度, 生成高度) 元组
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
    """
    从CSV文件读取所有设备信息

    Args:
        pixels_csv: CSV文件路径，需包含 device_id, width, height 列

    Returns:
        设备信息列表，每个设备包含 device_id, width, height
    """
    devices = []
    with open(pixels_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            devices.append({"device_id": row["device_id"], "width": int(row["width"]), "height": int(row["height"])})
    return devices
