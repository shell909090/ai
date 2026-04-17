# elocate 设计文档

## 总体架构

```
CLI (cli.py)
  ├── elocate-updatedb → Indexer → Embedder + VectorDB
  └── elocate          → Searcher → Embedder + VectorDB
                                         ↓
                                    Config (config.py)
```

## 模块说明

| 模块 | 职责 |
|------|------|
| `config.py` | 加载 `~/.config/elocate/config.toml`，提供 `Config` dataclass |
| `embedder.py` | 封装 sentence-transformers，文本批量转向量 |
| `db.py` | 封装 LanceDB，建表/写入/向量查询 |
| `indexer.py` | 扫描目录→读文件→embed→写 DB |
| `searcher.py` | embed query→向量召回→regex 过滤→返回结果 |
| `cli.py` | Click 命令入口，组装上述模块 |

## 数据模型（LanceDB 表结构）

表名：`documents`

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | `utf8` | 文件绝对路径（主键语义） |
| `content` | `utf8` | 文件全文（用于 regex 过滤和 snippet） |
| `vector` | `list<float32>[dim]` | 嵌入向量，维度由模型决定 |

全量重建策略：`elocate-updatedb` 每次 drop + rebuild，不做增量更新（简化实现，适合文档场景）。

## 接口定义

### Config

```python
@dataclass
class Config:
    index_dirs: list[str]
    index_path: Path
    file_extensions: list[str]
    top_k: int
    embedding_model: str

def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config: ...
```

### Embedder

```python
class Embedder:
    def __init__(self, model_name: str) -> None: ...
    def embed(self, texts: list[str]) -> np.ndarray: ...  # shape: (N, dim)
    @property
    def dim(self) -> int: ...
```

### VectorDB

```python
class VectorDB:
    def __init__(self, index_path: Path) -> None: ...
    def create_table(self, dim: int) -> None: ...
    def drop_table(self) -> None: ...
    def upsert(self, records: list[dict]) -> None: ...
    def query(self, vector: list[float], top_k: int) -> list[dict]: ...
    def table_exists(self) -> bool: ...
```

### Indexer

```python
class Indexer:
    def __init__(self, config: Config) -> None: ...
    def run(self) -> int: ...  # returns indexed document count
```

### Searcher

```python
@dataclass
class SearchResult:
    path: str
    score: float
    snippet: str

class Searcher:
    def __init__(self, config: Config) -> None: ...
    def search(self, query: str, pattern: str | None = None) -> list[SearchResult]: ...
```
