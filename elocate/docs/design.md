# elocate 设计文档

## 总体架构

```
CLI (cli.py)
  ├── elocate-updatedb → Indexer
  │                         ├── Chunker    (文档切分)
  │                         ├── Embedder   (OpenAI 兼容 API 客户端)
  │                         └── VectorDB   (LanceDB: files + chunks 两张表)
  └── elocate          → Searcher
                              ├── Embedder
                              └── VectorDB
                         ↑
                    Config (load_config)  ← ~/.config/elocate/config.yaml

外部服务（用户自行运行）：
  ollama / OpenAI / 任何 OpenAI 兼容 embedding 服务
```

**架构原则**：elocate 不内含推理权重，embedding 推理完全委托给外部 OpenAI 兼容服务，
职责边界清晰（索引+搜索 vs 推理）。

## 模块职责

| 模块 | 职责 |
|------|------|
| `config.py` | 加载 YAML 配置，提供 `Config` / `DirConfig` dataclass，并校验扩展名规则语法 |
| `chunker.py` | 段落优先 + 固定上限将文档切分为带偏移的 Chunk 列表 |
| `embedder.py` | 封装 OpenAI 兼容 embeddings API，文本批量转向量 |
| `db.py` | 管理 LanceDB `files`（元数据）和 `chunks`（向量）两张表 |
| `indexer.py` | 增量扫描：规则匹配筛选 → 文件一致性判断 → 抽取累积 → 阈值 flush → 切分 → embed → 写 DB |
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

**表关联**：`chunks.file_hash` → `files.file_hash`（一个 hash 对应多个 path，chunks 共享）

---

## 增量更新逻辑（Indexer.run）

### 文件一致性判断

```
对磁盘上每个目标文件 f：
  查 files 表找同 path 的记录 rec

  ① rec 存在 且 size == rec.size 且 mtime == rec.mtime
      → 跳过

  ② rec 存在 但 size 或 mtime 不同
      → 计算 SHA-256
        hash == rec.file_hash → 只更新 files 表的 size/mtime，不重算向量
        hash != rec.file_hash → 走"内容变化"分支

  ③ rec 不存在（新文件）
      → 计算 SHA-256
        hash 已在 chunks 表 → 只写 files 表（副本或移动来的文件）
        hash 不在 chunks 表 → 提取文本 → 切分 → embed → 写 chunks，再写 files 表
```

### 内容变化分支

```
1. 旧 hash 的引用计数（files 表中同 hash 的行数）减 1
2. 若引用计数归零 → 删除 chunks 表中该 hash 的所有行
3. 新 hash 走"新文件"③ 逻辑
```

### 已删除文件

```
files 表中存在但磁盘上消失的 path：
1. 从 files 表删除该 path
2. 若该 hash 引用计数归零 → 删除 chunks
```

### 文件移动自动处理

移动 = 旧 path 消失 + 新 path 出现（hash 相同）。
新 path 扫描时 hash 已在 chunks → 只写 files，不重算。
旧 path 删除时因 hash 仍有引用 → chunks 保留。
**无需任何额外移动检测逻辑。**

---

## 批量调度与性能计数

### 调度目标

索引流程不再先把全部待嵌入文本累积到内存再统一 embedding，而是：

1. 先完成全量扫描，仅识别“需要处理”的文件集合。
2. 再对待处理文件逐个抽取文本，并累积到当前 batch。
3. 当累计文件数或累计字符数达到阈值时，立即对当前 batch 执行切分、embedding 与写库。
4. 扫描结束后若仍有未 flush 的 batch，再执行最后一次 flush。

### 配置项

新增两个配置项，放在 `~/.config/elocate/config.yaml` 顶层：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `embed_batch_files` | `int` | `64` | 单批待嵌入文件上限 |
| `embed_batch_chars` | `int` | `65536` | 单批待嵌入文本字符总量上限 |

### flush 规则

