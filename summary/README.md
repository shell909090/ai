# Summary

使用 LLM 自动总结各种信息的工具集。

## 技术栈

- **语言**: Python 3.12+
- **框架**: LangChain
- **LLM**: 通过 LiteLLM 支持多种模型
- **包管理**: uv

## 功能

### read_nyt

自动阅读 New York Times 新闻文章并生成中文摘要。

## 安装

使用 uv 管理环境和依赖：

```bash
# 安装依赖
uv sync

# 或者使用 uv pip
uv pip install -e .
```

## 配置

### API 密钥

支持多种 LLM 供应商，按以下优先级选择：

1. **Google Gemini** - 设置 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`
2. **OpenAI** - 设置 `OPENAI_API_KEY`

可选配置自定义 API 端点：

- `GEMINI_BASE_URL` - Gemini API 自定义端点
- `OPENAI_BASE_URL` - OpenAI API 自定义端点

### 模型选择

通过环境变量或命令行参数指定模型：

```bash
# 环境变量
export MODEL=gpt-4o-mini

# 或通过命令行参数
./read_nyt.py --model gpt-4o-mini
```

模型选择原则参考 `../llms.txt`。

### 日志级别

通过环境变量 `LOG_LEVEL` 设置：

```bash
export LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

## 使用方法

### read_nyt

```bash
# 基本用法
./read_nyt.py <article_url1> <article_url2> ...

# 指定模型
./read_nyt.py --model gpt-4o-mini <article_url>

# 保存到文件
./read_nyt.py --output summary.txt <article_url>

# 完整示例
./read_nyt.py \
  --model gpt-4o-mini \
  --output summaries.txt \
  https://www.nytimes.com/2024/01/01/world/example-article.html
```

### 参数说明

- `--model, -m`: 指定 LLM 模型名称（默认：环境变量 `MODEL` 或 `gpt-4o-mini`）
- `--output, -o`: 输出文件路径，摘要将追加到文件末尾
- `rest`: 要处理的文章 URL 列表（位置参数）

## 开发

### 代码规范

项目遵循以下规范：

- **编码规范**: PEP-8
- **类型注解**: 强制执行 Type Annotations
- **文档**: 公有函数必须包含详尽的 Docstrings（Args, Returns, Raises）
- **复杂度**: 函数 McCabe 复杂度控制在 10 以内
- **静态检查**: 使用 ruff 进行代码质量检查
- **日志**: 使用 logging 模块处理日志输出

### 测试和构建

使用 Makefile 控制测试和构建过程（如已配置）。

### Git 规范

- 禁止自动 git 提交
- 每次修改源码后，必要时更新 README.md

## 输出格式

程序输出格式示例：

```
================================================================================
标题: Example Article Title
================================================================================

这里是生成的中文摘要内容...

================================================================================
```

## 错误处理

程序包含完善的错误处理和日志记录：

- HTTP 请求失败会记录详细错误信息
- 文章解析失败会跳过并继续处理下一篇
- LLM 调用异常会被捕获并记录

## 依赖项

核心依赖：

- `httpx` - HTTP 客户端
- `beautifulsoup4` + `lxml` - HTML 解析
- `langchain-openai` - OpenAI LLM 集成
- `langchain-google-genai` - Google Gemini 集成
- `langchain-core` - LangChain 核心功能

## License

BSD-3-Clause

## Author

Shell.Xu <shell909090@gmail.com>
