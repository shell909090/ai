# HITL-proxy 需求文档

## 1. 项目概述

OpenAPI 代理服务，作为 AI Agent 操作第三方 API 的中间层。系统定位为 **AAAA**：

- **Authentication** — 身份认证（Agent→代理 + 代理→目标 API 两层）
- **Authorization** — 按 OpenAPI operationId 粒度的访问控制
- **Auditing** — 全量审计日志
- **Approval** — 基于规则的人工审批（Human-in-the-Loop）

## 2. 系统架构

```
Agent (Claude Code 等)
  │
  ├─ MCP SSE transport (直连)
  │     │
  └─ CLI bridge (stdio→SSE 桥接，供只支持 stdio 的 Agent)
        │
        ▼
┌──────────────────────────┐
│     HITL-proxy (Go)      │
│                          │
│  MCP Server (SSE)        │
│  Web UI (html/template)  │
│  Policy Engine           │
│  Credential Store        │
│                          │
│  chromem-go (向量)       │
│  SQLite (结构化数据)       │
│  加密文件 (凭证)          │
└──────────────────────────┘
        │
        ▼
   目标 API (GitHub 等)
```

## 3. 技术选型

| 组件 | 选型 |
|------|------|
| 语言 | Go |
| Agent 协议 | MCP SSE transport |
| CLI Bridge | 独立二进制，MCP stdio↔SSE 桥接 |
| 向量存储 | chromem-go（内存 + 磁盘持久化，HNSW 索引）；接口抽象，未来支持 Qdrant |
| 结构化存储 | SQLite（primary store：审批规则、审计日志、API 元数据、FTS5 关键词索引） |
| 凭证存储 | 加密文件（MVP），接口抽象，未来支持 keyring/vault |
| Embedding | OpenAI-compatible HTTP API（环境变量 OPENAI_BASE_URL / OPENAI_API_KEY，兼容 Ollama） |
| Web UI | Go html/template + htmx |
| 测试目标 | GitHub API（MVP） |

## 4. 核心功能

### 4.1 OpenAPI Spec 管理

- 通过 HTTP API 导入 OpenAPI/Swagger spec（Web UI 支持上传）
- 解析 spec，提取每个 operation（operationId、method、path、summary、description、parameters、request body）
- 将 operation 描述文本向量化，存入 chromem-go 向量存储（spec 导入后异步触发）
- **依赖分析**：导入时预计算 API 间的依赖关系（如 DELETE /logs/{id} 依赖 GET /logs 来获取 id），存储依赖图

### 4.2 MCP Server

暴露两个 MCP tool（MVP，后续按需扩展）：

#### `search_tools`
- 输入：自然语言查询
- 处理：混合检索（FTS5 关键词 + chromem-go 向量语义），RRF 融合排序
- 输出：匹配的 API 列表及其描述，**同时返回依赖的相关接口**

#### `call_api`
- 输入：operationId + 参数 + reason（optional，AI 说明调用理由）
- 处理流程：
  1. Authentication — 验证 Agent 身份
  2. Authorization — 检查该 Agent 是否有权调用此 operation
  3. Approval — 按规则判断是否需要人工审批，需要则阻塞等待
  4. 执行 — 注入目标 API 凭证，发起请求
  5. Auditing — 记录完整调用日志
- 输出：API 响应结果

### 4.3 Authentication（双层）

**Agent → 代理：**
- MVP：用户指定的 API Key
- 未来：支持多种认证方式（含从浏览器获取凭证）

**代理 → 目标 API：**
- 代理统一管理凭证，Agent 不接触目标 API 的认证信息
- MVP：用户指定 API Key，存入加密文件
- 未来：支持从浏览器获取凭证、系统 keyring、外部 vault

### 4.4 Authorization

- 按 OpenAPI operationId 粒度配置访问权限
- 存储在 SQLite

### 4.5 Auditing

- 全量记录到 SQLite
- 记录内容：时间戳、Agent 身份、operationId、请求参数、响应状态码、审批结果、reason

### 4.6 Approval（HITL）

**审批规则：**
- 按 operationId 粒度配置（每个接口独立配置是否需要审批）
- 规则存储在 SQLite

**审批流程：**
- Agent 调用 call_api → 命中审批规则 → 请求同步阻塞
- 审批请求推送到 Web UI
- 人工审批通过/拒绝 → 请求继续或返回拒绝

**审批页面展示（关键）：**
- 不是展示原始 HTTP 请求，而是结合 OpenAPI spec 做**语义化释义**
- 展示：operation 的 summary/description、参数含义、AI 提供的 reason
- 让审批人能理解"这个调用要干什么"，而非盲批

**审批渠道：**
- MVP：Web UI
- 未来：终端交互、Slack/邮件通知

### 4.7 CLI Bridge

- 独立二进制工具
- 功能：将远程 MCP SSE 服务转为本地 MCP stdio 进程
- 用途：供只支持 stdio 的 Agent（如 Claude Code）连接

### 4.8 Web UI

**MVP：**
- 待审批列表 + 请求详情 + 通过/拒绝按钮（语义化展示）

**后续：**
- 管理页面：导入 spec、配置审批规则、管理凭证

## 5. MVP 范围

最小可用，先跑通完整流程：

1. OpenAPI spec 导入（API + Web UI 上传）
2. 混合检索（FTS5 + chromem-go 向量，RRF 融合，含依赖接口返回）
3. MCP SSE Server（search_tools + call_api）
4. CLI Bridge（stdio↔SSE）
5. SQLite 审批规则（per operationId）
6. Web UI 审批（语义化展示 + approve/reject）
7. 凭证管理（加密文件）
8. 全量审计日志
9. 测试目标：GitHub API

## 6. 现有方案调研

| 项目 | 匹配度 | 说明 |
|------|--------|------|
| [AgentGate](https://github.com/agentkitai/agentgate) | 最高 | 有 HITL 审批+审计+凭证隔离，但基于预置 connector，不支持任意 OpenAPI spec |
| auto-mcp / mcp-openapi-proxy 等 | 中 | OpenAPI→MCP 转换，但无审批/审计 |
| mcp-gateway-registry | 低 | MCP 治理网关，有 RBAC 和审计，但不消费 OpenAPI spec |

**结论：无现成项目完全满足需求，需自建。**
