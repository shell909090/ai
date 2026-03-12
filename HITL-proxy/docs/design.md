# HITL-proxy 设计文档

## 1. 认证抽象（Issue 3）

### 1.1 问题

当前凭证模型为 `specName → map[string]string`，执行请求时把这组 k/v 原样注入 request header。
这适合固定 header 场景（如 GitHub `Authorization: Bearer xxx`），但无法支持：

- `apiKey in: query`（需注入 URL 查询参数）
- `apiKey in: cookie`（需注入 Cookie）
- `http: basic`（需 base64 编码用户名密码）
- 同一 spec 内多个 security scheme 并存

### 1.2 数据库 Schema 变更

在 `specs` 表新增列，存储从 OpenAPI `components.securitySchemes` 解析出的 scheme 定义：

```sql
ALTER TABLE specs ADD COLUMN security_schemes_json TEXT NOT NULL DEFAULT '{}';
```

在 `operations` 表新增列，存储每个 operation 的 `security` 需求：

```sql
ALTER TABLE operations ADD COLUMN security_json TEXT NOT NULL DEFAULT '[]';
```

`security_schemes_json` 示例（对应 OpenAPI `components.securitySchemes`）：

```json
{
  "BearerAuth": { "type": "http", "scheme": "bearer" },
  "ApiKeyHeader": { "type": "apiKey", "in": "header", "name": "X-API-Key" },
  "ApiKeyQuery": { "type": "apiKey", "in": "query", "name": "api_key" }
}
```

`security_json` 示例（对应 operation 级 `security` 字段）：

```json
[{ "BearerAuth": [] }]
```

### 1.3 凭证存储模型

凭证加密文件从：

```
specName → { "Authorization": "Bearer ghp_xxx" }
```

改为：

```
specName → { "BearerAuth": "ghp_xxx", "ApiKeyQuery": "mytoken" }
```

key 是 OpenAPI securityScheme 的名称，value 是对应的 secret 值（token/密码/key）。

### 1.4 注入逻辑

执行 `call_api` 时，按以下步骤注入凭证：

1. 从 `operations.security_json` 读取该 operation 需要的 scheme 列表
2. 从 `specs.security_schemes_json` 读取 scheme 定义（`in`/`name`/`type`/`scheme`）
3. 从凭证存储按 `schemeName` 取出 secret
4. 根据 scheme 定义决定注入位置：

| scheme 类型 | 注入方式 |
|---|---|
| `http: bearer` | `Authorization: Bearer <secret>` |
| `http: basic` | `Authorization: Basic base64(secret)` |
| `apiKey, in: header` | `<name>: <secret>` |
| `apiKey, in: query` | URL 查询参数 `?<name>=<secret>` |
| `apiKey, in: cookie` | `Cookie: <name>=<secret>` |

5. operation 无 `security` 字段时，回退到 spec 级 global security（如果存在）

---

## 2. 混合检索（Issue 1）

### 2.1 架构

```
HybridSearcher（实现 Searcher 接口）
  ├── FTS5Searcher    ← 关键词匹配，SQLite FTS5 MATCH
  └── VectorSearcher  ← 语义匹配，embedding + ANN
        ├── Embedder      ← 文本 → 向量（OpenAI-compatible HTTP API）
        └── VectorStore   ← 向量存储 + 近邻检索
              ├── ChromemStore   （当前实现，chromem-go）
              └── QdrantStore    （未来扩展）

SQLite（primary store）：operations / operation_deps / specs / rules / audit
VectorStore（search index）：OperationID + Embedding，纯加速外挂
```

**设计原则：** SQLite 是 single source of truth，VectorStore 是搜索加速索引。
向量检索命中 OperationID 后，回查 SQLite 获取完整 operation 数据（indexed lookup，<1ms）。

### 2.2 Embedder 接口

```go
// Embedder 将文本转为向量。实现：OpenAI-compatible HTTP API。
type Embedder interface {
    Embed(ctx context.Context, text string) ([]float32, error)
    Model() string // 返回模型名，用于标记 embedding 版本
}
```

