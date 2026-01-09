# ComfyUI Wallpaper Generation Toolkit

AI壁纸生成工具集，基于ComfyUI的图像生成工作流，支持批量生成多设备分辨率壁纸。

## 流程

首先思考一个主题，并写出描述词。然后用这个主题，借助AI大模型，生成不同的描述变化。

例如主题是：“18岁亚裔女性，扎高马尾，黑发，细腰，长腿，邻家女孩。”。

可以向AI提问：“我的主题是“18岁亚裔女性，扎高马尾，黑发，细腰，长腿，邻家女孩。”请为我生成24条该女性的动作和场景描述的提示词，用于AI图像生成。每个月份两条，一条城市主题，一条乡村主题。穿着，背景和色调，必须符合这个月份当地的天气。中文生成。一行一条，输出纯文本格式。输出仅包含描述。输出无需包含主题。输出描述必须详细。输出必须包含详细的衣着，包括上下身穿着，首饰（如有）。输出必须包括环境，照片风格，动作神态，表情，取景范围。”

随后使用主题+变奏，批量生成图片。ZIT会保持生成对象间近似一致。不一致或不好看的，丢弃即可。

系统使用4个标准分辨率桶（896×1920, 1088×1472, 1536×1024, 1728×960），根据设备宽高比自动匹配。具体设备分辨率可以参考`test_pixels.csv`文件格式。

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

批量生成壁纸采用**两步工作流+4分辨率桶**架构：

#### 第一步：生成基础图片 (gen_images.py)

gen_images.py根据变奏，生成4种标准分辨率的母图（base images），对应4个分辨率桶：

| Bucket | Resolution  | Aspect Ratio | Typical Devices |
|--------|-------------|--------------|-----------------|
| 0      | 896×1920    | < 0.6        | Very tall/narrow phones|
| 1      | 1088×1472   | 0.6-1.15     | Standard phones/tablets (portrait)|
| 2      | 1536×1024   | 1.15-1.65    | Tablets/laptops (landscape)|
| 3      | 1728×960    | ≥ 1.65       | Wide monitors/TVs|

```bash
# 生成4张母图（每个变奏，每个批次）
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/

# 每个变奏生成多个批次
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ -b 3

# 只生成特定分辨率桶（例如只生成横屏）
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ --buckets "2,3"

# 只生成竖屏
./gen_images.py -u $API -t theme.txt -v variations.txt -o output/ --buckets "0,1"
```

**gen_images.py 命令行参数**：
- `-u/--url`: ComfyUI API URL (或从环境变量COMFYUI_API_URL读取)
- `-t/--theme`: 主题文件路径（必需）
- `-v/--variations`: 变奏文件路径（必需）
- `-o/--output-dir`: 输出目录（必需）
- `-b/--batches`: 每个变奏生成的批次数（默认1）
- `--buckets`: 选择生成哪些分辨率桶（默认"0,1,2,3"全部生成）
  - "0"：896×1920（超窄竖屏）
  - "1"：1088×1472（标准竖屏）
  - "2"：1536×1024（标准横屏）
  - "3"：1728×960（超宽横屏）

**输出文件**：
- 母图：`{counter:03d}_{batch:02d}_base_896x1920.png`
- 母图：`{counter:03d}_{batch:02d}_base_1088x1472.png`
- 母图：`{counter:03d}_{batch:02d}_base_1536x1024.png`
- 母图：`{counter:03d}_{batch:02d}_base_1728x960.png`

#### 第二步：超分放大 (upscale.py)

生成母图后，可以浏览检查。如果不满意，删除对应的base图片重新生成。然后运行upscale.py根据设备列表进行超分放大和适配：

```bash
# 查看设备到分辨率桶的映射（不执行超分）
./upscale.py -o output/ -p pixels.csv --show-table

# 超分所有母图并适配到设备分辨率（所有最终图片自动转换为JPG）
./upscale.py -u $API -o output/ -p pixels.csv

# 强制使用特定超分方法
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode aurasr     # 锁定AuraSR (4x)
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode upscale2x  # 锁定RealESRGAN 2x
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode upscale4x  # 锁定RealESRGAN 4x
./upscale.py -u $API -o output/ -p pixels.csv --upscale-mode usdu       # 锁定USDU
```

