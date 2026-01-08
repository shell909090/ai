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
├── libs/                 # 公共库和workflow模块
│   ├── __init__.py       # 模块导出
│   ├── libs.py           # 公共库函数
│   ├── zit.py            # z-image-turbo图片生成workflow
│   ├── usdu.py           # Ultimate SD Upscale超分workflow
│   ├── upscale.py        # 2倍模型超分workflow (RealESRGAN)
│   ├── aurasr.py         # 4倍模型超分workflow (AuraSR)
│   └── outpaint.py       # 扩图workflow
├── wf.py                 # workflow入口脚本
├── gen_images.py         # 批量生成脚本 (Phase 1)
├── upscale.py            # 批量超分脚本 (Phases 2-4)
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

#### 模型超分 (libs/upscale.py)
- **Upscale Model**: `RealESRGAN_x2.pth` (2倍放大)
- **Upscale Model**: `RealESRGAN_x4.pth` (4倍放大)
- **Upscale Model**: `4x-UltraSharp.pth` (4倍放大)

#### AuraSR超分 (libs/aurasr.py)
- **Upscale Model**: `Aura-SR/model.safetensors` (4倍放大)
- **GAN Model**: `4x-UltraSharp.pth`

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
- `4x-UltraSharp.pth` - 4倍超分辨率模型 (用于usdu.py和aurasr.py)
  - [HuggingFace下载](https://huggingface.co/Kim2091/UltraSharp/blob/main/4x-UltraSharp.pth)
- `RealESRGAN_x2.pth` - 2倍超分辨率模型 (用于upscale.py)
  - [HuggingFace下载](https://huggingface.co/ai-forever/Real-ESRGAN/blob/main/RealESRGAN_x2.pth)
- `RealESRGAN_x4.pth` - 4倍超分辨率模型 (用于upscale.py)
  - [HuggingFace下载](https://huggingface.co/ai-forever/Real-ESRGAN/blob/main/RealESRGAN_x4.pth)
- `sd_xl_base_1.0.safetensors` - SDXL基础模型
  - [HuggingFace下载](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/sd_xl_base_1.0.safetensors)
- `sd_xl_base_1.0_inpainting_0.1.safetensors` - SDXL修复模型
  - [HuggingFace下载](https://huggingface.co/benjamin-paine/sd-xl-alternative-bases/blob/main/sd_xl_base_1.0_inpainting_0.1.safetensors)
- `SDXL/controlnet-tile-sdxl-1.0/diffusion_pytorch_model.safetensors` - ControlNet瓦片模型
  - [HuggingFace下载](https://huggingface.co/xinsir/controlnet-tile-sdxl-1.0/blob/main/diffusion_pytorch_model.safetensors)
- `SDXL/sdxl_vae.safetensors` - SDXL VAE
  - [HuggingFace下载](https://huggingface.co/stabilityai/sdxl-vae/blob/main/sdxl_vae.safetensors)
- `Aura-SR/model.safetensors` - AuraSR v2
  - [HuggingFace下载](https://huggingface.co/fal/AuraSR-v2/blob/main/model.safetensors)

## 使用方法

### 批量生成壁纸

批量生成壁纸采用两步工作流：

#### 第一步：生成基础图片 (gen_images.py)

```bash
# 为所有设备生成基础图片
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ -p pixels.csv

# 生成默认分辨率（1024x1024）
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/

# 每个变奏生成多个批次
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ -p pixels.csv -b 3

# 禁用超分，直接生成目标分辨率（可能影响大分辨率图片质量）
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ -p pixels.csv --upscale-mode none

# 生成PNG并转换为JPG（仅针对直接生成的最终图片）
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ -p pixels.csv -j
```

**gen_images.py 命令行参数**：
- `-u/--url`: ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)
- `-t/--theme`: 主题文件路径（必需）
- `-v/--variations`: 变奏文件路径（必需）
- `-o/--output-dir`: 输出目录（必需）
- `-p/--pixels-csv`: 设备分辨率CSV文件（可选）
- `-b/--batches`: 每个变奏生成的批次数（默认1）
- `-j/--jpg`: 将PNG转换为JPG格式（仅对直接生成的最终图片有效）
- `--upscale-mode`: 超分模式，可选值：
  - `auto`（默认）：智能选择，factor≤2用upscale2x，factor>2用aurasr
  - `upscale2x`：锁定使用upscale + RealESRGAN_x2.pth (2倍放大)
  - `upscale4x`：锁定使用upscale + RealESRGAN_x4.pth (4倍放大)
  - `aurasr`：锁定使用AuraSR (4倍放大)
  - `usdu`：锁定使用Ultimate SD Upscale
  - `none`：禁用超分，直接生成目标分辨率

**输出文件**：
- 分辨率 ≤ 1.5M像素：直接生成最终图片 `{counter:03d}_{batch:02d}_{device_id}.png`
- 分辨率 > 1.5M像素：生成基础图片 `{counter:03d}_{batch:02d}_base_{width}x{height}.png`

#### 第二步：超分放大 (upscale.py)

生成基础图片后，可以浏览检查。如果不满意，删除对应的base图片重新生成。然后运行upscale.py进行超分放大：

```bash
# 超分所有基础图片
./upscale.py -u $API -o output/ -p pixels.csv

# 转换为JPG格式
./upscale.py -u $API -o output/ -p pixels.csv -j

# 保留中间文件（原图和放大图）用于调试
./upscale.py -u $API -o output/ -p pixels.csv --keep-intermediates

# 强制使用特定超分方法
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode aurasr     # 锁定AuraSR (4x)
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode upscale2x  # 锁定RealESRGAN 2x
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode upscale4x  # 锁定RealESRGAN 4x
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode usdu       # 锁定USDU
```

**upscale.py 命令行参数**：
- `-u/--url`: ComfyUI API URL (或从环境变量COMFYUI_API_URL读取，必需)
- `-o/--output-dir`: 输出目录（包含base images，必需）
- `-p/--pixels-csv`: 设备分辨率CSV文件（必需，用于确定目标分辨率）
- `-j/--jpg`: 将最终PNG转换为JPG格式
- `--upscale-mode`: 超分模式（auto/upscale2x/upscale4x/aurasr/usdu，默认auto）
- `--keep-intermediates`: 保留中间文件（原图和放大图），默认会自动清理

**输出文件**：
- 最终图片：`{counter:03d}_{batch:02d}_{device_id}.png`（或 `{counter:03d}_{batch:02d}.png` 无设备ID时）
- 中间文件（--keep-intermediates时保留）：
  - 基础图片：`{counter:03d}_{batch:02d}_base_{width}x{height}.png`
  - 放大图片：`{counter:03d}_{batch:02d}_upscaled_{method}_{width}x{height}.png`

#### 完整工作流示例

```bash
# 1. 设置API URL
export COMFYUI_API_URL=http://192.168.1.1:8188/

# 2. 生成基础图片
./gen_images.py -t theme.txt -v variations.txt -o output/ -p pixels.csv -b 3

# 3. 检查基础图片，删除不满意的
ls output/*_base_*.png

# 4. 超分放大并转换为JPG
./upscale.py -o output/ -p pixels.csv -j

# 5. 查看最终图片
ls output/*.png | grep -v base | grep -v upscaled
```

### 使用独立workflow

```bash
# 生成图片
./wf.py --workflow zit --prompt "主题描述" --output output.png

# 超分（Ultimate SD Upscale）
./wf.py --workflow usdu --input input.png --output output.png --upscale-by 2.0

# 模型超分（RealESRGAN，支持指定模型）
./wf.py --workflow upscale --input input.png --output output.png  # 默认使用RealESRGAN_x2.pth
./wf.py --workflow upscale --input input.png --output output.png -m RealESRGAN_x4.pth  # 使用4x模型

# 模型超分（AuraSR，4倍放大）
./wf.py --workflow aurasr --input input.png --output output.png

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
make test-upscale     # 测试RealESRGAN超分 (2倍)
make test-aurasr      # 测试AuraSR超分 (4倍)
make test-usdu        # 测试Ultimate SD Upscale
make test-outpaint    # 测试扩图
make test-gen-images  # 测试批量生成

# 清理测试输出
make clean
```

测试结果保存在 `test_output/` 目录。

**测试设备配置** (`test_pixels.csv`)：
- `phone` (1080×1920)：竖屏，2.07M像素，factor≈1.40，使用upscale2x超分
- `tablet` (1536×2048)：竖屏，3.15M像素，factor≈1.45，使用upscale2x超分
- `desktop` (1920×1080)：横屏，2.07M像素，factor≈1.18，使用upscale2x超分
- `4k` (3840×2160)：横屏，8.29M像素，factor≈2.35，**使用aurasr超分**

4K设备与desktop成2倍关系，专门用于测试aurasr超分流程（factor>2）。

## 核心逻辑

### 两步工作流程

#### Phase 1: gen_images.py - 生成基础图片

1. 从`theme.txt`读取主题提示词
2. 从`variations.txt`读取变奏（每行一个）
3. 主题+变奏混合生成最终提示词
4. 每个提示词分配一个序列ID（counter）
5. 每个提示词可生成多个批次（batch），通过`--batches`参数指定
6. 每个序列ID的每个批次生成一个随机数种子
7. 对每个设备分辨率：
   - 如果总像素 ≤ 1.5M：直接生成最终图片
   - 如果总像素 > 1.5M：生成base图片供超分使用
8. 文件命名：
   - 最终图片：`{counter:03d}_{batch:02d}_{device_id}.png`
   - Base图片：`{counter:03d}_{batch:02d}_base_{width}x{height}.png`

#### Phases 2-4: upscale.py - 批量超分处理

1. **发现base images**：扫描输出目录中的 `*_base_*.png` 文件
2. **重建任务列表**：根据base images和目标分辨率构建超分任务
3. **Phase 2 - upscale2x超分**：批量处理所有upscale2x任务（auto模式，factor≤2）
4. **Phase 2b - upscale4x超分**：批量处理upscale4x任务（如果使用--upscale-mode upscale4x）
5. **Phase 2c - AuraSR超分**：批量处理AuraSR任务（auto模式，factor>2或--upscale-mode aurasr）
6. **Phase 3 - USDU超分**：批量处理USDU任务（如果使用--upscale-mode usdu）
7. **Phase 4 - 裁切适配**：使用PIL ImageOps.fit将放大图裁切到目标尺寸
8. **清理**：删除中间文件（除非使用--keep-intermediates）

两步分离的优势：
- 可以在超分前检查base images，删除不满意的图片
- 支持断点续传：如果upscale中断，可以继续执行
- 避免重复生成：只需重新运行upscale.py即可调整超分参数

#### 智能分辨率处理

**临界尺寸**：1.5M像素 (1.5×1024×1024)

**分辨率桶**：为避免频繁切换GPU运算，所有生成分辨率会向上取整到64的倍数。例如：
- 1555×1011, 1556×1010, 1559×1008 都会规约到 1600×1024
- 这样可以将多个相近分辨率合并到同一个"分辨率桶"，减少重复计算

**超分模式**：

1. **auto（智能模式，默认）**：
   - 总像素 ≤ 1.5M：直接生成目标分辨率
   - 总像素 > 1.5M：等比例缩放到1.5M（并规约到分辨率桶），根据放大倍率智能选择超分方法
     - 放大倍率 ≤ 2：使用upscale2x（纯GAN，2倍超分）
     - 放大倍率 > 2：使用aurasr（GAN+图像空间重绘，4倍超分）
   - 缩放算法：保持宽高比，width × height = 1.5M，然后向上取整到64的倍数
   - 放大倍率计算：factor = max(目标width/原图width, 目标height/原图height)
   - 裁切算法：使用PIL ImageOps.fit，保持放大图长宽比，缩放至能覆盖目标尺寸的最小尺寸，居中裁切
   - 示例：3840×2160 (8.3M) → 1536×896（桶化，1.38M） → factor=max(3840/1536, 2160/896)=2.5 → 使用aurasr放大4倍 → 裁切到3840×2160

2. **upscale2x（锁定RealESRGAN 2x）**：
   - 所有超过1.5M的图片均使用upscale + RealESRGAN_x2.pth（纯GAN，2倍超分）
   - 速度最快，适合放大倍率≤2的场景

3. **upscale4x（锁定RealESRGAN 4x）**：
   - 所有超过1.5M的图片均使用upscale + RealESRGAN_x4.pth（纯GAN，4倍超分）
   - 速度快，适合放大倍率≤4的场景

4. **aurasr（锁定AuraSR）**：
   - 所有超过1.5M的图片均使用aurasr（4倍超分，带图像空间重绘）
   - 速度快，效果好，推荐用于factor>2的场景

5. **usdu（锁定USDU）**：
   - 所有超过1.5M的图片均使用Ultimate SD Upscale（GAN+SD重绘）
   - 速度较慢，但支持可变倍率，适合需要高质量重绘的大倍率放大

6. **none（禁用超分）**：
   - 直接使用目标分辨率生成图片
   - 优点：生成速度快，无需超分处理
   - 缺点：大分辨率（>1.5M像素）可能出现图片扭曲、断肢等质量问题

**超分缓存优化**：
- 多个设备可能共享同一个放大图（当它们的原图和放大参数相同时）
- 放大图以 `{序号}_{批次}_upscaled_{方法}_{宽}x{高}.png` 命名
- 处理超分任务前先检查缓存，避免重复计算
- 例如：phone和tablet都需要1536×896的基础图放大2倍，只需upscale一次

**断点续传**：
- 检查临时基础图片和放大图是否已存在
- 存在则跳过生成，直接使用现有文件
- 支持中断后继续执行

**中间文件清理**：
- 默认自动清理所有中间文件（原图和放大图）
- 使用 `--keep-intermediates` 保留中间文件用于调试或重复使用

#### 关键特性

- 同一counter+batch的所有设备使用相同seed，确保内容一致
- 支持多批次生成，提供更多变化
- 自动跳过已存在的最终文件
- 断点续传：跳过已生成的基础图片
- 批量超分：避免频繁切换模型，提升性能
- 自动清理：超分完成后删除临时文件

## 代码规范

1. 使用logging模块处理所有日志输出
2. 每个workflow独立为一个Python文件，位于libs/目录下
3. workflow JSON以字符串形式嵌入Python代码（WORKFLOW_STR常量）
4. 提供函数接口供外部调用
5. 公共逻辑放入libs/libs.py
6. 所有函数都包含完整的类型注解（Type Annotations）
7. 所有公共函数都包含详细的docstring文档（参数、返回值、异常）
8. 使用ruff进行静态检查，McCabe复杂度阈值为10

## API文档

### libs/libs.py 公共函数

**图片I/O**:
- `save_image(image_data: bytes, output_filepath: Path) -> None`: 保存图片为PNG
- `convert_to_jpg(png_filepath: Path, quality: int = 95) -> None`: PNG转JPG

**设备分辨率**:
- `get_all_devices(pixels_csv: str) -> list[dict]`: 读取设备列表

### Workflow模块函数

**libs/zit.py**:
- `zit(api: ComfyApiWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes`: 生成图片

**libs/upscale.py**:
- `upscale(api: ComfyApiWrapper, image_filepath: str, model_name: str = "RealESRGAN_x2.pth") -> bytes`: 模型超分（支持RealESRGAN_x2/x4, 4x-UltraSharp）

**libs/aurasr.py**:
- `aurasr(api: ComfyApiWrapper, image_filepath: str) -> bytes`: AuraSR超分（4倍）

**libs/usdu.py**:
- `usdu(api: ComfyApiWrapper, image_filepath: str, upscale_by: float) -> bytes`: Ultimate SD Upscale超分

**libs/outpaint.py**:
- `outpaint(api: ComfyApiWrapper, image_filepath: str, left: int, top: int, right: int, bottom: int) -> bytes`: 图片扩展

所有函数都包含完整的类型注解和docstring文档。可通过 `from libs import zit, upscale, aurasr, usdu, outpaint` 导入使用。

## 许可证

BSD-3-Clause
