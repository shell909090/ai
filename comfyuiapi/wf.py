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

from libs import save_image


def main() -> None:
    """
    Workflow入口脚本主函数

    根据命令行参数调用不同的workflow模块（zit, usdu, upscale, aurasr, outpaint）。
    统一处理参数解析和结果保存。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="运行特定workflow")
    parser.add_argument(
        "--url",
        "-u",
        default=os.environ.get("COMFYUI_API_URL"),
        help="ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)",
    )
    parser.add_argument("--workflow", "-w", help="ComfyUI Workflow")
    parser.add_argument("--input", "-i", help="输入图像文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出图像文件路径")
    parser.add_argument("--upscale-by", type=float, help="放大倍数 (默认: 2.0)")
    parser.add_argument("--left", type=int, default=0, help="左侧扩展像素 (默认: 0)")
    parser.add_argument("--top", type=int, default=0, help="顶部扩展像素 (默认: 0)")
    parser.add_argument("--right", type=int, default=0, help="右侧扩展像素 (默认: 0)")
    parser.add_argument("--bottom", type=int, default=0, help="底部扩展像素 (默认: 0)")
    parser.add_argument("--prompt", "-p", help="提示词")
    parser.add_argument(
        "--model-name",
        "-m",
        help="放大模型名称 (仅用于upscale, 例如: RealESRGAN_x2.pth, RealESRGAN_x4.pth, 4x-UltraSharp.pth)",
    )
    parser.add_argument("rest", nargs="*", type=str)
    args = parser.parse_args()

    if not args.url:
        logging.error(
            "Error: ComfyUI API URL must be specified via --url parameter or COMFYUI_API_URL environment variable"
        )
        sys.exit(1)

    # 初始化ComfyUI API和Workflow
    api = ComfyApiWrapper(args.url)

    if args.workflow == "usdu":
        from libs import usdu

        image_data = usdu.usdu(api, args.input, args.upscale_by)
        save_image(image_data, Path(args.output))

    elif args.workflow == "upscale":
        from libs import upscale

        if args.model_name:
            image_data = upscale.upscale(api, args.input, args.model_name)
        else:
            image_data = upscale.upscale(api, args.input)
        save_image(image_data, Path(args.output))

    elif args.workflow == "aurasr":
        from libs import aurasr

        image_data = aurasr.aurasr(api, args.input)
        save_image(image_data, Path(args.output))

    elif args.workflow == "outpaint":
        from libs import outpaint

        image_data = outpaint.outpaint(api, args.input, args.left, args.top, args.right, args.bottom)
        save_image(image_data, Path(args.output))

    elif args.workflow == "zit":
        from libs import zit

        image_data = zit.zit(api, args.prompt, random.randint(2**20, 2**64))
        save_image(image_data, Path(args.output))

    else:
        logging.error(f"unknown workflow {args.workflow}")


if __name__ == "__main__":
    main()