1. 对待处理文件完成文本抽取后，将 `(path, hash, size, mtime, text, old_hash)` 加入当前 batch。
2. 同时累加当前 batch 的文件数和 `len(text)` 字符数。
3. 当 `batch_file_count >= embed_batch_files` 或 `batch_char_count >= embed_batch_chars` 时，立即 flush。
4. 若某个单文件自身文本字符数已超过 `embed_batch_chars`，则允许其单独成批 flush。
5. flush 阶段仍保持“单次 embed 调用覆盖当前 batch 全部 chunks”的行为，以维持模型吞吐效率。

### 失败语义

1. 文件抽取失败时，仅记录 warning 并跳过该文件。
2. 已成功 flush 的批次视为已落库，后续文件失败不回滚此前批次。
3. 中断运行时，已完成写库的批次保留；未 flush 或处于当前 flush 中的批次允许在下次运行时重新收敛。

### debug 级性能计数

`--debug` 开启后，Indexer 需要输出两级指标：

1. **批次级指标**
   - `batch_index`
   - `files`
   - `chars`
   - `chunks`
   - `extract_seconds`
   - `chunk_seconds`
   - `embed_seconds`
   - `db_write_seconds`
   - `chars_per_second`
   - `chunks_per_second`
2. **全局汇总指标**
   - `files_scanned`
   - `files_skipped_unchanged`
   - `files_pending`
   - `files_extract_failed`
   - `files_flushed`
   - `chunks_embedded`
   - `chars_embedded`
   - `extract_seconds_total`
   - `embed_seconds_total`
   - `db_write_seconds_total`

### debug 日志范围

CLI 的 `--debug` 不再把 root logger 直接提升到 `DEBUG`。改为：

1. root logging 维持在 `WARNING`，避免第三方依赖输出大量调试日志。
2. `elocate` 命名空间 logger（如 `elocate.cli`、`elocate.indexer`）单独提升到 `DEBUG`。
3. `openai`、`httpx`、`httpcore` 命名空间显式设为 `WARNING`，确保网络请求和 SDK 细节不会冲掉批次性能输出。
4. 非 debug 模式保持现状，不主动调整日志配置。

---

## 文档切分策略（Chunker）

**策略**：段落优先 + 滑动窗口

1. 以 `\n\n` 切分段落
2. 相邻段落贪心合并，累计不超过 `chunk_size` 字符
3. 单段落 > `chunk_size` 时，按 `(chunk_size - overlap)` 步长滑动切分
4. 丢弃 < 20 字符的 chunk
5. 每个 chunk 记录 `start`/`end`（在原文中的字符偏移）

---

## 扩展名规则与文件筛选

### 规则语法

`DirConfig.extensions` 保持 `list[str]` 类型，但每个元素允许以下三种语义：

| 规则形式 | 示例 | 语义 |
|----------|------|------|
| 精确扩展名 | `.md` | 与 `Path.suffix.lower()` 精确匹配，保持向后兼容 |
| 完整后缀 | `suffix:.tar.gz` | 与 `Path.name.lower().endswith(".tar.gz")` 匹配，用于复合扩展名 |
| 文件名 glob | `glob:*.*` | 对 `Path.name.lower()` 做 glob 匹配，用于少量规则覆盖一组文件名 |

### 匹配策略

1. 规则匹配统一大小写不敏感。
2. 多条规则之间是“或”关系，只要命中任意一条就纳入扫描。
3. 精确扩展名规则只看最后一段扩展名，保留现有行为；例如 `.gz` 可命中 `a.tar.gz`。
4. `suffix:` 规则基于完整文件名后缀匹配；例如 `suffix:.tar.gz` 只命中 `a.tar.gz`，不命中 `a.gz`。
5. `glob:` 规则仅匹配文件名 `Path.name`，不匹配父目录路径；底层采用 shell 风格 glob 语义。
6. 目录扫描阶段先应用扩展名规则，再执行文本抽取；因此 `glob:*.*` 可作为“尽量放开白名单”的单条规则，把文件交给后续 extractor 决定是否可提取。

### 配置校验

`load_config()` 在加载 `dirs[].extensions` 时做静态校验：

