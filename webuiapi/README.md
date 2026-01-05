# 自动壁纸生成脚本

自动壁纸生成由2个AI相关脚本和工作流构成：`gen_images.py`和`resize.py`。基本业务逻辑如下：

1. `gen_images.py`底层使用`zit-gen.py`，但是可以根据设备分辨率表，计算出所需生成的纵横比。此纵横比和设备的目标纵横比等比例，且总像素数接近1Mpx。
2. 筛选和过滤照片，去掉不合适的图片。
3. 使用upscale进行超分辨率处理，将图片调整到各设备的目标分辨率。
   3.1. 如果目标分辨率大于生成分辨率，使用AI超分辨率(upscale)。由于upscale会自动放大4倍，随后只需要缩小就好。
   3.2. 如果目标分辨率小于等于生成分辨率，使用PIL缩小。
4. 筛选和过滤照片，去掉不合适照片。

# zit-gen

使用`z-image-turbo.json`流程，生成图片。提示词包括两部分：主题和变奏。脚本拼合主题和变奏，输出生成文件到特定目录。

支持以下几个参数：

* ComfyUI API URL: 支持从命令行输入（--url/-u），或从环境变量COMFYUI_API_URL读取。
* ComfyUI Workflow: 支持从命令输入（--workflow/-w），默认为`z_image_turbo.json`。
* 主题: 一个文件，支持从命令行指定（--theme/-t，必需）。
* 变奏: 一个文本文件，支持从命令行指定（--variations/-v，必需）。每行一个变奏。
* 输出目录: 一个目录（--output-dir/-o，必需），如果不存在则创建。输出文件以`{序号}_{宽}x{高}.png`格式命名。
* 宽度和高度: 手动指定图像尺寸（--width和--height），默认均为1024。

# usdu

使用`ultimate-sd-upscale.json`流程，进行超分辨率处理。

支持两种模式：

* **批量模式**: 使用--input-dir和--pixels-csv批量处理所有设备分辨率
* **单文件模式**: 使用--input和--output处理单个文件

参数说明：

* ComfyUI API URL: 支持从命令行输入（--url/-u），或从环境变量COMFYUI_API_URL读取。
* ComfyUI Workflow: 支持从命令输入（--workflow/-w），默认为`ultimate-sd-upscale.json`。
* 单文件模式参数:
  - --input/-i: 输入文件
  - --output/-o: 输出文件
  - --upscale-by: 放大比例（默认2.0）
* 批量模式参数:
  - --input-dir: 输入目录
  - --pixels-csv: 设备分辨率CSV文件
  - --jpg/-j: 同时生成JPG格式

# outpaint

使用`sdxl-outpaint.json`流程，进行外扩图处理。

参数说明：

* ComfyUI API URL: 支持从命令行输入（--url/-u），或从环境变量COMFYUI_API_URL读取。
* ComfyUI Workflow: 支持从命令输入（--workflow/-w），默认为`sdxl-outpaint.json`。
* --input/-i: 输入文件（必需）
* --output/-o: 输出文件（必需）
* --left, --top, --right, --bottom: 四边扩图像素数（默认均为0）
