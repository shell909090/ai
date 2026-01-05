#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
'''
from pathlib import Path
from os import path
from io import BytesIO

from PIL import Image
from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper


def read_img_from_byte(image_data: bytes) -> Image.Image:
    """
    Read an image from raw byte data.

    Args:
        image_data: Raw image bytes (e.g., PNG, JPEG, etc.)

    Returns:
        PIL Image object loaded from the byte data
    """
    return Image.open(BytesIO(image_data))


def save_image(image_data: bytes, output_filepath: Path) -> None:
    output_file_png = Path(output_filepath).with_suffix('.png')
    with open(output_file_png, "wb") as f:
        f.write(image_data)
    print(f"已保存PNG: {output_file_png}")


def resize_image(input_filepath: Path, output_filepath: Path, target_width: int, target_height: int) -> None:
    """使用PIL调整图片尺寸"""
    img = Image.open(input_filepath)
    img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    img_resized.save(output_filepath, 'PNG')
    img.close()


def convert_to_jpg(png_filepath: Path, quality: int = 95) -> None:
    """将PNG转换为JPG"""
    jpg_filepath = png_filepath.with_suffix('.jpg')
    img = Image.open(png_filepath)

    # 如果图片有透明通道，转换为RGB
    if img.mode in ('RGBA', 'LA', 'P'):
        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        rgb_img.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = rgb_img
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    img.save(jpg_filepath, 'JPEG', quality=quality)
    print(f"      已转换为JPG: {jpg_filepath.name}")


def upscale(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, image_filepath: str) -> bytes:
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt['subfolder'], rslt['name'])
    print(f'server side filepath: {server_filepath}')

    wf.set_node_param("加载图像", "image", server_filepath)

    # 生成图片
    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))


def usdu(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, image_filepath: str, upscale_by: float) -> bytes:
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt['subfolder'], rslt['name'])
    print(f'server side filepath: {server_filepath}')

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("Ultimate SD Upscale", "upscale_by", upscale_by)

    # 生成图片
    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))


def outpaint(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, image_filepath: str, left: int, top: int, right: int, bottom: int) -> bytes:
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt['subfolder'], rslt['name'])
    print(f'server side filepath: {server_filepath}')

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("外补画板", "left", left)
    wf.set_node_param("外补画板", "top", top)
    wf.set_node_param("外补画板", "right", right)
    wf.set_node_param("外补画板", "bottom", bottom)

    # 生成图片
    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))


def zit_generate_image(api: ComfyApiWrapper, wf: ComfyWorkflowWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes:
    # 设置提示词和随机种子
    wf.set_node_param("CLIP文本编码", "text", prompt)
    wf.set_node_param("K采样器", "seed", seed)

    # 设置图像尺寸
    wf.set_node_param("空Latent图像（SD3）", "width", width)
    wf.set_node_param("空Latent图像（SD3）", "height", height)

    # 生成图片
    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))