**upscale.py 命令行参数**：
- `-u/--url`: ComfyUI API URL (或从环境变量COMFYUI_API_URL读取，执行超分时必需)
- `-o/--output-dir`: 输出目录（包含母图，必需）
- `-p/--pixels-csv`: 设备分辨率CSV文件（**必需**，用于设备到分辨率桶的映射）
- `--upscale-mode`: 超分模式（auto/upscale2x/upscale4x/aurasr/usdu，默认auto）
- `--show-table`: 只显示设备到分辨率桶的映射表，不执行超分（无需API URL）

**输出文件**：
- 最终图片（JPG）：`{counter:03d}_{batch:02d}_{device_id}.png`
- 超分图片（保留）：`{counter:03d}_{batch:02d}_upscale2x_{width}x{height}.png` 或 `{counter:03d}_{batch:02d}_aurasr_{width}x{height}.png`
- 母图（保留）：`{counter:03d}_{batch:02d}_base_{width}x{height}.png`

**注意事项**：
- upscale.py不再清理中间文件，所有母图和超分图都会保留
- 如果设备所需的分辨率桶的母图不存在，upscale.py会报错并提示需要生成哪个bucket
- 例如：设备需要bucket 2 (1536×1024)但母图不存在时，错误信息会提示运行 `gen_images.py --buckets 2`

#### 完整工作流示例

