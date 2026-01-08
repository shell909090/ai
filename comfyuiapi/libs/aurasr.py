#!/usr/bin/env python3
"""
@date: 2026-01-08
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import json
import logging
from os import path

from libs.workflow import ComfyApiWrapper, ComfyWorkflow

WORKFLOW_STR = """
{
  "1": {
    "inputs": {
      "image": ""
    },
    "class_type": "LoadImage",
    "_meta": {
      "title": "加载图像"
    }
  },
  "2": {
    "inputs": {
      "model_name": "model.safetensors",
      "mode": "4x",
      "reapply_transparency": true,
      "tile_batch_size": 8,
      "device": "default",
      "offload_to_cpu": false,
      "Purge Cache": null,
      "image": [
        "6",
        0
      ]
    },
    "class_type": "AuraSR.AuraSRUpscaler",
    "_meta": {
      "title": "AuraSR Upscaler"
    }
  },
  "3": {
    "inputs": {
      "images": [
        "2",
        0
      ]
    },
    "class_type": "PreviewImage",
    "_meta": {
      "title": "预览图像"
    }
  },
  "5": {
    "inputs": {
      "model_name": "4x-UltraSharp.pth"
    },
    "class_type": "UpscaleModelLoader",
    "_meta": {
      "title": "加载放大模型"
    }
  },
  "6": {
    "inputs": {
      "upscale_model": [
        "5",
        0
      ],
      "image": [
        "1",
        0
      ]
    },
    "class_type": "ImageUpscaleWithModel",
    "_meta": {
      "title": "使用模型放大图像"
    }
  }
}
"""


def aurasr(api: ComfyApiWrapper, image_filepath: str, model_name: str ="4x-UltraSharp.pth") -> bytes:
    """
    使用模型进行图片超分

    该方法使用纯模型超分，不进行重绘，直接放大2倍。适用于快速放大图片。

    Args:
        api: ComfyUI API wrapper实例
        image_filepath: 输入图片文件路径
        model_name: 可选RealESRGAN_x2.pth, RealESRGAN_x4.pth, 4x-UltraSharp.pth三种。

    Returns:
        超分后的图片字节数据（PNG格式），分辨率为原图的2倍

    Raises:
        AssertionError: 如果返回的图片数量不是1张
    """
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))

    logging.info(f"upload image {image_filepath}")
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt["subfolder"], rslt["name"])
    logging.debug(f"Server side filepath: {server_filepath}")

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("加载放大模型", "model_name", model_name)

    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))
