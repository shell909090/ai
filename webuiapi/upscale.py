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

# 4x-UltraSharp.pth


WORKFLOW_STR = '''
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
  "14": {
    "inputs": {
      "images": [
        "15",
        0
      ]
    },
    "class_type": "PreviewImage",
    "_meta": {
      "title": "预览图像"
    }
  },
  "15": {
    "inputs": {
      "upscale_model": [
        "2",
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
'''


def upscale(api: ComfyApiWrapper, image_filepath: str) -> bytes:
    wf = ComfyWorkflow(json.loads(WORKFLOW_STR))

    logging.info(f'upload image {image_filepath}')
    rslt = api.upload_image(image_filepath)
    server_filepath = path.join(rslt['subfolder'], rslt['name'])
    logging.debug(f'Server side filepath: {server_filepath}')

    wf.set_node_param("加载图像", "image", server_filepath)

    results = api.queue_and_wait_images(wf, "预览图像")
    assert len(results) == 1, f"Expected 1 image, got {len(results)}"
    return next(iter(results.values()))
