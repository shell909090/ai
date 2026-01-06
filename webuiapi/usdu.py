#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
'''
import os
import sys
import argparse
from pathlib import Path

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper

from libs import usdu, save_image


def main():
    parser = argparse.ArgumentParser(description='使用usdu流程提升分辨率')
    parser.add_argument('--url', '-u',
                        default=os.environ.get('COMFYUI_API_URL'),
                        help='ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)')
    parser.add_argument('--workflow', '-w',
                        default='usdu.json',
                        help='ComfyUI Workflow文件 (默认: usdu.json)')
    parser.add_argument('--input', '-i',
                        required=True,
                        help='输入图像文件路径')
    parser.add_argument('--output', '-o',
                        required=True,
                        help='输出图像文件路径')
    parser.add_argument('--upscale-by',
                        type=float,
                        default=2.0,
                        help='放大倍数 (默认: 2.0)')
    args = parser.parse_args()

    if not args.url:
        print("错误: 必须通过--url参数或COMFYUI_API_URL环境变量指定ComfyUI API URL", file=sys.stderr)
        sys.exit(1)

    # 初始化ComfyUI API和Workflow
    api = ComfyApiWrapper(args.url)
    wf = ComfyWorkflowWrapper(args.workflow)

    # 生成图片
    image_data = usdu(api, wf, args.input, args.upscale_by)

    # 保存PNG文件
    save_image(image_data, Path(args.output))


if __name__ == '__main__':
    main()
