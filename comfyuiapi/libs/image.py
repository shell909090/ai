#!/usr/bin/env python3
"""
Image I/O utilities

@date: 2026-01-08
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import logging
from pathlib import Path

from PIL import Image


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
