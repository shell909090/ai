#!/usr/bin/env python3
"""
Device and CSV utilities

@date: 2026-01-08
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import csv

from libs.constants import CRITICAL_SIZE, calculate_base_resolution


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


def get_devices_with_upscale_info(pixels_csv: str, upscale_mode: str = "auto") -> list[dict]:
    """
    从CSV文件读取设备信息，并计算所有超分相关参数

    Args:
        pixels_csv: CSV文件路径，需包含 device_id, width, height 列
        upscale_mode: 超分模式 ("auto"/"upscale"/"usdu")

    Returns:
        设备信息列表，每个设备包含:
        - device_id: 设备ID
        - width: 目标宽度
        - height: 目标高度
        - total_pixels: 总像素数
        - need_upscale: 是否需要超分
        - gen_width: 生成宽度（如果需要超分）
        - gen_height: 生成高度（如果需要超分）
        - factor: 放大倍率（如果需要超分）
        - upscale_method: 超分方法 ("upscale"/"usdu"，如果需要超分）
        - upscaled_width: 放大后宽度（如果需要超分）
        - upscaled_height: 放大后高度（如果需要超分）
    """
    devices = []
    with open(pixels_csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            device_id = row["device_id"]
            width = int(row["width"])
            height = int(row["height"])
            total_pixels = width * height

            device_info = {
                "device_id": device_id,
                "width": width,
                "height": height,
                "total_pixels": total_pixels,
                "need_upscale": total_pixels > CRITICAL_SIZE,
            }

            # 如果需要超分，计算相关参数
            if device_info["need_upscale"]:
                gen_width, gen_height, factor = calculate_base_resolution(width, height)
                device_info["gen_width"] = gen_width
                device_info["gen_height"] = gen_height
                device_info["factor"] = factor

                # 根据upscale_mode确定使用哪个超分方法
                if upscale_mode == "auto":
                    upscale_method = "upscale" if factor <= 2 else "usdu"
                elif upscale_mode == "upscale":
                    upscale_method = "upscale"
                elif upscale_mode == "usdu":
                    upscale_method = "usdu"
                else:
                    raise ValueError(f"Unknown upscale mode: {upscale_mode}")

                device_info["upscale_method"] = upscale_method

                # 计算放大后的尺寸
                if upscale_method == "upscale":
                    # RealESRGAN_x2 固定放大2倍
                    device_info["upscaled_width"] = gen_width * 2
                    device_info["upscaled_height"] = gen_height * 2
                else:
                    # USDU根据factor放大
                    device_info["upscaled_width"] = int(gen_width * factor)
                    device_info["upscaled_height"] = int(gen_height * factor)
            else:
                # 不需要超分，直接生成
                device_info["gen_width"] = width
                device_info["gen_height"] = height
                device_info["factor"] = 1.0
                device_info["upscale_method"] = "none"
                device_info["upscaled_width"] = None
                device_info["upscaled_height"] = None

            devices.append(device_info)

    return devices


def print_devices_table(devices: list[dict]) -> None:
    """
    打印设备信息表格

    Args:
        devices: get_devices_with_upscale_info() 返回的设备列表
    """
    try:
        from prettytable import PrettyTable
    except ImportError:
        # Fallback to simple text table if prettytable not available
        print("\nDevice Information:")
        print("-" * 120)
        print(
            f"{'Device ID':<20} {'Target':<12} {'Pixels':<8} {'Gen Size':<12} "
            f"{'Factor':<7} {'Method':<8} {'Upscaled':<12}"
        )
        print("-" * 120)
        for device in devices:
            target_size = f"{device['width']}x{device['height']}"
            pixels_m = f"{device['total_pixels']/1e6:.2f}M"

            if device["need_upscale"]:
                gen_size = f"{device['gen_width']}x{device['gen_height']}"
                factor = f"{device['factor']:.2f}x"
                method = device["upscale_method"]
                upscaled = f"{device['upscaled_width']}x{device['upscaled_height']}"
            else:
                gen_size = target_size
                factor = "1.00x"
                method = "none"
                upscaled = "-"

            print(f"{device['device_id']:<20} {target_size:<12} {pixels_m:<8} {gen_size:<12} {factor:<7} {method:<8} {upscaled:<12}")
        print("-" * 120)
        return

    # Use prettytable if available
    table = PrettyTable()
    table.field_names = ["Device ID", "Target Size", "Pixels", "Need Upscale", "Gen Size", "Factor", "Method", "Upscaled Size"]
    table.align["Device ID"] = "l"
    table.align["Target Size"] = "r"
    table.align["Pixels"] = "r"
    table.align["Need Upscale"] = "c"
    table.align["Gen Size"] = "r"
    table.align["Factor"] = "r"
    table.align["Method"] = "c"
    table.align["Upscaled Size"] = "r"

    for device in devices:
        target_size = f"{device['width']}x{device['height']}"
        pixels_m = f"{device['total_pixels']/1e6:.2f}M"
        need_upscale = "Yes" if device["need_upscale"] else "No"

        if device["need_upscale"]:
            gen_size = f"{device['gen_width']}x{device['gen_height']}"
            factor = f"{device['factor']:.2f}x"
            method = device["upscale_method"]
            upscaled = f"{device['upscaled_width']}x{device['upscaled_height']}"
        else:
            gen_size = target_size
            factor = "1.00x"
            method = "none"
            upscaled = "-"

        table.add_row([device["device_id"], target_size, pixels_m, need_upscale, gen_size, factor, method, upscaled])

    print("\n" + str(table))
