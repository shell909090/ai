# all2txt

从任意格式文件中提取纯文本，专为 RAG（检索增强生成）流水线和向量搜索引擎设计。

[English README](README.md)

## 特性

- **自动 MIME 检测**：通过 `file --mime-type` 识别文件类型，无需依赖扩展名
- **多后端自动 fallback**：按优先级逐个尝试后端，缺失工具自动跳过
- **完全可配置**：通过 `all2txt.yaml` 覆盖后端顺序，并为每个后端传入配置
- **胶水模式设计**：封装外部 CLI 工具，无强制重依赖
- **易于扩展**：新增后端只需新建一个文件加一行装饰器

## 支持格式

| 类别 | 格式 | 后端 |
|---|---|---|
| 纯文本 / CSV | `.txt`、`.csv`、`.md`、`.py`、`.tsv` | `plaintext` |
| 文档 | `.docx`、`.odt`、`.epub`、`.rtf` | `pandoc`、`python_docx`、`libreoffice`、`tika` |
| 电子表格 | `.xlsx`、`.ods` | `openpyxl`、`libreoffice`、`tika` |
| 演示文稿 | `.pptx`、`.odp` | `python_pptx`、`libreoffice`、`tika` |
| 旧版 Office | `.doc`、`.xls`、`.ppt` | `libreoffice`、`tika` |
| PDF | `.pdf` | `pdftotext`、`pymupdf`、`tika`、`unstructured` |
| 标记语言 | `.html`、`.tex`、`.rst`、`.org`、`.textile`、`.creole` | `pandoc` |
| Man 手册页 | `.1`–`.8` | `man`（groff+col）、`pandoc` |
| GNU Info | `.info` | `info` |
| 图片（OCR） | `.png`、`.jpg`、`.tiff`、`.bmp`、`.webp`、`.gif` | `tesseract`、`easyocr`、`paddleocr`、`unstructured`、`openai_vision` |
| 音频 / 视频 | `.mp3`、`.wav`、`.mp4`、`.mkv`、`.mov` 等 | `openai_whisper`、`faster_whisper`、`whisper_local` |
| 压缩包 | `.zip`、`.tar`、`.tar.gz`、`.tar.bz2`、`.tar.xz`、`.7z`、`.rar` | `archive_recurse`、`7zip_recurse`、`rar_recurse` |
| 单文件压缩 | `.gz`、`.bz2`、`.xz`、`.lzma` | `archive_recurse`（默认禁用，需 `--allow-archive`） |

## 安装

要求 Python ≥ 3.11。默认仅安装 `pyyaml`，可选后端需单独安装其依赖。

```bash
# 最小安装（纯文本、pandoc、groff 等均为外部 CLI）
pip install all2txt

# 附带 PyMuPDF（快速 PDF 提取）
pip install "all2txt[pymupdf]"

# 附带 Apache Tika（PDF + Office，需 JVM）
pip install "all2txt[tika]"

# 附带 unstructured（PDF + 图片 OCR）
pip install "all2txt[unstructured]"
```

使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv add all2txt
uv add "all2txt[pymupdf]"
uv sync --extra 7zip   # 7-Zip 支持
uv sync --extra rar    # RAR 支持（还需：apt install unrar）
```

## 使用方法

```bash
# 提取一个或多个文件的文本
all2txt 文档.pdf 报告.docx 图片.png

# 强制指定 MIME 类型
all2txt --mime text/x-rst README.rst

# 使用自定义配置文件
all2txt --config ~/my-all2txt.yaml notes.epub

# 查看后端选择信息（INFO 级别）
all2txt --verbose 文档.pdf

# 启用调试日志
all2txt --debug 未知文件

# 启用压缩包递归提取（默认禁用）
all2txt --allow-archive 归档.zip
```

输出写入 stdout；错误信息写入 stderr，退出码为 1。

## 配置文件（all2txt.yaml）

放在工作目录下，或通过 `--config PATH` 指定。

```yaml
# 按 MIME 类型覆盖后端顺序
mime:
  "application/pdf":
    backends: [pymupdf, tika, unstructured]
  "image/png":
    backends: [openai_vision, tesseract]

# 各后端配置
extractor:
  openai_vision:
    mode: extract_text    # extract_text（提取文字）| describe（描述内容）
    model: gpt-4o

  openai_whisper:
    model: whisper-1
    language: zh

  faster_whisper:
    model: base
    language: zh
    device: cpu           # cpu | cuda

  tesseract:
    lang: eng+chi_sim
    psm: 3

  easyocr:
    langs: [en, ch_sim]

  paddleocr:
    lang: ch

# 扩展名覆盖（仅当 file 命令返回通用类型时生效）
extensions:
  .rst: text/x-rst
  .org: text/x-org
  .ipynb: application/x-ipynb+json
```

## 新增后端

1. 在 `all2txt/backends/` 新建 `.py` 文件
2. 继承 `Extractor`，设置 `name` 和 `priority`
3. 用 `@registry.register("mime/type", ...)` 装饰类
4. 在 `backends/__init__.py` 中添加 `from . import my_backend`

无需修改任何已有代码。

## 开发

```bash
# 格式化
make fmt

# 静态检查
make lint

# 语法检查
make build

# 单元测试及覆盖率
make unittest
```

开发依赖通过 `uv` 安装：

```bash
uv sync --extra dev
```

## 作者

Shell.Xu

## 许可证

MIT License — 详见 [LICENSE](LICENSE)。
