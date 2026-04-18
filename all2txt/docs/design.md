# all2txt 设计文档

## 一、架构概览

```
输入文件
  │
  ▼
detect(path)
  ├─ file --mime-type -b → MIME 字符串
  └─ 若结果为通用类型（text/plain 等），查 Config.extensions 按扩展名覆盖
  │
  ▼
Registry._map[mime] → [BackendA(cfg), BackendB(cfg), ...]  （按优先级排序）
  │
  ├─ BackendA.available()? No → skip
  ├─ BackendA.extract(path) → 成功 → 返回文本
  ├─ BackendA.extract(path) → 失败 → 记录错误，继续
  └─ 全部失败 → raise RuntimeError
```

**核心原则**：
- 类型识别以 `file --mime-type` 为主，扩展名映射为辅（解决 file 无法区分的格式）。
- 每个后端在实例化时注入自己的配置字典，实现后端级可配置。
- 任何单个后端缺失（`available()` 为 False）不影响其他后端。
- 新增后端只需新建文件 + 一行 import，无需修改已有代码。

---

## 二、模块结构

```
all2txt/
├── __init__.py
├── __main__.py                  # CLI 入口
├── core/
│   ├── base.py                  # Extractor 抽象基类（含配置注入）
│   ├── registry.py              # Registry 单例
│   └── config.py                # Config dataclass + load_config()
└── backends/
    ├── __init__.py              # 导入所有后端，触发注册副作用
    ├── plaintext.py             # 直读文本
    ├── pandoc.py                # pandoc CLI（文档/标记语言全系列）
    ├── libreoffice.py           # LibreOffice CLI（Office + ODF）
    ├── native_office.py         # python-docx / openpyxl / python-pptx
    ├── system.py                # groff+col（man）；info CLI（GNU Info）
    ├── pymupdf.py               # PyMuPDF（PDF，快）
    ├── tika.py                  # Apache Tika（PDF + Office 全系）
    ├── unstructured.py          # unstructured（PDF + 图片 OCR）
    ├── ocr.py                   # Tesseract / EasyOCR / PaddleOCR
    ├── openai_vision.py         # OpenAI Vision API（可配：提取文字 vs 描述内容）
    └── asr.py                   # OpenAI Whisper API / Whisper 本地 / faster-whisper
```

---

## 三、接口定义

### 3.1 Extractor（core/base.py）

```python
class Extractor(ABC):
    name: str        # 唯一标识符，供配置文件引用，如 "pandoc"
    priority: int    # 默认优先级，数字越小越优先（同 MIME 内比较）

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg: dict[str, Any] = config or {}

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
    # key:   MIME 类型，如 "application/pdf"
    # value: 按期望顺序的 backend name 列表；列表中的后端优先，其余按 priority 追加

    extractors: dict[str, dict[str, Any]]
    # key:   backend name，如 "openai_vision"
    # value: 传给该后端构造函数的配置字典

    extensions: dict[str, str]
    # key:   小写扩展名，含点，如 ".rst"
    # value: 覆盖用的 MIME 类型，如 "text/x-rst"
    # 仅在 file 命令返回通用类型时生效

def load_config(path: Path | None = None) -> Config:
    """从 all2txt.yaml 加载配置，文件不存在时返回空 Config。"""
```

### 3.3 Registry（core/registry.py）

```python
class Registry:

    def register(self, *mimes: str) -> Callable[[type[Extractor]], type[Extractor]]:
        """类装饰器：注册 Extractor 子类到一个或多个 MIME 类型。"""

    def configure(self, config: Config) -> None:
        """应用配置，对所有已注册 MIME 重新排序。首次 extract 前调用。"""

    def detect(self, path: Path) -> str:
        """调用 file --mime-type -b；若结果为通用类型，按 Config.extensions 覆盖。"""

    def extract(self, path: Path, mime: str | None = None) -> str:
        """按优先级链逐个尝试后端，实例化时注入 Config.extractors 对应配置。
        全部失败时抛出 RuntimeError。"""

registry: Registry   # 模块级单例
```

#### 排序规则（Registry._sort）

1. 若当前 MIME 在 `config.backends` 中有配置列表：
   - 在列表中的后端按列表下标排序（tuple 第一元素为 0）。
   - 不在列表中的后端按 `cls.priority` 排序（tuple 第一元素为 1）。
