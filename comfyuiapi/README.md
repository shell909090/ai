# ComfyUI Wallpaper Generation Toolkit

AI壁纸生成工具集，基于ComfyUI的图像生成工作流，支持批量生成多设备分辨率壁纸。

## 流程

首先思考一个主题，并写出描述词。然后用这个主题，借助AI大模型，生成不同的描述变化。

例如主题是：“18岁亚裔女性，扎高马尾，黑发，细腰，长腿，邻家女孩。”。

可以向AI提问：“我的主题是“18岁亚裔女性，扎高马尾，黑发，细腰，长腿，邻家女孩。”请为我生成24条该女性的动作和场景描述的提示词，用于AI图像生成。每个月份两条，一条城市主题，一条乡村主题。穿着，背景和色调，必须符合这个月份当地的天气。中文生成。一行一条，输出纯文本格式。输出仅包含描述。输出无需包含主题。输出描述必须详细。输出必须包含详细的衣着，包括上下身穿着，首饰（如有）。输出必须包括环境，照片风格，动作神态，表情，取景范围。”

随后使用主题+变奏，批量生成图片。ZIT会保持生成对象间近似一致。不一致或不好看的，丢弃即可。

默认生成1024x1024分辨率。其他分辨率可以参考`test_pixels.csv`文件。

## 特性

- 使用z-image-turbo模型快速生成高质量图片
- 支持批量生成：根据主题和变奏自动生成多张图片
- 多设备适配：直接生成原始设备分辨率，保持宽高比
- 多种workflow：图片生成、超分、扩图
- 模块化架构：每个workflow独立封装为Python模块
- 完整测试：Makefile提供所有workflow的自动化测试

## 项目结构

```
.
├── libs.py               # 公共库函数
├── wf.py                 # workflow入口脚本
├── zit.py                # z-image-turbo图片生成workflow
├── usdu.py               # Ultimate SD Upscale超分workflow
├── upscale.py            # 2倍模型超分workflow (RealESRGAN)
├── outpaint.py           # 扩图workflow
├── gen-images.py         # 批量生成脚本
├── Makefile              # 测试自动化
├── theme.txt             # 主题提示词
├── variations.txt        # 变奏提示词（每行一个）
├── pixels.csv            # 设备分辨率表
├── test_theme.txt        # 测试用主题
├── test_variations.txt   # 测试用变奏
├── test_pixels.csv       # 测试用设备表
└── CLAUDE.md             # 项目开发文档
```

## 安装

### 使用uv（推荐）

```bash
uv sync
```

### 使用pip

```bash
pip install comfy-api-simplified pillow websockets
```

## 配置

### 设置ComfyUI API地址

```bash
export COMFYUI_API_URL=http://192.168.1.1:8188/
```

### 设备分辨率表格式（pixels.csv）

```csv
device_id,width,height
iphone_15_16,1179,2556
win_hd_monitor,1920,1080
mac_retina,2880,1800
```

### 必需的ComfyUI模型

项目使用以下ComfyUI模型，需要预先下载并放置在ComfyUI的models目录：

#### z-image-turbo 图片生成 (zit.py)
- **CLIP**: `qwen_3_4b.safetensors`
- **VAE**: `ae.safetensors`
- **Diffusion Model**: `z_image_turbo_bf16_nsfw_v2.safetensors`

#### Ultimate SD Upscale 超分 (usdu.py)
- **Upscale Model**: `4x-UltraSharp.pth`
- **SDXL Checkpoint**: `sd_xl_base_1.0.safetensors`
- **ControlNet**: `SDXL/controlnet-tile-sdxl-1.0/diffusion_pytorch_model.safetensors`

#### 2倍模型超分 (upscale.py)
- **Upscale Model**: `RealESRGAN_x2.pth`

#### 图片扩展 (outpaint.py)
- **SDXL Inpainting**: `sd_xl_base_1.0_inpainting_0.1.safetensors`
- **VAE**: `SDXL/sdxl_vae.safetensors`