```bash
# 1. 设置API URL
export COMFYUI_API_URL=http://192.168.1.1:8188/

# 2. 生成母图（4个标准分辨率）
./gen_images.py -t theme.txt -v variations.txt -o output/ -b 3

# 3. 检查母图，删除不满意的
ls output/*_base_*.png

# 4. 查看设备到分辨率桶的映射
./upscale.py -o output/ -p pixels.csv --show-table

# 5. 超分放大并适配到所有设备分辨率（自动转换为JPG）
./upscale.py -o output/ -p pixels.csv

# 6. 查看最终图片
ls output/*.png | grep -v base | grep -v upscale | grep -v aurasr
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

### 两步工作流程 + 4分辨率桶架构

#### Phase 1: gen_images.py - 生成母图

gen_images.py生成4个标准分辨率的母图（base images），对应全球设备的4个纵横比区间：

**4个分辨率桶**：
- **Bucket 0**: 896×1920 (ar < 0.6) - 超窄竖屏手机
- **Bucket 1**: 1088×1472 (0.6 ≤ ar < 1.15) - 标准竖屏手机/平板
- **Bucket 2**: 1536×1024 (1.15 ≤ ar < 1.65) - 标准横屏平板/笔记本
- **Bucket 3**: 1728×960 (ar ≥ 1.65) - 超宽横屏显示器/电视

**生成流程**：
1. 从`theme.txt`读取主题提示词
2. 从`variations.txt`读取变奏（每行一个）
3. 主题+变奏混合生成最终提示词
4. 每个提示词分配一个序列ID（counter）
5. 每个提示词可生成多个批次（batch），通过`--batches`参数指定
6. 每个序列ID的每个批次生成一个随机数种子
7. 使用相同的seed，生成4张母图（4个标准分辨率）
8. 文件命名：`{counter:03d}_{batch:02d}_base_{width}x{height}.png`

**优势**：
- 简化生成：每个变奏只需生成4张图片，不管有多少设备
- 高效缓存：所有设备共享4张母图
- 灵活选择：可以只生成特定分辨率桶（--buckets参数）

#### Phases 2-4: upscale.py - 超分、裁切、适配

upscale.py将4张母图超分放大，并裁切适配到所有设备分辨率：

**处理流程**：
1. **发现母图**：扫描输出目录中的 `*_base_*.png` 文件
2. **设备映射**：根据设备纵横比，映射到4个分辨率桶
3. **重建任务**：为每个设备生成超分+裁切任务
4. **Phase 2a - upscale2x超分**：批量处理所有upscale2x任务（auto模式，factor≤2）
5. **Phase 2b - upscale4x超分**：批量处理upscale4x任务（如果使用--upscale-mode upscale4x）
6. **Phase 2c - AuraSR超分**：批量处理AuraSR任务（auto模式，factor>2或--upscale-mode aurasr）
7. **Phase 3 - USDU超分**：批量处理USDU任务（如果使用--upscale-mode usdu）
8. **Phase 4 - 裁切适配**：使用PIL ImageOps.fit将超分图裁切到各设备分辨率
9. **JPG转换**：所有最终图片强制转换为JPG格式

**设备到分辨率桶映射示例**：
- iPhone 15 (1179×2556, ar=0.46) → Bucket 0 (896×1920)
- iPad Pro (1668×2388, ar=0.70) → Bucket 1 (1088×1472)
- MacBook Pro (2880×1800, ar=1.60) → Bucket 2 (1536×1024)
- 4K Monitor (3840×2160, ar=1.78) → Bucket 3 (1728×960)

两步分离的优势：
- 可以在超分前检查母图，删除不满意的图片
- 支持断点续传：如果upscale中断，可以继续执行
- 避免重复生成：只需重新运行upscale.py即可调整超分参数
- 设备扩展简单：添加新设备无需重新生成母图

#### 智能分辨率处理

**4分辨率桶架构**：

所有设备根据纵横比（aspect ratio）自动映射到4个标准分辨率桶：

| 纵横比范围 | 分辨率桶 | 典型设备 |
|------------|----------|----------|
| ar < 0.6   | 896×1920  | 超窄竖屏手机 |
| 0.6 ≤ ar < 1.15 | 1088×1472 | 标准竖屏手机/平板 |
| 1.15 ≤ ar < 1.65 | 1536×1024 | 标准横屏平板/笔记本 |
| ar ≥ 1.65 | 1728×960 | 超宽横屏显示器/电视 |

**超分模式**：

1. **auto（智能模式，默认）**：
   - 根据设备分辨率和分辨率桶计算放大倍率：factor = max(device_width/bucket_width, device_height/bucket_height)
   - factor ≤ 2：使用upscale2x（纯GAN，2倍超分）
   - factor > 2：使用aurasr（GAN+图像空间重绘，4倍超分）
   - 裁切算法：使用PIL ImageOps.fit，保持超分图长宽比，缩放至能覆盖目标尺寸的最小尺寸，居中裁切
   - 示例：iPhone 15 (1179×2556, ar=0.46) → Bucket 0 (896×1920) → factor=max(1179/896, 2556/1920)=1.33 → 使用upscale2x放大2倍到1792×3840 → 裁切到1179×2556

2. **upscale2x（锁定RealESRGAN 2x）**：
   - 所有母图均使用upscale + RealESRGAN_x2.pth（纯GAN，2倍超分）
   - 速度最快，适合factor≤2的场景

3. **upscale4x（锁定RealESRGAN 4x）**：
   - 所有母图均使用upscale + RealESRGAN_x4.pth（纯GAN，4倍超分）
   - 速度快，适合factor≤4的场景

4. **aurasr（锁定AuraSR）**：
   - 所有母图均使用aurasr（4倍超分，带图像空间重绘）
   - 速度快，效果好，推荐用于factor>2的场景

5. **usdu（锁定USDU）**：
   - 所有母图均使用Ultimate SD Upscale（GAN+SD重绘）
   - 速度较慢，但支持可变倍率，适合需要高质量重绘的大倍率放大

**超分缓存优化**：
- 同一分辨率桶的所有设备共享同一张超分图
- 超分图以 `{序号}_{批次}_{方法}_{宽}x{高}.png` 命名（注意：无"upscaled"词）
- 处理超分任务前先检查缓存，避免重复计算
- 示例：多个竖屏手机都映射到Bucket 1 (1088×1472)，只需upscale一次到2176×2944

**断点续传**：
- 检查母图和超分图是否已存在
- 存在则跳过生成，直接使用现有文件
- 支持中断后继续执行

**中间文件保留**：
- 所有母图和超分图都会保留，不再自动清理
- 便于调试、重用和扩展新设备

#### 关键特性

- **4分辨率桶架构**：所有设备映射到4个标准分辨率，简化生成流程
- **设备扩展简单**：添加新设备无需重新生成母图，只需运行upscale.py
- **纵横比智能映射**：根据设备aspect ratio自动选择最合适的分辨率桶
- **同一counter+batch使用相同seed**：所有分辨率桶保持内容一致
- **支持多批次生成**：提供更多变化选择
- **自动跳过已存在文件**：支持断点续传
- **批量超分**：避免频繁切换模型，提升性能
- **中间文件保留**：所有母图和超分图都保留，便于调试和重用
- **强制JPG转换**：所有最终设备图片自动转换为JPG格式

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