2. 无配置：仅按 `cls.priority` 升序。
3. `available()` 不影响排序，在运行时跳过。

#### 通用 MIME 类型列表（触发扩展名覆盖）

`detect()` 在以下 MIME 类型时才查 `extensions` 表：
`text/plain`, `application/octet-stream`, `application/xml`,
`text/xml`, `application/json`

### 3.4 CLI（\_\_main\_\_.py）

```
all2txt [--config FILE] [--mime MIME] [--verbose] [--debug] [--allow-archive] FILE [FILE ...]
```

| 参数 | 说明 |
|---|---|
| `FILE` | 一个或多个输入文件路径 |
| `--config FILE` | 指定配置文件，默认 `./all2txt.yaml` |
| `--mime MIME` | 跳过自动检测，强制所有输入文件使用同一 MIME |
| `--verbose` / `-v` | 启用 INFO 日志（显示 MIME 检测、后端选择信息） |
| `--debug` | 启用 DEBUG 日志到 stderr |
| `--allow-archive` | 启用压缩包递归提取（默认禁用，防 zip bomb） |

`--allow-archive` 等价于在配置文件中设置 `extractor.zip_recurse.enabled: true`。它在 `load_config` 之后、`registry.configure` 之前注入到 `config.extractors`。

每个文件输出顺序写入 stdout，文件间无分隔符。任意文件失败则 stderr 报错、退出码 1。

---

## 四、后端规格

### 4.1 文本直读

| 后端 | name | priority | 注册 MIME | 外部依赖 |
|---|---|---|---|---|
| PlainTextExtractor | `plaintext` | 1 | text/plain, text/csv, text/markdown, text/tab-separated-values, text/x-python, text/x-script.python | 无 |

### 4.2 文档/标记语言（pandoc）

PandocExtractor 通过 `pandoc -t plain --wrap=none` 统一处理以下格式。
对于 file 命令无法区分的格式（如 .rst → text/plain），应在 `[extensions]` 中配置覆盖。

| MIME 类型 | 典型扩展名 | pandoc 读取格式 |
|---|---|---|
| text/x-tex | .tex | latex |
| text/troff | .1–.8, .man | man |
| text/html | .html, .htm | html |
| application/xhtml+xml | .xhtml | html |
| application/epub+zip | .epub | epub |
| application/vnd.oasis.opendocument.text | .odt | odt |
| application/vnd.openxmlformats-officedocument.wordprocessingml.document | .docx | docx |
| text/x-rst | .rst | rst |
| text/x-org | .org | org |
| text/rtf / application/rtf | .rtf | rtf |
| text/x-opml | .opml | opml |
| application/docbook+xml | .dbk | docbook |
| application/x-fictionbook+xml | .fb2 | fb2 |
| application/x-ipynb+json | .ipynb | ipynb |
| text/x-creole | .creole | creole |
| text/x-textile | .textile | textile |

| 后端 | name | priority | 外部依赖 |
|---|---|---|---|
| PandocExtractor | `pandoc` | 10 | `pandoc` CLI |

### 4.3 Man / GNU Info（系统命令）

| 后端 | name | priority | 注册 MIME | 外部依赖 |
|---|---|---|---|---|
| ManExtractor | `man` | 5 | text/troff | `groff`, `col` |
| InfoExtractor | `info` | 5 | text/x-info | `info` (GNU) |

### 4.4 PDF

| 后端 | name | priority | 注册 MIME | 外部依赖 |
|---|---|---|---|---|
| PyMuPDFExtractor | `pymupdf` | 15 | application/pdf | `pymupdf` 包 |
| TikaExtractor | `tika` | 20 | application/pdf（及 Office，见 4.5） | `tika` 包 + JVM |
| UnstructuredExtractor | `unstructured` | 30 | application/pdf（及图片，见 4.6） | `unstructured` 包 |

### 4.5 Office 文档

三种后端均注册相同 MIME，通过优先级/配置选择：

| MIME 类型 | 典型扩展名 |
|---|---|
| application/msword | .doc |
| application/vnd.openxmlformats-officedocument.wordprocessingml.document | .docx |
| application/vnd.ms-excel | .xls |
| application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | .xlsx |
| application/vnd.ms-powerpoint | .ppt |
| application/vnd.openxmlformats-officedocument.presentationml.presentation | .pptx |
| application/vnd.oasis.opendocument.text | .odt |
| application/vnd.oasis.opendocument.spreadsheet | .ods |
| application/vnd.oasis.opendocument.presentation | .odp |

