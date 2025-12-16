# Auto Cut - 智能壁纸切图工具

借助视觉识别AI智能切割图片，产生不同平台可用的壁纸。

设定不同平台和分辨率，以及最大尺寸的核心壁纸。脚本会把核心壁纸提交给AI模型（支持Gemini和OpenAI），要求其判断出适合被切割的尺寸。最后执行切割和缩放。

## 支持的AI提供商

- **Google Gemini** - 默认模型：`gemini-2.5-flash`
- **OpenAI** - 默认模型：`gpt-4o`

程序会自动检测可用的API密钥并选择相应的提供商。如果两者都配置，默认使用Gemini。

## 环境变量配置

使用前需要设置相应的API密钥环境变量：

### Gemini
```bash
export GEMINI_API_KEY=your_gemini_api_key_here
```

### OpenAI
```bash
export OPENAI_API_KEY=your_openai_api_key_here

# 可选：自定义API端点（用于Azure OpenAI、本地模型或代理）
export OPENAI_ENDPOINT=https://your-custom-endpoint.com/v1
```

**自定义端点使用场景：**
- **Azure OpenAI** - 使用Azure托管的OpenAI服务
- **本地模型** - 连接本地部署的OpenAI兼容模型（如vLLM、LocalAI）
- **代理服务器** - 通过代理访问OpenAI API

## 安装依赖

```bash
pip install -e .
# 或使用 uv
uv pip install -e .
```

## 使用方法

### 基本用法（自动检测提供商）
```bash
python main.py your_image.jpg
```

### 指定提供商
```bash
# 使用 Gemini
python main.py --provider gemini your_image.jpg

# 使用 OpenAI
python main.py --provider openai your_image.jpg
```

### 指定模型
```bash
# 使用特定的 Gemini 模型
python main.py --provider gemini --model gemini-2.5-flash your_image.jpg

# 使用特定的 OpenAI 模型
python main.py --provider openai --model gpt-4o-mini your_image.jpg
```

### 指定输出目录
```bash
python main.py --output-dir my_wallpapers your_image.jpg
```

### 批量处理多个图片
```bash
python main.py image1.jpg image2.jpg image3.jpg
```

### 自定义AI分析图片缩放比例
```bash
# 使用30%大小发送给AI（节省更多成本，但可能降低精度）
python main.py --resize-factor 0.3 your_image.jpg

# 使用原图发送（不缩放，最高精度但成本较高）
python main.py --resize-factor 1.0 your_image.jpg
```

### 使用自定义OpenAI端点
```bash
# Azure OpenAI
export OPENAI_ENDPOINT=https://your-resource.openai.azure.com/openai/deployments/your-deployment
export OPENAI_API_KEY=your_azure_key
python main.py --provider openai --model gpt-4o your_image.jpg

# 本地部署的兼容模型（如vLLM）
export OPENAI_ENDPOINT=http://localhost:8000/v1
export OPENAI_API_KEY=dummy  # 本地模型可能不需要真实密钥
python main.py --provider openai --model your-local-model your_image.jpg
```

## CLI 参数说明

### 命令行参数
- `filenames` - 输入图片路径（可指定多个）
- `--provider, -p` - AI提供商选择（gemini 或 openai），不指定则自动检测
- `--model, -m` - 指定模型名称（默认：Gemini用gemini-2.5-flash，OpenAI用gpt-4o）
- `--output-dir, -o` - 输出目录（默认：output_wallpapers）
- `--resize-factor, -r` - AI分析时的图片缩放比例（默认：0.5即50%，用于节省带宽和成本）
- `--log-level, -l` - 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）

### 环境变量
- `GEMINI_API_KEY` - Google Gemini API密钥（使用Gemini时必需）
- `OPENAI_API_KEY` - OpenAI API密钥（使用OpenAI时必需）
- `OPENAI_ENDPOINT` - 自定义OpenAI API端点（可选，用于Azure/本地模型/代理）

## 目标设备

程序会为以下设备生成壁纸：
- iPhone 15 Pro (1179x2556)
- iPad Air (1640x2360)
- MacBook Pro (3024x1964)
- UltraWide (3440x1440)

## 性能优化

### 图片缩放优化
程序默认将图片缩小到50%后再发送给AI进行分析。由于返回的是归一化坐标（0-1范围），缩放不影响精度，但能显著：

- ✅ **降低API成本** - 更小的图片意味着更低的处理费用
- ✅ **加快处理速度** - 上传更快，AI分析更快
- ✅ **节省带宽** - 减少网络传输数据量

实际裁切仍基于原始高分辨率图片，输出质量不受影响。

## 注意事项

使用智能切图的前提是：

1. **最大尺寸核心壁纸大于所有平台分辨率**
2. **主要物体均分布在画面相对中间位置**
3. **画布四周相对空旷**

否则AI无法找出合适切图位置。因此，图片生成时就对提示词有要求。

### 提示词例子

生成图片，比例1:1，油画风格，深色调，蓝色或黑色背景，主题是星空，月亮，地面上有一只英短。月亮和英短出现在画面正中心1/4区域。中心区域和周边连续不割裂。
