# Summary

使用 LLM 自动总结各种信息的工具集。

## 技术栈

- **语言**: Python 3.12+
- **框架**: LangChain + LiteLLM
- **LLM**: 通过 LiteLLM 统一接口支持多种供应商（OpenAI、Google Gemini、Anthropic Claude、Cohere 等）
- **包管理**: uv

## 功能

### read_nyt

自动阅读 New York Times 新闻文章并生成中文摘要。

### read_nyt_rss

自动读取纽约时报中文网 RSS feed，过滤出指定时间范围内（默认24小时）的新闻，并为每篇新闻生成中文摘要，最后汇总到一个文件。

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

**重要**: 使用前必须设置相应的 API 密钥环境变量，程序会在启动时使用 `litellm.validate_environment` 验证环境变量，如果缺失会直接抛出异常。

使用 LiteLLM 统一接口，支持多种 LLM 供应商。LiteLLM 会根据环境变量自动识别供应商：

- **Groq** - 设置 `GROQ_API_KEY` (默认模型使用)
- **OpenAI** - 设置 `OPENAI_API_KEY`
- **Google Gemini** - 设置 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`
- **Anthropic Claude** - 设置 `ANTHROPIC_API_KEY`
- **Cohere** - 设置 `COHERE_API_KEY`
- 更多供应商请参考 [LiteLLM 文档](https://docs.litellm.ai/docs/providers)

可选配置自定义 API 端点（通过 LiteLLM 支持）：

- `OPENAI_API_BASE` - OpenAI API 自定义端点
- 其他供应商端点配置参考 LiteLLM 文档

### 模型选择

通过环境变量或命令行参数指定模型，遵循 LiteLLM 格式：

```bash
# 环境变量（推荐使用 provider/model 格式）
export MODEL=groq/llama-3.3-70b-versatile     # 默认模型
export MODEL=openai/gpt-4o-mini
export MODEL=gemini/gemini-pro
export MODEL=anthropic/claude-3-5-sonnet-20241022

# 或通过命令行参数
./read_nyt.py --model groq/llama-3.3-70b-versatile
./read_nyt.py --model openai/gpt-4o-mini
./read_nyt.py --model gemini/gemini-pro
```

**LiteLLM 模型格式说明**：

- **推荐格式**: `provider/model` (如 `groq/llama-3.3-70b-versatile`、`openai/gpt-4o-mini`、`gemini/gemini-pro`)
- **简化格式**: 对于常见模型，可省略 provider (如 `gpt-4o-mini`)，LiteLLM 会自动识别
- 完整模型列表和格式请参考 [LiteLLM 文档](https://docs.litellm.ai/docs/providers)

模型选择原则参考 `../CLAUDE.md`。

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
  --model groq/llama-3.3-70b-versatile \
  --output summaries.txt \
  https://www.nytimes.com/2024/01/01/world/example-article.html
```

#### read_nyt 参数说明

- `--model, -m`: 指定 LLM 模型名称，遵循 LiteLLM 格式（默认：环境变量 `MODEL` 或 `groq/llama-3.3-70b-versatile`）
- `--output, -o`: 输出文件路径，摘要将追加到文件末尾
- `rest`: 要处理的文章 URL 列表（位置参数）

### read_nyt_rss

```bash
# 基本用法（读取24小时内的新闻）
./read_nyt_rss.py

# 指定模型
./read_nyt_rss.py --model gpt-4o-mini

# 指定输出文件
./read_nyt_rss.py --output my_summary.txt

# 指定时间范围（48小时内）
./read_nyt_rss.py --hours 48

# 指定自定义RSS源
./read_nyt_rss.py --rss-url https://example.com/rss/

# 完整示例
./read_nyt_rss.py \
  --model groq/llama-3.3-70b-versatile \
  --output nyt_daily.txt \
  --hours 24
```

#### read_nyt_rss 参数说明

- `--model, -m`: 指定 LLM 模型名称，遵循 LiteLLM 格式（默认：环境变量 `MODEL` 或 `groq/llama-3.3-70b-versatile`）
- `--output, -o`: 输出文件路径（默认：`nyt_summary.txt`）
- `--hours`: 时间范围（小时），只处理指定时间内的新闻（默认：24）
- `--rss-url`: RSS feed URL（默认：`https://cn.nytimes.com/rss/`）

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

- **API 密钥验证**：启动时使用 `litellm.validate_environment` 验证环境变量，如缺失会立即抛出异常
- **HTTP 请求失败**：会记录详细错误信息
- **文章解析失败**：会跳过并继续处理下一篇
- **LLM 调用异常**：会被捕获并记录

## 依赖项

核心依赖：

- `httpx` - HTTP 客户端
- `beautifulsoup4` + `lxml` - HTML 解析
- `feedparser` - RSS feed 解析
- `langchain-community` - LangChain 社区集成（包含 ChatLiteLLM）
- `langchain-core` - LangChain 核心功能
- `litellm` - 统一的 LLM API 接口（通过 langchain-community 间接依赖）

## License

BSD-3-Clause

## Author

Shell.Xu <shell909090@gmail.com>