| 后端 | name | priority | 说明 | 外部依赖 |
|---|---|---|---|---|
| NativeDocxExtractor | `python_docx` | 18 | 仅 .docx，提取段落和表格 | `python-docx` 包 |
| NativeXlsxExtractor | `openpyxl` | 18 | 仅 .xlsx，逐行输出单元格 | `openpyxl` 包 |
| NativePptxExtractor | `python_pptx` | 18 | 仅 .pptx，提取文本框 | `python-pptx` 包 |
| LibreOfficeExtractor | `libreoffice` | 25 | 全系列 Office+ODF，headless 模式转 txt（见注） | `libreoffice` CLI |
| TikaExtractor | `tika` | 20 | 全系列，见 4.4 | `tika` 包 + JVM |

**LibreOffice 输出文件处理**：`libreoffice --headless --convert-to txt` 默认将结果写到
源文件所在目录，文件名为 `<原名>.txt`，无法自定义。实现时必须：
1. 用 `tempfile.mkdtemp()` 创建临时目录。
2. 通过 `--outdir <tmpdir>` 将输出重定向到临时目录。
3. 读取 `<tmpdir>/<原文件名去扩展名>.txt` 的内容。
4. 在 `finally` 块中用 `shutil.rmtree(tmpdir)` 清理。

### 4.6 图片 OCR

所有图片 OCR 后端注册以下 MIME：
`image/png, image/jpeg, image/tiff, image/bmp, image/webp, image/gif`

| 后端 | name | priority | 说明 | 外部依赖 | 可配置项 |
|---|---|---|---|---|---|
| TesseractExtractor | `tesseract` | 40 | 传统 OCR | `pytesseract` 包 + `tesseract` CLI | `lang`（语言串）, `psm`（页面分割模式） |
| EasyOCRExtractor | `easyocr` | 45 | ML OCR，多语言 | `easyocr` 包 | `langs`（语言列表） |
| PaddleOCRExtractor | `paddleocr` | 46 | 百度 OCR，中文效果佳 | `paddleocr` 包 | `lang` |
| UnstructuredExtractor | `unstructured` | 30 | 内置 Tesseract，见 4.4 | `unstructured` 包 | — |
| OpenAIVisionExtractor | `openai_vision` | 50 | AI 识图，可识内容也可提取文字 | `openai` 包 | `mode`（`extract_text`\|`describe`）, `model`, `prompt` |

### 4.8 压缩包递归提取

使用 Python 标准库实现，无外部依赖。

| 后端 | name | priority | 注册 MIME | 外部依赖 | 说明 |
|---|---|---|---|---|---|
| ArchiveExtractor | `archive_recurse` | 10 | application/zip, application/x-tar, application/gzip, application/x-bzip2, application/x-xz, application/x-lzma | 无（标准库） | ZIP 用 `zipfile`；TAR.* 用 `tarfile(mode='r:*')`；gzip/bzip2/xz/lzma 单文件用对应标准库模块解压后递归提取 |
| SevenZipExtractor | `7zip_recurse` | 10 | application/x-7z-compressed | `py7zr` 包 | 7-Zip 格式 |
| RarExtractor | `rar_recurse` | 10 | application/x-rar, application/vnd.rar, application/x-rar-compressed | `rarfile` 包 | RAR 格式（需系统安装 `unrar` 或 `bsdtar`） |

**默认禁用**：所有后端的 `available()` 均检查 `self._cfg.get("enabled", False)`，未显式开启时返回 False。SevenZipExtractor 和 RarExtractor 还额外检查对应库是否已安装。

**`--allow-archive` 标志**：在 CLI 层对 `archive_recurse`、`7zip_recurse`、`rar_recurse` 统一注入 `enabled=True`。