1. 以 `suffix:` 开头的规则，冒号后的值必须非空，且必须以 `.` 开头。
2. 以 `glob:` 开头的规则，冒号后的 pattern 必须非空。
3. 含有前缀但前缀不在 `suffix` / `glob` 白名单内时，直接报 `ValueError`。
4. 不含前缀且以 `.` 开头的字符串，视为合法的向后兼容精确扩展名规则。

### exclude 规则

`DirConfig` 新增 `exclude: list[str]`，默认空列表。每条规则允许两种语义：

| 规则形式 | 示例 | 语义 |
|----------|------|------|
| 名称快捷排除 | `.venv`、`.git`、`__pycache__` | 若规则不含 `/` 且不含 glob 特殊字符，则匹配扫描树中任意路径段的名称；命中目录时直接剪枝整个子树 |
| 相对路径 glob | `.claude/*`、`*.pyc`、`cache/*.json` | 对相对于 `DirConfig.path` 的 POSIX 风格路径做 `fnmatch` 匹配；可排除单文件或局部子树 |

### exclude 匹配策略

1. `exclude` 作用域仅限当前 `DirConfig.path` 对应的扫描树。
2. 目录扫描改为基于 `os.walk()`，以便在发现被排除目录后直接从 `dirnames` 中删除，避免继续进入其子目录。
3. 对任意候选路径，先做 `exclude` 判断，再做 `extensions` 判断；即 `exclude` 优先级高于 `extensions`。
4. 名称快捷排除用于高频噪音目录/文件，如 `.venv`、`.git`、`__pycache__`；相对路径 glob 用于更精细的局部排除。
5. 路径匹配基于相对于 base 目录的 `as_posix()` 结果，不包含 base 本身；例如 `notes/.venv/bin/python` 在规则判断中看到的是 `.venv/bin/python`。
6. 未配置 `exclude` 时，扫描行为与当前版本保持一致。

---

## 文本抽取（Extractor 集成）

### 单一路径

elocate 的文本抽取统一委托给 `all2txt.registry.extract(path)`。
`all2txt` 升级为 **required dependency**，默认安装后即应可导入和使用。

`plaintext` 不再作为独立 extractor 存在；纯文本文件也通过 all2txt 的 MIME 检测与后端链处理。

### 配置兼容策略

1. `DirConfig` 保留 `extractor_config`，继续作为 all2txt 的透传配置入口。
2. `DirConfig` 中的 `extractor` 字段从配置层移除，不再要求用户填写。
3. 兼容期内若用户配置中显式写 `extractor` 字段，加载时统一接受并忽略，不再影响行为。
4. 文档与示例不再推荐填写 `extractor` 字段。

### extractor_config 透传

`extractor_config` 字典按 `all2txt.core.config.Config` 字段结构透传给
`all2txt.registry.configure()`：

```yaml
# all2txt Config 字段
backends:
  "image/jpeg": [openai_vision]  # 覆盖该 MIME 的后端顺序
extractors:
  openai_vision:
    model: gpt-4o               # 传给 Extractor.__init__(config=...)
extensions:
  ".md": "text/markdown"        # file(1) 返回 generic MIME 时的扩展名覆盖
```

Indexer 为每个 `DirConfig` 构造一个独立的 all2txt `Config` 实例并调用
`registry.configure()`，处理完该目录后恢复原状态（避免目录间互相干扰）。

---

## 配置文件格式（YAML）

```yaml
# ~/.config/elocate/config.yaml

index_path: ~/.local/share/elocate/index
embedding_model: all-MiniLM-L6-v2
top_k: 10
chunk_size: 500
chunk_overlap: 50
embed_batch_files: 64
embed_batch_chars: 65536

dirs:
  # 纯文本笔记也统一通过 all2txt 抽取
  - path: ~/notes
    extensions: [.md, .org, .txt]

  # 文档目录：常规扩展名 + 复合后缀
  - path: ~/Documents
    extensions:
      - .pdf
      - .docx
      - suffix:.tar.gz

  # 宽松模式：放行所有带点文件名，由 all2txt 自动判定 MIME 与 backend
  - path: ~/mixed-data
    extensions:
      - glob:*.*
    extractor_config:
      extractors:
        archive_recurse:
          enabled: true
        7zip_recurse:
          enabled: true
        rar_recurse:
          enabled: true
```

