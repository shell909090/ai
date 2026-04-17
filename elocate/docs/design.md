# elocate 设计文档

## 总体架构

```
CLI (cli.py)
  ├── elocate-updatedb → Indexer
  │                         ├── Chunker    (文档切分)
  │                         ├── Embedder   (sentence-transformers)
  │                         └── VectorDB   (LanceDB: files + chunks 两张表)
  └── elocate          → Searcher
                              ├── Embedder
                              └── VectorDB
                         ↑
                    Config (load_config)  ← ~/.config/elocate/config.yaml
```

## 模块职责

| 模块 | 职责 |
|------|------|
| `config.py` | 加载 YAML 配置，提供 `Config` / `DirConfig` dataclass |
| `chunker.py` | 段落优先 + 固定上限将文档切分为带偏移的 Chunk 列表 |
| `embedder.py` | 封装 sentence-transformers，文本批量转向量 |
| `db.py` | 管理 LanceDB `files`（元数据）和 `chunks`（向量）两张表 |
| `indexer.py` | 增量扫描：文件一致性判断 → 引用计数 → 切分 → embed → 写 DB |
| `searcher.py` | embed query → cosine ANN → 可选 regex 过滤 → 返回结果 |
| `cli.py` | Click 命令入口，组装上述模块 |

---

## 数据模型

### `files` 表（文件元数据，无向量）

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `utf8` | 文件绝对路径（业务主键） |
| `size` | `int64` | 文件字节数 |
| `mtime` | `float64` | 修改时间戳（`os.stat().st_mtime`） |
| `file_hash` | `utf8` | 文件全文 SHA-256 |

### `chunks` 表（向量索引）

| 字段 | 类型 | 说明 |
|------|------|------|
| `file_hash` | `utf8` | 关联 `files.file_hash`（内容键） |
| `chunk_index` | `int32` | chunk 在文件内的顺序（0-based） |
| `start` | `int32` | chunk 在原文中的起始字符偏移 |
| `end` | `int32` | chunk 在原文中的结束字符偏移（不含） |
| `content` | `utf8` | chunk 文本（用于 regex 过滤和 snippet） |
| `vector` | `list<float32>[dim]` | 嵌入向量，metric=cosine |

**表关联**：`chunks.file_hash` → `files.file_hash`（1 对多，多个 path 可共享同一 hash）

---

## 增量更新逻辑（Indexer.run）

### 文件一致性判断

```
对磁盘上每个目标文件 f：
  查 files 表找同 path 的记录 rec

  ① rec 存在 且 size == rec.size 且 mtime == rec.mtime
      → 跳过（内容大概率未变）

  ② rec 存在 但 size 或 mtime 不同
      → 计算 SHA-256
        hash == rec.file_hash → 只更新 files 表的 size/mtime，不重算向量
        hash != rec.file_hash → 走"内容变化"分支（见下）

  ③ rec 不存在（新文件）
      → 计算 SHA-256
        hash 已在 chunks 表 → 只写 files 表（文件副本/移动来的）
        hash 不在 chunks 表 → 切分 + embed + 写 chunks，再写 files 表
```

### 内容变化分支

```
1. 旧 hash 的引用计数（files 表中同 hash 的 path 数）减 1
2. 若引用计数归零 → 删除 chunks 表中该 hash 的所有行
3. 新 hash 走"新文件"③ 逻辑
```

### 已删除文件

```
files 表中存在但磁盘上消失的 path：
1. 从 files 表删除该 path
2. 计算该 hash 剩余引用数
3. 若归零 → 删除 chunks 表中该 hash 的所有行
```

### 文件移动自动处理

文件移动 = 旧 path 消失 + 新 path 出现（hash 相同）。
扫描时：新 path 的 hash 已在 chunks 表 → 只写 files 表，不重算向量。
旧 path 处理时因 hash 还有引用（新 path）→ 不删 chunks。
**无需任何额外的"移动检测"逻辑。**

---

## 文档切分策略（Chunker）

**策略**：段落优先 + 滑动窗口

1. 以 `\n\n` 切分段落
2. 相邻段落贪心合并，累计不超过 `chunk_size` 字符
3. 单段落 > `chunk_size` 时，按 `(chunk_size - overlap)` 步长滑动切分
4. 丢弃 < 20 字符的 chunk
5. 每个 chunk 记录 `start`/`end`（在原文中的字符偏移）

