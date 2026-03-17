# 项目核心定位

功能：总结各种信息。
技术栈：Python, langchain, litellm, uv (包管理)。

# 代码规范

* 禁止自动git提交
* 提交只包含git stage中的内容，comment使用英文书写，需要简明扼要，禁止把ai列为co-author
* 编码规范遵循PEP-8。
* 强制执行 Type Annotations。
* 公有函数应包含简洁的 Docstrings。不超过一行，注明函数中最重要的事。
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

### 新闻处理顺序

**设计决策**：新闻按时间升序处理（先处理最老的，再处理新的）

**原因**：
1. 符合时间线阅读习惯（从早到晚）
2. RSS feed 通常按倒序排列（最新在前），需要反转
3. 推送到 Telegram 后按时间顺序显示，便于理解事件发展

**实现**：在 `filter_recent_entries()` 中使用 `sort(key=lambda x: x["published_timestamp"])` 排序

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

# kev_report

## 背景和目标

自动化漏洞跟踪工具，用于：
1. 拉取 CISA KEV（已知被利用漏洞）等数据源
2. 过滤指定时间窗口内新增的漏洞条目
3. 可选：按本地软件清单过滤，只关注影响本地环境的漏洞
4. 输出报告（stdout / 本地文件 / Telegram）

## 系统架构：四个模块

### 1. 数据源（Source）

- 当前实现：CISA KEV CSV（两个备用 URL，带本地缓存）
- 架构上须为其他数据源留扩展口，例如 NVD、OSV 直连等
- 每个数据源实现统一接口，返回漏洞条目列表（CVE ID + 元数据）
- 漏洞详情（受影响软件 + 最低安全版本）通过 OSV 优先、NVD 回退方式查询，带缓存

### 2. 过滤日期（Date Filter）

- 参数：`--window-days`，默认 31 天
- 只保留在时间窗口内新增的漏洞条目

### 3. 软件清单过滤（Inventory Filter）

- **不提供清单时**：显示时间窗口内所有 CVE
- **提供清单时**：只显示影响本地已安装软件的 CVE
- 清单来源支持：dpkg / rpm / apk / pip / npm global / gem（自动采集），以及 CSV / JSON（CycloneDX、SPDX、通用列表）/ 纯文本文件
- 参数：`--inventory-file`（可重复），`--no-auto-inventory`

### 4. 输出（Output）

支持三种输出目标，可同时启用多个：

- **stdout**：打印到控制台，格式与本地文件相同（Markdown 文本）
- **本地文件**：Markdown + JSON 双格式，按日期命名
- **Telegram**：复用现有 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 配置，支持多 Chat ID（逗号分隔）

参数：`--output-stdout`、`--output-dir`（不设则不写文件）、`--output-telegram`

## 显示模式（`--mode`）

### CVE 列表模式（默认，`--mode cve`）

按 CVE 维度展示，每条 CVE 列出：
- CVE ID、日期、厂商/产品、必要操作、截止日期
- 命中的本地软件（如有）
- 受影响软件列表，每项显示各自的 min_safe_version 和数据来源

### 汇总清单模式（`--mode summary`）

按软件包维度聚合，跨所有 CVE 汇总：
- 软件包名称
- 最低安全版本：同一软件出现在多个 CVE 时取所有 min_safe_version 的最大值（最严格）
- 关联的 CVE 列表

## 版本比较规则

- 使用轻量级版本比较器（按 `.+-_:` 分割，数字段按数值比较，字母段按字典序）
- 汇总模式下同一软件取 max(min_safe_version)，即要求最高的那个

## 已有 vs 待实现

| 功能 | 状态 |
|---|---|
| KEV 数据源 + 缓存 | ✅ 已实现 |
| `--window-days` 日期过滤 | ✅ 已实现 |
| 本地软件清单采集（dpkg/rpm/apk/pip/npm/gem） | ✅ 已实现 |
| 自定义清单文件（CSV/JSON/TXT） | ✅ 已实现 |
| 本地文件输出（Markdown + JSON） | ✅ 已实现 |
| CVE 列表视图（`--mode cve`） | ✅ 已实现 |
| 数据源扩展接口（`Source` ABC + `KevSource`） | ✅ 已实现 |
| stdout 输出（`--output-stdout`） | ✅ 已实现 |
| Telegram 输出（`--output-telegram`） | ✅ 已实现 |
| 汇总清单模式（`--mode summary`） | ✅ 已实现 |
| 过滤语义修正（不提供清单时显示全部） | ✅ 已实现 |
