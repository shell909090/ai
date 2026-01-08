#!/usr/bin/env python3
"""
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import csv
import logging
from pathlib import Path

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper
from PIL import Image

# Re-export ComfyApiWrapper for convenience
__all__ = ["ComfyApiWrapper", "ComfyWorkflow"]


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