配置：

```yaml
embedding:
  url: "http://localhost:11434/v1/embeddings"  # OpenAI-compatible endpoint
  model: "nomic-embed-text"
  api_key: ""  # 可选
```

未配置时（`url` 为空），VectorSearcher 不启用，HybridSearcher 降级为纯 FTS5。

### 2.3 VectorStore 接口

```go
// VectorStore 存储和检索 operation 的向量索引。
// 当前实现：chromem-go（内存 + 磁盘持久化）。
// 未来扩展：Qdrant（独立服务）。
type VectorStore interface {
    Upsert(ctx context.Context, items []VectorItem) error
    DeleteBySpec(ctx context.Context, specID int64) error
    Search(ctx context.Context, queryVec []float32, limit int) ([]VectorResult, error)
}

type VectorItem struct {
    OperationID string
    SpecID      int64
    Embedding   []float32
}

type VectorResult struct {
    OperationID string
    Score       float32 // cosine similarity，0..1
}
```

### 2.4 Searcher 接口修订

现有接口中 `IndexTx(*sql.Tx, ...)` 把 SQLite 事务泄漏到接口上，向量库无法实现。修订：

- `IndexTx` 从接口移除，保留为 `FTS5Searcher` 的具体公有方法（handler 直接调用）
- 接口新增 `Index(ctx, ops, specID)`，在 SQLite 事务提交后调用，负责向量层索引
- 新增 `DeleteSpec(ctx, specID)`
- 全面加 `context.Context`

```go
// Searcher 是检索的统一接口。
// FTS5Searcher：纯关键词检索（无 embedding 时的完整实现或降级）。
// HybridSearcher：FTS5 + 向量检索，RRF 融合。
type Searcher interface {
    // Index 在 SQLite 事务提交后调用，触发向量索引生成。
    // FTS5Searcher 此方法为 no-op（FTS5 由触发器自动维护）。
    Index(ctx context.Context, ops []openapi.Operation, specID int64) error

    // DeleteSpec 删除 spec 相关的所有向量索引条目。
    DeleteSpec(ctx context.Context, specID int64) error

    // Search 返回语义/关键词相关的操作列表。
    Search(ctx context.Context, query string, limit int) ([]SearchResult, error)
}
```

### 2.5 调用时序

**Spec 导入：**

```
handler
  ├── tx = db.Begin()
  ├── fts5.IndexTx(tx, ops, deps, specID, specName)   // 冲突检测 + SQL 写入
  ├── tx.Commit()
  └── searcher.Index(ctx, ops, specID)                 // 事务外，生成 embedding
                                                        // FTS5Searcher: no-op
                                                        // HybridSearcher: 调 Embedder → VectorStore
```

**搜索：**

```
HybridSearcher.Search(query, limit)
  ├── goroutine: fts5.Search(query, limit*2)           → []FTS5Result{OperationID, rank}
  ├── goroutine: embed(query) → VectorStore.Search()   → []VectorResult{OperationID, score}
  ├── 等待两路结果
  ├── RRF 融合：score = Σ 1/(60 + rank_i)，按 OperationID 聚合
  ├── 取 top-limit OperationID
  ├── SELECT * FROM operations WHERE operation_id IN (...)   // 回查完整数据
  └── loadDependencies()                               // 补充依赖关系
```

### 2.6 RRF 融合

Reciprocal Rank Fusion，k=60（经验值）：

```
对每个出现在任意一路结果中的 OperationID：
  rrf_score = Σ_i  1 / (k + rank_i)

两路结果按各自排名计算，未出现则不贡献分数。
按 rrf_score 降序，取 top-limit。
```

优点：不需要归一化两路分数，关键词 rank 和向量 cosine score 量纲不同也能融合。

### 2.7 数据库变更

VectorStore 使用 chromem-go 独立持久化，不新增 SQLite 表。

配置新增向量库路径：

```yaml
vector:
  path: "vector.db"  # chromem-go 持久化路径
```