**模型清单汇总**：
- `qwen_3_4b.safetensors` - CLIP文本编码器
  - [HuggingFace下载](https://huggingface.co/Comfy-Org/z_image_turbo/blob/main/split_files/text_encoders/qwen_3_4b.safetensors)
- `ae.safetensors` - VAE编码器
  - [HuggingFace下载](https://huggingface.co/Comfy-Org/z_image_turbo/blob/main/split_files/vae/ae.safetensors)
- `z_image_turbo_bf16_nsfw_v2.safetensors` - Z-Image Turbo扩散模型
  - [HuggingFace下载 (标准bf16版本)](https://huggingface.co/Comfy-Org/z_image_turbo/blob/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors)
  - [HuggingFace下载](https://huggingface.co/tewea/z_image_turbo_bf16_nsfw/blob/main/z_image_turbo_bf16_nsfw_v2.safetensors)
- `4x-UltraSharp.pth` - 4倍超分辨率模型 (用于usdu.py)
  - [HuggingFace下载](https://huggingface.co/Kim2091/UltraSharp/blob/main/4x-UltraSharp.pth)
- `RealESRGAN_x2.pth` - 2倍超分辨率模型 (用于upscale.py)
  - [HuggingFace下载](https://huggingface.co/ai-forever/Real-ESRGAN/blob/main/RealESRGAN_x2.pth)
- `sd_xl_base_1.0.safetensors` - SDXL基础模型
  - [HuggingFace下载](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors)
- `sd_xl_base_1.0_inpainting_0.1.safetensors` - SDXL修复模型
  - [HuggingFace下载](https://huggingface.co/benjamin-paine/sd-xl-alternative-bases/blob/main/sd_xl_base_1.0_inpainting_0.1.safetensors)
- `SDXL/controlnet-tile-sdxl-1.0/diffusion_pytorch_model.safetensors` - ControlNet瓦片模型
  - [HuggingFace下载](https://huggingface.co/xinsir/controlnet-tile-sdxl-1.0/blob/main/diffusion_pytorch_model.safetensors)
- `SDXL/sdxl_vae.safetensors` - SDXL VAE
  - [HuggingFace下载](https://huggingface.co/stabilityai/sdxl-vae/blob/main/sdxl_vae.safetensors)

## 使用方法

### 批量生成壁纸

```bash
# 为所有设备生成壁纸
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv

# 生成默认分辨率（1024x1024）
./gen-images.py -t theme.txt -v variations.txt -o output/

# 每个变奏生成多个批次
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv --batches 3

# 生成PNG并自动转换为JPG
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv --jpg

# 禁用大分辨率超分功能（直接生成原始分辨率，可能影响质量）
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv --no-upscale
```

生成的文件命名规则：
- 有设备表：`{序号:03d}_{批次:02d}_{device_id}.png`
- 无设备表：`{序号:03d}_{批次:02d}.png`
- 如果使用`--jpg`参数，会同时生成`.png`和`.jpg`文件

例如：`000_00_iphone_15_16.png`、`000_01_iphone_15_16.png`、`001_00_win_hd_monitor.png`

**命令行参数说明**：
- `-t/--theme`: 主题文件路径
- `-v/--variations`: 变奏文件路径
- `-o/--output-dir`: 输出目录
- `-p/--pixels-csv`: 设备分辨率CSV文件（可选）
- `-b/--batches`: 每个变奏生成的批次数（默认1）
- `-j/--jpg`: 将PNG转换为JPG格式
- `--no-upscale`: 禁用大分辨率超分功能（默认启用）

### 使用独立workflow

```bash
# 生成图片
./wf.py --workflow zit --prompt "主题描述" --output output.png

# 超分（Ultimate SD Upscale）
./wf.py --workflow usdu --input input.png --output output.png --upscale-by 2.0

# 模型超分（2倍，RealESRGAN）
./wf.py --workflow upscale --input input.png --output output.png

# 扩图
./wf.py --workflow outpaint --input input.png --output output.png --left 100 --right 100
```

### 运行测试

项目包含完整的Makefile测试套件：

```bash
# 查看所有可用测试
make help

# 运行所有workflow测试
make test

# 运行单个workflow测试
make test-zit         # 测试图片生成
make test-upscale     # 测试2倍超分 (RealESRGAN)
make test-usdu        # 测试Ultimate SD Upscale
make test-outpaint    # 测试扩图
make test-gen-images  # 测试批量生成

# 清理测试输出
make clean
```

测试结果保存在 `test_output/` 目录。

## 核心逻辑

### gen-images.py工作流程

#### 第一阶段：生成所有基础图片

1. 从`theme.txt`读取主题提示词
2. 从`variations.txt`读取变奏（每行一个）
3. 主题+变奏混合生成最终提示词
4. 每个提示词分配一个序列ID（counter）
5. 每个提示词可生成多个批次（batch），通过`--batches`参数指定
6. 每个序列ID的每个批次生成一个随机数种子
7. 如果指定了分辨率表，为所有设备生成对应分辨率图片
8. 文件命名：`{counter:03d}_{batch:02d}_{device_id}.png`（有设备表）或 `{counter:03d}_{batch:02d}.png`（无设备表）

#### 第二阶段：批量超分处理

所有基础图片生成完成后，统一处理需要超分的图片：
1. 收集所有超分任务
2. 批量调用upscale进行2倍放大（使用RealESRGAN_x2）
3. 使用PIL精确缩放到目标尺寸
4. 保存最终图片
5. 可选转换为JPG格式
6. 自动清理临时文件

#### 智能分辨率处理

**缩放策略**（默认启用）：
- 如果总像素 > 1.5M (1.5×1024×1024)，先生成较小的基础图片，再超分放大
- 缩放算法：循环乘以2/3，直到总像素 ≤ 1M
- 示例：3840×2160 (8.3M) → 2560×1440 (3.7M) → 1707×960 (1.64M) → 1138×640 (0.73M)
- 优点：避免图片扭曲、断肢等问题
- 缺点：需要额外的超分时间

**禁用超分（`--no-upscale`）**：
- 直接使用原始分辨率生成图片
- 优点：生成速度快，无需超分处理
- 缺点：大分辨率（>1.5M像素）可能出现图片质量问题

**断点续传**：
- 检查临时基础图片是否已存在
- 存在则跳过生成，直接使用现有文件
- 支持中断后继续执行

#### 关键特性

- 同一counter+batch的所有设备使用相同seed，确保内容一致
- 支持多批次生成，提供更多变化
- 自动跳过已存在的最终文件
- 断点续传：跳过已生成的基础图片
- 批量超分：避免频繁切换模型，提升性能
- 自动清理：超分完成后删除临时文件

## 代码规范

1. 使用logging模块处理所有日志输出
2. 每个workflow独立为一个Python文件
3. workflow JSON以字符串形式嵌入Python代码
4. 提供函数接口供外部调用
5. 公共逻辑放入libs.py
6. 所有函数都包含完整的类型注解（Type Annotations）
7. 所有公共函数都包含详细的docstring文档（参数、返回值、异常）

## API文档

### libs.py 公共函数

**图片I/O**:
- `read_img_from_byte(image_data: bytes) -> Image.Image`: 从字节数据读取图片
- `save_image(image_data: bytes, output_filepath: Path) -> None`: 保存图片为PNG
- `resize_image(input_filepath: Path, output_filepath: Path, target_width: int, target_height: int) -> None`: 调整图片尺寸
- `convert_to_jpg(png_filepath: Path, quality: int = 95) -> None`: PNG转JPG

**设备分辨率**:
- `get_all_devices(pixels_csv: str) -> list[dict]`: 读取设备列表
- `calculate_generation_size(device_width: int, device_height: int, target_area: int = 1024 * 1024) -> tuple[int, int]`: 计算生成尺寸（保留供其他用途）

### Workflow模块函数

**zit.py**:
- `zit(api: ComfyApiWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes`: 生成图片

**upscale.py**:
- `upscale(api: ComfyApiWrapper, image_filepath: str) -> bytes`: 2倍模型超分（RealESRGAN_x2）

**usdu.py**:
- `usdu(api: ComfyApiWrapper, image_filepath: str, upscale_by: float) -> bytes`: Ultimate SD Upscale超分

**outpaint.py**:
- `outpaint(api: ComfyApiWrapper, image_filepath: str, left: int, top: int, right: int, bottom: int) -> bytes`: 图片扩展

所有函数都包含完整的类型注解和docstring文档。

## 许可证

BSD-3-Clause
