#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@date: 2025-12-16
@author: Shell.Xu
@copyright: 2025, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
'''
import os
import json
import logging
import argparse

import google.generativeai as genai
import typing_extensions as typing
from PIL import Image


# 定义设备及其分辨率
TARGET_DEVICES = [
    {"name": "iPhone_15_Pro", "width": 1179, "height": 2556}, # 极窄长宽比 (~0.46)
    {"name": "iPad_Air",      "width": 1640, "height": 2360}, # 接近方形 (~0.69)
    {"name": "MacBook_Pro",   "width": 3024, "height": 1964}, # 横屏宽幅 (~1.54)
    {"name": "UltraWide",     "width": 3440, "height": 1440}  # 超宽屏 (~2.38)
]


class CropResult(typing.TypedDict):
    box_2d: list[float]


def verify_box_ratio(box, target_ratio, tolerance=0.03):
    """
    验证返回的box是否符合目标比例
    box: [ymin, xmin, ymax, xmax] 归一化坐标
    target_ratio: 目标宽高比 (width/height)
    tolerance: 允许的误差范围 (默认3%)
    """
    xmin, ymin, xmax, ymax = box
    box_width = xmax - xmin
    box_height = ymax - ymin

    if box_height == 0:
        return False

    box_ratio = box_width / box_height
    ratio_diff = abs(box_ratio - target_ratio) / target_ratio

    logging.debug(f"Box ratio: {box_ratio:.3f}, Target ratio: {target_ratio:.3f}, Diff: {ratio_diff:.1%}")

    return ratio_diff <= tolerance


def get_subject_box(model, img, device, max_retries=3):
    """
    只做一件事：让 Gemini 找出画面中最核心的主体（人、物体、建筑）的边界。
    不需要 Gemini 考虑设备比例，只考虑内容。
    如果返回的box比例不符合目标比例，最多重试3次。
    """
    logging.info(f"正在分析视觉重心: {device['name']} ...")

    w, h = img.size
    s_width = float(device['width']) / w
    s_height = float(device['height']) / h
    target_ratio = float(device['width'])/device['height']

    prompt = f"""
    You are an expert photo editor. Your task is to identify the best cropping region for a wallpaper. Analyze the image to find the best bounding box for the MAIN SUBJECT.

    Target Aspect Ratio: {target_ratio:.3f} (width/height = {device['width']}/{device['height']})

    Constraints:
    1. **Completeness**: The box must encompass the full subject (head to toe if applicable, or key features).
    2. **Minimum Size**: Do NOT produce a tight crop. The bounding box MUST cover at least {100*s_width}% width and {100*s_height}% height of the original image area to ensure high resolution.
    3. **Composition**: Include sufficient background/negative space around the subject to match the target aspect ratio naturally.
    4. **Aspect Ratio**: The bounding box MUST approximately match the target aspect ratio {target_ratio:.3f}.
    5. **Safety**: Ensure no important parts (like heads or feet) are cut off.
    6. **Coordinates**: The output must be normalized coordinates [xmin, ymin, xmax, ymax].
    """

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                logging.warning(f"重试第 {attempt} 次...")

            response = model.generate_content(
                [prompt, img],
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json", # 强制 JSON MIME
                    response_schema=CropResult             # 强制 Schema 结构
                ))
            result_json = json.loads(response.text)
            box = result_json["box_2d"]

            logging.debug(f"Subject box: {box}")

            # 验证box比例是否符合目标
            if verify_box_ratio(box, target_ratio):
                logging.info(f"✓ Box比例验证通过")
                return box
            else:
                logging.warning(f"✗ Box比例不匹配目标比例 {target_ratio:.3f}")
                if attempt < max_retries - 1:
                    continue
                else:
                    logging.error(f"达到最大重试次数 ({max_retries})，使用最后一次结果")
                    return box

        except Exception as e:
            logging.error(f"Gemini 分析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                continue
            else:
                return None

    return None


def calculate_best_crop(img_w, img_h, subject_box):
    '''
    核心算法：把subject_box转换为真实坐标
    '''
    xmin, ymin, xmax, ymax = subject_box
    return [round(xmin*img_w), round(ymin*img_h), round(xmax*img_w), round(ymax*img_h)]


def process_image(fp, output_dir, model_name):
    if not os.path.exists(fp):
        logging.error(f"图片不存在: {fp}")
        return

    logging.info("=" * 60)
    logging.info(f"处理图片: {fp}")
    logging.info("=" * 60)

    img = Image.open(fp)
    w, h = img.size

    # Get base filename without extension for output naming
    base_name = os.path.splitext(os.path.basename(fp))[0]

    model = genai.GenerativeModel(model_name)

    # 2. 本地针对不同设备进行几何计算
    for device in TARGET_DEVICES:
        logging.info(f"正在处理: {device['name']} ...")

        subject_box = get_subject_box(model, img, device)

        # 计算最佳裁切框
        crop_box = calculate_best_crop(w, h, subject_box)

        # 裁切
        cropped_img = img.crop(crop_box)

        # 缩放 (Resize)
        # 此时 crop_box 的比例已经严格等于 device 比例，直接 resize 不会有变形
        final_img = cropped_img.resize((device['width'], device['height']), Image.Resampling.LANCZOS)

        # Include base filename in output to avoid overwriting when processing multiple files
        save_path = os.path.join(output_dir, f"{base_name}_{device['name']}.jpg")
        final_img.save(save_path, quality=95)
        logging.info(f" -> 已保存: {save_path}, 裁切源尺寸: {crop_box[2]-crop_box[0]}x{crop_box[3]-crop_box[1]}")


def main():
    parser = argparse.ArgumentParser(description='Auto crop images for multiple device wallpapers')
    parser.add_argument('filenames', nargs='+', type=str, help='Input image file path(s)')
    parser.add_argument('--output-dir', '-o', type=str, default='output_wallpapers_fixed',
                        help='Output directory (default: output_wallpapers_fixed)')
    parser.add_argument('--model', '-m', type=str, default='gemini-2.5-flash',
                        help='Gemini model name (default: gemini-2.5-flash)')
    parser.add_argument('--log-level', '-l', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Logging level (default: INFO)')
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    output_dir = args.output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    logging.info(f"将处理 {len(args.filenames)} 个文件")
    logging.info(f"输出目录: {output_dir}")
    logging.info(f"使用模型: {args.model}")

    for filename in args.filenames:
        try:
            process_image(filename, output_dir, args.model)
        except Exception as e:
            logging.error(f"处理 {filename} 时出错: {e}")
            continue

    logging.info("=" * 60)
    logging.info(f"全部完成! 共处理 {len(args.filenames)} 个文件")
    logging.info("=" * 60)


if __name__ == '__main__':
    main()