**ArchiveExtractor 提取逻辑**：
1. 依次检测格式：`zipfile.is_zipfile()` → `tarfile.is_tarfile()` → 按 MIME 做单文件解压。
2. 多成员格式（ZIP/TAR）：先检查所有成员未压缩大小之和，超 `max_bytes` 则抛异常；解压到临时目录，遍历每个文件成员调用 `registry.extract()` 递归处理。
3. 单文件压缩（gzip/bzip2/xz/lzma）：流式解压并累计已输出字节数，超 `max_bytes` 立即抛异常；将解压后的文件（以 `path.stem` 命名）放入临时目录，调用 `registry.extract()` 处理。
4. 每个成员输出：`=== {内部路径} ===\n{文本}`，成员间以空行分隔；单个成员失败记录 `=== {路径} === (error: {原因})` 并继续。
5. `finally` 块 `shutil.rmtree(tmpdir)` 清理。

**配置项**（各后端名均支持相同键）：

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | bool | false | 必须显式设为 true 才生效 |
| `max_bytes` | int | 104857600 | 最大解压总字节数（100 MB） |

### 4.9 音频 / 视频 ASR

ASR 后端注册以下 MIME：

**音频**：audio/mpeg (.mp3), audio/x-wav (.wav), audio/ogg (.ogg),
audio/flac (.flac), audio/mp4 (.m4a), audio/aac (.aac), audio/webm

**视频**：video/mp4 (.mp4), video/x-matroska (.mkv), video/quicktime (.mov),
video/x-msvideo (.avi), video/webm

视频文件需先提取音频轨再送 ASR；三个后端共用同一工具函数（见下）。

**共享工具函数** `backends/_util.py`：

```python
def extract_audio(path: Path) -> Path:
    """用 ffmpeg 将 path 的音频轨提取为临时 WAV 文件，返回临时文件路径。
    调用方负责在使用完毕后删除该文件。
    仅当 path 的 MIME 为视频类型时调用；音频文件直接传入 ASR，无需提取。"""
```

实现要点：
- 用 `tempfile.mkstemp(suffix=".wav")` 创建临时文件。
- 调用 `ffmpeg -i <path> -vn -ar 16000 -ac 1 -f wav <tmpwav>`（单声道 16 kHz，Whisper 推荐格式）。
- 返回临时文件路径；ASR 后端在 `finally` 块中 `os.unlink(tmpwav)` 清理。

| 后端 | name | priority | 外部依赖 | 可配置项 |
|---|---|---|---|---|
| OpenAIWhisperExtractor | `openai_whisper` | 30 | `openai` 包 | `model`（默认 whisper-1）, `language`, `response_format` |
| WhisperLocalExtractor | `whisper_local` | 35 | `openai-whisper` 包 | `model`（tiny/base/small/medium/large）, `language` |
| FasterWhisperExtractor | `faster_whisper` | 33 | `faster-whisper` 包 | `model`, `language`, `device`（cpu/cuda） |

---

## 五、配置文件格式（all2txt.yaml）

```yaml
# 1. 按 MIME 覆盖后端顺序（列出的后端优先，其余按默认 priority 追加）
mime:
  "application/pdf":
    backends: [pymupdf, tika, unstructured]
  "image/png":
    backends: [openai_vision, tesseract]

# 2. 按后端名称传入配置（可选）
extractor:
  openai_vision:
    mode: extract_text    # extract_text | describe
    model: gpt-4o
    # prompt: "..."       # 可选，覆盖默认系统提示

  openai_whisper:
    model: whisper-1
    language: zh
    response_format: text   # text | srt | vtt | verbose_json

  whisper_local:
    model: base
    language: zh

  faster_whisper:
    model: base             # tiny | base | small | medium | large
    language: zh
    device: cpu             # cpu | cuda

  tesseract:
    lang: eng+chi_sim
    psm: 3

  easyocr:
    langs: [en, ch_sim]

  paddleocr:
    lang: ch

# 3. 扩展名覆盖（仅当 file 命令返回通用类型时生效）
extensions:
  .rst: text/x-rst
  .org: text/x-org
  .ipynb: application/x-ipynb+json
  .fb2: application/x-fictionbook+xml
  .opml: text/x-opml
  .creole: text/x-creole
```

---

## 六、扩展指南

新增后端只需：
1. 在 `backends/` 新建 `.py`，继承 `Extractor`，设置 `name`、`priority`。
2. 在 `__init__` 中从 `self._cfg` 读取所需配置（带默认值）。
3. 用 `@registry.register("mime/type", ...)` 装饰类。
4. 在 `backends/__init__.py` 中 import 该模块。

无需修改任何已有代码。
