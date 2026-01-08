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
      "image": "013_00_base_1728x960.png"
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
        "1",
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
  }
}
"""


def aurasr(api: ComfyApiWrapper, image_filepath: str) -> bytes:
    """
    使用AuraSR进行图片超分

    该方法使用GAN超分后接图像空间重绘，速度快效果好，固定放大4倍。

    Args:
        api: ComfyUI API wrapper实例
        image_filepath: 输入图片文件路径

    Returns:
        超分后的图片字节数据（PNG格式），分辨率为原图的4倍

    Raises:
        AssertionError: 如果返回的图片数量不是1张
    """
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))

    logging.info(f"upload image {image_filepath}")
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt["subfolder"], rslt["name"])
    logging.debug(f"Server side filepath: {server_filepath}")

    wf.set_node_param("加载图像", "image", server_filepath)

    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))
