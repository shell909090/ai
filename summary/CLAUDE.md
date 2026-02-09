# 项目核心定位

功能：总结各种信息。
技术栈：Python, langchain, litellm, uv (包管理)。

# 代码规范

* 禁止自动git提交
* 编码规范遵循PEP-8。
* 强制执行 Type Annotations。
* 公有函数必须包含详尽的 Docstrings (Args, Returns, Raises)。
* 环境使用uv管理
* 函数的McCabe复杂度尽量不要超过10。
* 使用 ruff 进行静态检查，配置 McCabe 复杂度阈值为 10。
* 测试和构建过程使用Makefile控制
* 每次修改源码后，如果需要，更新README.md。
* 删除无用代码，删除头部无效import
* 使用logging处理日志。

# read_nyt

使用llm自动阅读new york time新闻，生成摘要。

llm的选择原则参考../CLAUDE.md。

支持多种供应商。

# read_nyt_rss

## 背景和目标

自动化新闻摘要工具，用于：
1. 定期抓取纽约时报中文网 RSS feed
2. 过滤指定时间范围内的新闻（默认24小时）
3. 使用 LLM 生成中文摘要
4. 通过 Telegram Bot 推送到移动设备
5. 支持在 GitHub Actions 上定时运行（完全自动化、免费）

## 核心设计

### 执行环境

1. **本地执行**：
   - 手动运行脚本
   - 使用 `.env` 文件配置（需手动 `source .env`）
   - 输出保存到本地文件

2. **GitHub Actions 执行**（主要使用场景）：
   - 定时触发（cron）或手动触发
   - 使用 Repository Secrets 安全存储敏感信息
   - 无需服务器，完全免费
   - 摘要通过 Telegram 推送，无需访问 GitHub

### 配置方式

**统一使用环境变量**（本地和 GitHub Actions 都适用）：

```bash
# LLM API
GROQ_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY 等
MODEL=groq/llama-3.3-70b-versatile

# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

- 本地：手动 `source .env` 或 `export`
- GitHub Actions：通过 secrets 映射为环境变量

### Telegram 发送策略

1. **一个新闻一条或多条消息**：
   - 每篇新闻独立发送，避免混淆
   - 单条消息超过 4096 字符时自动分段
   - 智能按段落分割，保持可读性

2. **消息格式**（Markdown）：
   ```
   📌 *标题文本*
   🕐 2026-02-09 12:00:00
   🔗 [阅读原文](链接)

   摘要内容...
   ```

3. **错误处理**：
   - Telegram 发送失败不影响后续处理
   - 详细日志记录
   - 文件保存作为备份（虽然在 GitHub Actions 上无意义，但逻辑统一）

### 为什么选择 Telegram 而不是邮件？

1. **申请成本**：Telegram bot 30秒创建，邮件 SMTP 配置复杂或需付费
2. **安全性**：bot token 泄露影响有限，邮箱密码泄露风险大
3. **实时性**：移动端即时推送，随时随地阅读
4. **可撤销性**：bot 可随时通过 @BotFather 撤销重建

## 安全设计和最佳实践

### 1. Telegram Markdown 安全

**问题**：未转义的特殊字符可能导致解析错误或注入问题

**解决方案**：
```python
def escape_markdown(text: str) -> str:
    """转义 Telegram Markdown 特殊字符"""
    escape_chars = ["_", "*", "[", "`", "\\"]
    for char in escape_chars:
        text = text.replace(char, "\\" + char)
    return text
```

- ✅ 标题、摘要、时间全部转义
- ✅ URL 不转义（在链接语法括号内安全）
- ✅ 防止解析错误和潜在注入

### 2. 消息长度控制

**问题**：分页标记可能导致消息超过 4096 字符限制

**解决方案**：双重保护机制
- **预留空间**：使用 3996 字符限制（预留 100 字符给标记）
- **最后验证**：添加标记后检查，超出则截断

```python
TELEGRAM_MAX_LENGTH = 4096
PAGINATION_MARKER_RESERVE = 100
max_chunk_size = TELEGRAM_MAX_LENGTH - PAGINATION_MARKER_RESERVE
```

### 3. 超时控制

**问题**：RSS 或文章获取可能挂起，导致 GitHub Actions 卡死

**解决方案**：所有 HTTP 请求都设置超时
- RSS 获取：30 秒超时
- 文章获取：30 秒超时
- Telegram 发送：10 秒超时

```python
# RSS 获取（使用 httpx 先下载，再解析）
response = httpx.get(rss_url, timeout=30.0, follow_redirects=True)
feed = feedparser.parse(response.text)
```

### 4. HTTP 请求优化

**问题**：缺少 User-Agent 可能被网站拒绝（403），缺少重定向处理

**解决方案**：完整的 HTTP headers
```python
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    "Accept": "text/html,application/xhtml+xml...",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "DNT": "1",
}

httpx.get(url, headers=DEFAULT_HEADERS, follow_redirects=True)
```

- ✅ 模拟真实浏览器
- ✅ 避免 403 Forbidden
- ✅ 自动处理重定向

### 5. 多目标推送

**设计**：支持多个 Chat ID（逗号分隔）
- 可同时推送给多个用户或群组
- 灵活的通知策略

```bash
TELEGRAM_CHAT_ID=123456789,987654321,111222333
```

### 6. 优雅的错误处理

**策略**：
- Telegram 发送失败不中断后续处理
- 只在有失败时发送失败通知（避免噪音）
- 详细的失败信息（标题、错误原因）
- 所有操作都有日志记录

## 依赖和工具链

- `feedparser`：RSS feed 解析
- `httpx`：HTTP 请求（文章抓取 + Telegram API 调用）
- `beautifulsoup4 + lxml`：HTML 解析
- `langchain + litellm`：LLM 统一接口
- **无需** `python-dotenv`：手动加载环境变量
