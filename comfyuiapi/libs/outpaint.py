#!/usr/bin/env python3
"""
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

# ruff: noqa: E501
import json
import logging
from os import path

from libs.libs import ComfyApiWrapper, ComfyWorkflow

# sd_xl_base_1.0_inpainting_0.1.safetensors
# SDXL/sdxl_vae.safetensors


WORKFLOW_STR = """
{
  "3": {
    "inputs": {
      "seed": 527148651682568,
      "steps": 40,
      "cfg": 3.5,
      "sampler_name": "ddim",
      "scheduler": "karras",
      "denoise": 1,
      "model": [
        "200",
        0
      ],
      "positive": [
        "6",
        0
      ],
      "negative": [
        "178",
        0
      ],
      "latent_image": [
        "191",
        0
      ]
    },
    "class_type": "KSampler",
    "_meta": {
      "title": "K采样器"
    }
  },
  "6": {
    "inputs": {
      "text": "masterpiece, best quality, high quality, (photorealistic), (realistic)",
      "clip": [
        "107",
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
      "samples": [
        "3",
        0
      ],
      "vae": [
        "195",
        0
      ]
    },
    "class_type": "VAEDecode",
    "_meta": {
      "title": "VAE解码"
    }
  },
  "10": {
    "inputs": {
      "images": [
        "8",
        0
      ]
    },
    "class_type": "PreviewImage",
    "_meta": {
      "title": "预览图像"
    }
  },
  "107": {
    "inputs": {
      "ckpt_name": "sd_xl_base_1.0_inpainting_0.1.safetensors"
    },
    "class_type": "CheckpointLoaderSimple",
    "_meta": {
      "title": "Checkpoint加载器（简易）"
    }
  },
  "146": {
    "inputs": {
      "image": ""
    },
    "class_type": "LoadImage",
    "_meta": {
      "title": "加载图像"
    }
  },
  "178": {
    "inputs": {
      "text": "paintings,sketches,text,watermark,(worst quality:2),(low quality:2),(normal quality:2),lowres,((monochrome)),((grayscale)),acnes,age spot,glans,skin spots,acnes,skin blemishes,age spot,glans,extra fingers,fewer fingers,strange fingers,bad hand,(bad_prompt:0.8),LOGO",
      "clip": [
        "107",
        1
      ]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {
      "title": "CLIP文本编码"
    }
  },
  "186": {
    "inputs": {
      "left": 0,
      "top": 0,
      "right": 0,
      "bottom": 0,
      "feathering": 20,
      "image": [
        "146",
        0
      ]
    },
    "class_type": "ImagePadForOutpaint",
    "_meta": {
      "title": "外补画板"
    }
  },
  "191": {
    "inputs": {
      "grow_mask_by": 6,
      "pixels": [
        "186",
        0
      ],
      "vae": [
        "195",
        0
      ],
      "mask": [
        "186",
        1
      ]
    },
    "class_type": "VAEEncodeForInpaint",
    "_meta": {
      "title": "VAE编码（局部重绘）"
    }
  },
  "195": {
    "inputs": {
      "vae_name": "SDXL/sdxl_vae.safetensors"
    },
    "class_type": "VAELoader",
    "_meta": {
      "title": "加载VAE"
    }
  },
  "200": {
    "inputs": {
      "weight": 1,
      "start_at": 0,
      "end_at": 1,
      "weight_type": "standard",
      "model": [
        "201",
        0
      ],
      "ipadapter": [
        "201",
        1
      ],
      "image": [
        "146",
        0
      ]
    },
    "class_type": "IPAdapter",
    "_meta": {
      "title": "IPAdapter"
    }
  },
  "201": {
    "inputs": {
      "preset": "PLUS (high strength)",
      "model": [
        "107",
        0
      ]
    },
    "class_type": "IPAdapterUnifiedLoader",
    "_meta": {
      "title": "IPAdapter Unified Loader"
    }
  }
}
"""


def outpaint(api: ComfyApiWrapper, image_filepath: str, left: int, top: int, right: int, bottom: int) -> bytes:
    """
    使用SDXL inpainting模型进行图片扩展（outpainting）

    在图片四周扩展指定像素，使用AI填充扩展区域，保持画面连贯性。

    Args:
        api: ComfyUI API wrapper实例
        image_filepath: 输入图片文件路径
        left: 左侧扩展像素数
        top: 顶部扩展像素数
        right: 右侧扩展像素数
        bottom: 底部扩展像素数

    Returns:
        扩展后的图片字节数据（PNG格式）

    Raises:
        AssertionError: 如果返回的图片数量不是1张
    """
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))

    logging.info(f"upload image {image_filepath}")
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt["subfolder"], rslt["name"])
    logging.info(f"Server side filepath: {server_filepath}")

    wf.set_node_param("加载图像", "image", server_filepath)
    wf.set_node_param("外补画板", "left", left)
    wf.set_node_param("外补画板", "top", top)
    wf.set_node_param("外补画板", "right", right)
    wf.set_node_param("外补画板", "bottom", bottom)

    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))
