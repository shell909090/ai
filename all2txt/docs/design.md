# all2txt 设计文档

## 一、架构概览

```
输入文件
  │
  ▼
detect(path) → file --mime-type -b → MIME 字符串
  │
  ▼
Registry._map[mime] → [BackendA, BackendB, BackendC, ...]  （按优先级排序）
  │
  ├─ BackendA.available()? No → skip
  ├─ BackendA.extract(path) → 成功 → 返回文本
  ├─ BackendA.extract(path) → 失败 → 记录错误，继续
  ├─ BackendB.available()? No → skip
  ├─ BackendB.extract(path) → 成功 → 返回文本
  └─ 全部失败 → raise RuntimeError
```

**核心原则**：以系统 `file` 命令为唯一类型识别手段；后端以调用外部 CLI 工具为主，Python 为粘合层；任何单个后端缺失不影响整体可用性。

---

## 二、模块结构

```
all2txt/
├── __init__.py          # 导出 registry, load_config, __version__
├── __main__.py          # CLI 入口，argparse
├── core/
│   ├── __init__.py
│   ├── base.py          # Extractor 抽象基类
│   ├── registry.py      # Registry 单例；MIME → 后端链；排序逻辑
│   └── config.py        # 读取 all2txt.toml → Config dataclass
└── backends/
    ├── __init__.py      # 导入所有后端，触发注册副作用
    ├── plaintext.py     # 直读文本（text/plain, csv, markdown …）
    ├── pandoc.py        # pandoc CLI（tex, troff, html, epub, odt …）
    ├── system.py        # groff+col（man/troff）；info CLI（GNU Info）
    ├── pymupdf.py       # PyMuPDF 库（PDF，快速，无 JVM）
    ├── tika.py          # Apache Tika Python 包（PDF + Office 全系）
    └── unstructured.py  # unstructured 库（PDF + 图片 OCR）
```

---

## 三、接口定义

### 3.1 Extractor（core/base.py）

```python
class Extractor(ABC):
    name: str        # 唯一标识符，供配置文件引用，如 "pandoc"
    priority: int    # 默认优先级，数字越小越优先（同 MIME 内比较）

    @abstractmethod
    def extract(self, path: Path) -> str:
        """从 path 抽取纯文本，失败时抛出异常。"""

    def available(self) -> bool:
        """返回 True 表示后端所需外部依赖已就位，默认 True。"""
        return True
```

### 3.2 Config（core/config.py）

```python
@dataclass
class Config:
    backends: dict[str, list[str]]
    # key:   MIME 类型字符串，如 "application/pdf"
    # value: 按期望优先级排列的 backend name 列表，如 ["pymupdf", "tika"]
    #        列表中的后端排在前面；未列出的后端按 priority 属性追加在后

def load_config(path: Path | None = None) -> Config:
    """从 all2txt.toml 加载配置，文件不存在时返回空 Config。"""
```

### 3.3 Registry（core/registry.py）

```python
class Registry:

    def register(self, *mimes: str) -> Callable[[type[Extractor]], type[Extractor]]:
        """类装饰器：将 Extractor 子类注册到指定 MIME 类型。
        可同时注册多个 MIME，重复注册同一类型追加到链尾后重新排序。"""

    def configure(self, config: Config) -> None:
        """应用配置，对所有已注册 MIME 重新排序。应在导入后端之后、首次 extract 之前调用。"""

    def detect(self, path: Path) -> str:
        """调用 `file --mime-type -b <path>`，返回 MIME 字符串。"""

    def extract(self, path: Path, mime: str | None = None) -> str:
        """按优先级链逐个尝试后端，返回第一个成功结果。
        mime 为 None 时自动调用 detect()。全部失败时抛出 RuntimeError。"""

# 模块级单例，所有后端通过此实例注册
registry: Registry
```

### 3.4 排序规则（Registry._sort）

1. 若当前 MIME 在 config.backends 中有配置列表：
   - 在列表中的后端：按列表下标排序（tuple 第一元素为 0）。
   - 不在列表中的后端：按 `cls.priority` 排序（tuple 第一元素为 1）。
2. 无配置时：仅按 `cls.priority` 升序。
3. `available()` 的结果不影响排序，在 `extract()` 运行时跳过。

### 3.5 CLI（\_\_main\_\_.py）

```
all2txt [--config FILE] [--mime MIME] [--debug] FILE [FILE ...]
```

| 参数 | 说明 |
|---|---|
| `FILE` | 一个或多个输入文件路径 |
| `--config FILE` | 指定配置文件，默认 `./all2txt.toml` |
| `--mime MIME` | 跳过自动检测，强制指定所有输入文件的 MIME |
| `--debug` | 启用 DEBUG 级别日志，输出到 stderr |

每个文件的提取结果顺序写入 stdout，文件间不插入分隔符。任意文件失败则打印错误到 stderr 并以退出码 1 结束。

---

## 四、后端规格

| 后端 | name | priority | 注册 MIME | 外部依赖 |
|---|---|---|---|---|
| PlainTextExtractor | `plaintext` | 1 | text/plain, text/csv, text/markdown, text/x-python | 无 |
| ManExtractor | `man` | 5 | text/troff | `groff`, `col` |
| InfoExtractor | `info` | 5 | text/x-info | `info` (GNU) |
| PandocExtractor | `pandoc` | 10 | text/x-tex, text/troff, text/html, application/xhtml+xml, application/epub+zip, application/vnd.oasis.opendocument.text | `pandoc` CLI |
| PyMuPDFExtractor | `pymupdf` | 15 | application/pdf | `pymupdf` Python 包 |
| TikaExtractor | `tika` | 20 | application/pdf, application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document, application/vnd.ms-excel, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-powerpoint, application/vnd.openxmlformats-officedocument.presentationml.presentation, application/vnd.oasis.opendocument.text, application/vnd.oasis.opendocument.spreadsheet | `tika` Python 包 + JVM |
| UnstructuredExtractor | `unstructured` | 30 | application/pdf, image/png, image/jpeg, image/tiff, image/bmp, image/webp | `unstructured` Python 包 |

---

## 五、配置文件格式（all2txt.toml）

```toml
# 按 MIME 类型覆盖后端优先级，列表中靠前的后端优先尝试
[mime."application/pdf"]
backends = ["pymupdf", "tika", "unstructured"]

[mime."text/x-tex"]
backends = ["pandoc"]
```

---

## 六、扩展指南

新增后端只需：
1. 在 `backends/` 下新建 `.py` 文件，继承 `Extractor`，设置 `name`、`priority`。
2. 用 `@registry.register("mime/type", ...)` 装饰类。
3. 在 `backends/__init__.py` 中 import 该模块。

无需修改任何现有代码。
