#!/usr/bin/env python3
"""
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

import json
import logging
from os import path

from libs.libs import ComfyApiWrapper, ComfyWorkflow

# 4x-UltraSharp.pth
# sd_xl_base_1.0.safetensors
# SDXL/controlnet-tile-sdxl-1.0/diffusion_pytorch_model.safetensors


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
      "model_name": "4x-UltraSharp.pth"
    },
    "class_type": "UpscaleModelLoader",
    "_meta": {
      "title": "加载放大模型"
    }
  },
  "4": {
    "inputs": {
      "strength": 0.5,
      "start_percent": 0,
      "end_percent": 1,
      "positive": [
        "5",
        0
      ],
      "negative": [
        "6",
        0
      ],
      "control_net": [
        "10",
        0
      ],
      "image": [
        "1",
        0
      ],
      "vae": [
        "8",
        2
      ]
    },
    "class_type": "ControlNetApplyAdvanced",
    "_meta": {
      "title": "应用ControlNet（旧版高级）"
    }
  },
  "5": {
    "inputs": {
      "text": "masterpiece, best quality, high quality, (photorealistic), (realistic), depth of field, highres",
      "clip": [
        "8",
        1
      ]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {
      "title": "CLIP文本编码"
    }
  },
  "6": {
    "inputs": {
      "text": "paintings,sketches,text,watermark,(worst quality:2),(low quality:2),(normal quality:2),lowres,((monochrome)),((grayscale)),acnes,age spot,glans,skin spots,acnes,skin blemishes,age spot,glans,extra fingers,fewer fingers,strange fingers,bad hand,(bad_prompt:0.8),LOGO",
      "clip": [
        "8",
        1
      ]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {
      "title": "CLIP文本编码"
    }
  },
  "8": {
    "inputs": {
      "ckpt_name": "sd_xl_base_1.0.safetensors"
    },
    "class_type": "CheckpointLoaderSimple",
    "_meta": {
      "title": "Checkpoint加载器（简易）"
    }
  },
  "10": {
    "inputs": {
      "control_net_name": "SDXL/controlnet-tile-sdxl-1.0/diffusion_pytorch_model.safetensors"
    },
    "class_type": "ControlNetLoader",
    "_meta": {
      "title": "加载ControlNet模型"
    }
  },
  "13": {
    "inputs": {
      "upscale_by": 2,
      "seed": 0,
      "steps": 20,
      "cfg": 6,
      "sampler_name": "uni_pc",
      "scheduler": "beta",
      "denoise": 0.35,
      "mode_type": "Linear",
      "tile_width": 1024,
      "tile_height": 1024,
      "mask_blur": 8,
      "tile_padding": 32,
      "seam_fix_mode": "None",
      "seam_fix_denoise": 1,
      "seam_fix_width": 64,
      "seam_fix_mask_blur": 8,
      "seam_fix_padding": 16,
      "force_uniform_tiles": true,
      "tiled_decode": false,
      "image": [
        "1",
        0
      ],
      "model": [
        "8",
        0
      ],
      "positive": [
        "4",
        0
      ],
      "negative": [
        "4",
        1
      ],
      "vae": [
        "8",
        2
      ],
      "upscale_model": [
        "2",
        0
      ]
    },
    "class_type": "UltimateSDUpscale",
    "_meta": {
      "title": "Ultimate SD Upscale"
    }
  },
  "14": {
    "inputs": {
      "images": [
        "13",
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


def usdu(api: ComfyApiWrapper, image_filepath: str, upscale_by: float) -> bytes:
    """
    使用Ultimate SD Upscale workflow进行图片超分

    该方法会上传图片到服务器，使用SDXL模型和ControlNet进行高质量超分辨率处理。

    Args:
        api: ComfyUI API wrapper实例
        image_filepath: 输入图片文件路径
        upscale_by: 放大倍数（例如2.0表示放大2倍）

    Returns:
        超分后的图片字节数据（PNG格式）

    Raises:
        AssertionError: 如果返回的图片数量不是1张
    """
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))

    logging.info(f"upload image {image_filepath}")
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt["subfolder"], rslt["name"])
    logging.debug(f"Server side filepath: {server_filepath}")

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("Ultimate SD Upscale", "upscale_by", upscale_by)

    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))