---

## 接口定义

### config.py

```python
@dataclass
class DirConfig:
    path: str
    extensions: list[str]                   # e.g. [".md", "suffix:.tar.gz", "glob:*.*"]
    exclude: list[str] = field(default_factory=list)
    extractor_config: dict = field(...)     # forwarded to all2txt.Config

@dataclass
class Config:
    dirs: list[DirConfig]
    index_path: Path
    top_k: int
    embedding_model: str
    chunk_size: int                         # default 500
    chunk_overlap: int                      # default 50
    embed_batch_files: int = 64
    embed_batch_chars: int = 65536
    embedder_backend: str = "local"         # "local" | "openai"
    openai_base_url: str = ""               # OpenAI-compatible API base URL
    openai_api_key: str = ""                # API key (empty = no auth)

def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config: ...
```

### chunker.py

```python
@dataclass
class Chunk:
    content: str
    chunk_index: int
    start: int          # character offset, inclusive
    end: int            # character offset, exclusive

class Chunker:
    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None: ...
    def chunk(self, text: str) -> list[Chunk]: ...
```

### embedder.py

```python
class Embedder:
    def __init__(
        self,
        model_name: str,
        backend: str = "local",        # "local" | "openai"
        api_base: str = "",            # OpenAI-compatible base URL
        api_key: str = "",             # API key
    ) -> None: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...  # shape (N, dim)
    @property
    def dim(self) -> int: ...
    # local:  dim from SentenceTransformer.get_sentence_embedding_dimension()
    # openai: dim probed lazily on first access (one-shot embed of dummy text)
```

**后端说明：**

| backend | 依赖 | dim 获取方式 |
|---------|------|-------------|
| `"local"` | `sentence-transformers`（已有） | `model.get_sentence_embedding_dimension()` |
| `"openai"` | `openai>=1.0`（optional） | 首次访问 `dim` 时 embed 一个空串探测 |

`openai` 后端对 `api_base`/`api_key` 不做格式校验，直接透传给 `openai.OpenAI(base_url=..., api_key=...)`，兼容 ollama、LM Studio、OpenAI 等任何实现。`api_key` 为空时传 `"none"`（openai SDK 要求非空字符串）。

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
        # record keys: file_hash, chunk_index, start, end, content, vector
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
    def _matches_exclude(self, rel_path: str, parts: tuple[str, ...], rules: list[str]) -> bool: ...
    def _scan_disk_files(self, disk_files: list[tuple[Path, DirConfig]]) -> tuple[list[tuple[Path, DirConfig, object, dict | None, str]], int, int]: ...
    def _flush_pending_batch(self, pending: list[tuple[str, str, int, float, str, str | None]], ...) -> None: ...
    def _match_extension_rule(self, path: Path, rule: str) -> bool: ...
    def _matches_extensions(self, path: Path, rules: list[str]) -> bool: ...
    def _file_hash(self, path: Path) -> str: ...
    def _extract_text(self, path: Path, dir_cfg: DirConfig) -> str:
        # always configure all2txt with dir_cfg.extractor_config,
        # call registry.extract(path), restore registry state
        ...
```

### searcher.py

```python
@dataclass
class SearchResult:
    paths: list[str]    # all file paths sharing this file_hash
    file_hash: str
    chunk_index: int
    start: int
    end: int
    score: float        # 1 - cosine_distance
    snippet: str        # content[:200]

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
| 文件读取/抽取失败 | warning 跳过该文件 |
| `all2txt` 未安装 | 启动即视为环境错误；CLI 友好提示并退出 |
| 索引不存在（搜索时） | RuntimeError → CLI 友好提示 + exit(1) |
| 非法正则 | re.error → CLI 友好提示 + exit(1) |