---

## 配置文件格式（YAML）

```yaml
# ~/.config/elocate/config.yaml

index_path: ~/.local/share/elocate/index
embedding_model: all-MiniLM-L6-v2
top_k: 10
chunk_size: 500
chunk_overlap: 50

dirs:
  - path: ~/Documents/work
    extensions: [.md, .txt]
    extractors: [plaintext]
  - path: ~/notes
    extensions: [.md, .org]
    extractors: [plaintext]
```

`extractors` 为字符串列表，当前仅支持 `"plaintext"`（直接读取 UTF-8 文本）。
后续可扩展其他抽取器，由各抽取器决定如何将文件转换为纯文本后交给 Chunker。

---

## 接口定义

### config.py

```python
@dataclass
class DirConfig:
    path: str
    extensions: list[str]          # e.g. [".md", ".txt"]
    extractors: list[str]          # e.g. ["plaintext"]

@dataclass
class Config:
    dirs: list[DirConfig]
    index_path: Path
    top_k: int
    embedding_model: str
    chunk_size: int                # default 500
    chunk_overlap: int             # default 50

def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config: ...
```

### chunker.py

```python
@dataclass
class Chunk:
    content: str
    chunk_index: int   # 0-based
    start: int         # character offset in original text
    end: int           # character offset, exclusive

class Chunker:
    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None: ...
    def chunk(self, text: str) -> list[Chunk]: ...
```

### embedder.py

```python
class Embedder:
    def __init__(self, model_name: str) -> None: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...  # shape (N, dim)
    @property
    def dim(self) -> int: ...
```

### db.py

```python
class VectorDB:
    def __init__(self, index_path: Path) -> None: ...

    # 表管理
    def init_tables(self, dim: int) -> None: ...
    def drop_tables(self) -> None: ...
    def tables_exist(self) -> bool: ...

    # files 表
    def get_file_meta(self, path: str) -> dict | None: ...
    def upsert_file_meta(self, path: str, size: int, mtime: float, file_hash: str) -> None: ...
    def delete_file_meta(self, path: str) -> None: ...
    def list_indexed_paths(self) -> list[str]: ...
    def get_paths_by_hash(self, file_hash: str) -> list[str]: ...

    # chunks 表
    def hash_has_chunks(self, file_hash: str) -> bool: ...
    def add_chunks(self, records: list[dict]) -> None:
        # records: {file_hash, chunk_index, start, end, content, vector}
        ...
    def delete_chunks_by_hash(self, file_hash: str) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[dict]:
        # returns: [{file_hash, chunk_index, start, end, content, _distance}, ...]
        ...
```

### indexer.py

```python
BATCH_SIZE = 64

class Indexer:
    def __init__(self, config: Config) -> None: ...
    def run(self) -> tuple[int, int, int]: ...  # (added, updated, removed) file counts
    def _collect_files(self) -> list[tuple[Path, DirConfig]]: ...
    def _file_hash(self, path: Path) -> str: ...  # SHA-256 hex
```

### searcher.py

```python
@dataclass
class SearchResult:
    paths: list[str]   # all file paths sharing this file_hash
    file_hash: str
    chunk_index: int
    start: int
    end: int
    score: float       # 1 - cosine_distance
    snippet: str       # content[:200]

class Searcher:
    def __init__(self, config: Config) -> None: ...
    def search(self, query: str, pattern: str | None = None) -> list[SearchResult]:
        # ANN recall top_k; if pattern: regex filter on paths+content
        ...
```

### cli.py

```
elocate <query> [-k TOP_K] [-p PATTERN] [--debug]
elocate-updatedb [--debug]
```

`elocate` 捕获：`RuntimeError`（无索引）、`re.error`（非法正则）→ stderr + exit(1)。
`elocate-updatedb` 输出：`Done: +A added, ~B updated, -C removed.`

---

## 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| 配置文件缺失 | 使用默认值 |
| `dirs` 为空 | CLI warning + exit(1) |
| 目录不存在 | warning 跳过 |
| 文件读取失败 | warning 跳过该文件 |
| 索引不存在（搜索时） | RuntimeError → CLI 友好提示 + exit(1) |
| 非法正则 | re.error → CLI 友好提示 + exit(1) |
