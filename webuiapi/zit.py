#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
@date: 2026-01-03
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
'''
import json
import logging
from os import path

from libs import ComfyApiWrapper, ComfyWorkflow

# qwen_3_4b.safetensors
# ae.safetensors
# z_image_turbo_bf16_nsfw_v2.safetensors


WORKFLOW_STR = '''
{
  "39": {
    "inputs": {
      "clip_name": "qwen_3_4b.safetensors",
      "type": "lumina2",
      "device": "default"
    },
    "class_type": "CLIPLoader",
    "_meta": {
      "title": "加载CLIP"
    }
  },
  "40": {
    "inputs": {
      "vae_name": "ae.safetensors"
    },
    "class_type": "VAELoader",
    "_meta": {
      "title": "加载VAE"
    }
  },
  "41": {
    "inputs": {
      "width": 1024,
      "height": 1024,
      "batch_size": 1
    },
    "class_type": "EmptySD3LatentImage",
    "_meta": {
      "title": "空Latent图像（SD3）"
    }
  },
  "42": {
    "inputs": {
      "conditioning": [
        "45",
        0
      ]
    },
    "class_type": "ConditioningZeroOut",
    "_meta": {
      "title": "条件零化"
    }
  },
  "43": {
    "inputs": {
      "samples": [
        "44",
        0
      ],
      "vae": [
        "40",
        0
      ]
    },
    "class_type": "VAEDecode",
    "_meta": {
      "title": "VAE解码"
    }
  },
  "44": {
    "inputs": {
      "seed": 922655339502032,
      "steps": 9,
      "cfg": 1,
      "sampler_name": "res_multistep",
      "scheduler": "simple",
      "denoise": 1,
      "model": [
        "47",
        0
      ],
      "positive": [
        "45",
        0
      ],
      "negative": [
        "42",
        0
      ],
      "latent_image": [
        "41",
        0
      ]
    },
    "class_type": "KSampler",
    "_meta": {
      "title": "K采样器"
    }
  },
  "45": {
    "inputs": {
      "text": "亚裔女性",
      "clip": [
        "39",
        0
      ]
    },
    "class_type": "CLIPTextEncode",
    "_meta": {
      "title": "CLIP文本编码"
    }
  },
  "47": {
    "inputs": {
      "shift": 3,
      "model": [
        "87",
        0
      ]
    },
    "class_type": "ModelSamplingAuraFlow",
    "_meta": {
      "title": "采样算法（AuraFlow）"
    }
  },
  "87": {
    "inputs": {
      "model_name": "z_image_turbo_bf16_nsfw_v2.safetensors",
      "weight_dtype": "fp16",
      "compute_dtype": "default",
      "patch_cublaslinear": false,
      "sage_attention": "disabled",
      "enable_fp16_accumulation": false
    },
    "class_type": "DiffusionModelLoaderKJ",
    "_meta": {
      "title": "Diffusion Model Loader KJ"
    }
  },
  "90": {
    "inputs": {
      "images": [
        "43",
        0
      ]
    },
    "class_type": "PreviewImage",
    "_meta": {
      "title": "预览图像"
    }
  }
}
'''


def zit(api: ComfyApiWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes:
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))

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
