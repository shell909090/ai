# ComfyUI Wallpaper Generation Toolkit

AI壁纸生成工具集，基于ComfyUI的图像生成工作流，支持批量生成多设备分辨率壁纸。

## 特性

- 使用z-image-turbo模型快速生成高质量图片
- 支持批量生成：根据主题和变奏自动生成多张图片
- 多设备适配：自动计算各设备分辨率，保持宽高比
- 智能超分：根据目标分辨率自动选择AI超分或PIL缩放
- 模块化架构：每个workflow独立封装为Python模块

## 项目结构

```
.
├── libs.py          # 公共库函数
├── wf.py            # workflow入口脚本
├── zit.py           # z-image-turbo图片生成workflow
├── usdu.py          # Ultimate SD Upscale超分workflow
├── upscale.py       # 4倍模型超分workflow
├── outpaint.py      # 扩图workflow
├── gen-images.py    # 批量生成脚本
├── resize.py        # 批量调整分辨率脚本
├── theme.txt        # 主题提示词
├── variations.txt   # 变奏提示词（每行一个）
└── pixels.csv       # 设备分辨率表
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
export COMFYUI_API_URL=http://192.168.33.4:8188/
```

### 设备分辨率表格式（pixels.csv）

```csv
device_id,width,height
iphone_15_16,1179,2556
win_hd_monitor,1920,1080
mac_retina,2880,1800
```

## 使用方法

### 批量生成壁纸

```bash
# 为所有设备生成壁纸
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv

# 生成默认分辨率（1024x1024）
./gen-images.py -t theme.txt -v variations.txt -o output/

# 每个变奏生成多个批次
./gen-images.py -t theme.txt -v variations.txt -o output/ --pixels-csv pixels.csv --batches 3
```

生成的文件命名规则：
- 有设备表：`{序号:03d}_{批次:02d}_{device_id}.png`
- 无设备表：`{序号:03d}_{批次:02d}.png`

例如：`000_00_iphone_15_16.png`、`000_01_iphone_15_16.png`、`001_00_win_hd_monitor.png`

### 调整已有图片到多设备分辨率

```bash
# 将output目录的图片调整到所有设备分辨率
./resize.py --input-dir output/ --pixels-csv pixels.csv

# 同时转换为JPG
./resize.py --input-dir output/ --pixels-csv pixels.csv --jpg
```

### 使用独立workflow

```bash
# 生成图片
./wf.py --workflow zit --prompt "主题描述" --output output.png

# 超分（Ultimate SD Upscale）
./wf.py --workflow usdu --input input.png --output output.png --upscale-by 2.0

# 模型超分（4倍）
./wf.py --workflow upscale --input input.png --output output.png

# 扩图
./wf.py --workflow outpaint --input input.png --output output.png --left 100 --right 100
```

## 核心逻辑

### gen-images.py工作流程

1. 从`theme.txt`读取主题提示词
2. 从`variations.txt`读取变奏（每行一个）
3. 主题+变奏混合生成最终提示词
4. 每个提示词分配一个序列ID（counter）
5. 每个提示词可生成多个批次（batch），通过`--batches`参数指定
6. 每个序列ID的每个批次生成一个随机数种子
7. 如果指定了分辨率表，为所有设备生成对应分辨率图片
8. 文件命名：`{counter:03d}_{batch:02d}_{device_id}.png`（有设备表）或 `{counter:03d}_{batch:02d}.png`（无设备表）

关键特性：
- 同一counter+batch的所有设备使用相同seed，确保内容一致
- 支持多批次生成，提供更多变化
- 自动跳过已存在文件
- 生成尺寸保持设备宽高比，总像素约1024x1024

### 分辨率计算策略

生成尺寸计算（libs.py中`calculate_generation_size`）：

```python
aspect_ratio = device_width / device_height
gen_width = int(math.sqrt(1048576 * aspect_ratio))
gen_height = int(math.sqrt(1048576 / aspect_ratio))
```

确保生成图片：
1. 保持设备原始宽高比
2. 总像素数接近1024×1024（SDXL最佳训练尺寸）

### 批量调整策略（resize.py）

智能选择缩放方式：

```python
if device_pixels > gen_pixels:
    # 目标更大 -> AI超分
    upscale_by = math.sqrt(device_pixels / gen_pixels)
    image_data = upscale(api, input_file, upscale_by)
else:
    # 目标更小 -> PIL LANCZOS缩放
    resize_image(input_file, output_file, device_width, device_height)
```

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
- `calculate_generation_size(device_width: int, device_height: int, target_area: int = 1024 * 1024) -> tuple[int, int]`: 计算生成尺寸
- `get_all_devices(pixels_csv: str) -> list[dict]`: 读取设备列表

### Workflow模块函数

**zit.py**:
- `zit(api: ComfyApiWrapper, prompt: str, seed: int, width: int = 1024, height: int = 1024) -> bytes`: 生成图片

**upscale.py**:
- `upscale(api: ComfyApiWrapper, image_filepath: str) -> bytes`: 4倍模型超分

**usdu.py**:
- `usdu(api: ComfyApiWrapper, image_filepath: str, upscale_by: float) -> bytes`: Ultimate SD Upscale超分

**outpaint.py**:
- `outpaint(api: ComfyApiWrapper, image_filepath: str, left: int, top: int, right: int, bottom: int) -> bytes`: 图片扩展

所有函数都包含完整的类型注解和docstring文档。

## 许可证

BSD-3-Clause
