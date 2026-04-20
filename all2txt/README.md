# all2txt

Extract plain text from any file format, designed for RAG (Retrieval-Augmented Generation) pipelines and vector search engines.

[中文说明](README.cn.md)

## Features

- **Three-tier MIME detection** — `file --mime-type`, then `mimetypes`, then an internal extension map
- **Multi-backend fallback** — backends are tried in priority order; missing tools are skipped automatically
- **Fully configurable** — override backend order and pass per-backend settings via `all2txt.yaml`
- **Glue-mode design** — wraps external CLI tools; no mandatory heavy dependencies
- **HTML encoding normalization for pandoc** — HTML/XHTML is decoded from BOM / `<meta charset>` / `http-equiv` before pandoc sees it
- **Extensible** — add a new backend in a single file with one decorator

## Supported Formats

| Category | Formats | Backend(s) |
|---|---|---|
| Plain text / CSV | `.txt`, `.csv`, `.md`, `.py`, `.tsv` | `plaintext` |
| Documents | `.docx`, `.odt`, `.epub`, `.rtf` | `pandoc`, `native_python_docx`, `libreoffice`, `tika` |
| Spreadsheets | `.xlsx`, `.ods` | `openpyxl`, `libreoffice`, `tika` |
| Presentations | `.pptx`, `.odp` | `python_pptx`, `libreoffice`, `tika` |
| Legacy Office | `.doc`, `.xls`, `.ppt` | `libreoffice`, `tika` |
| PDF | `.pdf` | `pdftotext`, `pymupdf`, `tika`, `unstructured` |
| Markup | `.html`, `.tex`, `.rst`, `.org`, `.textile`, `.creole` | `pandoc` |
| Man pages | `.1`–`.8` | `man` (groff+col), `pandoc` |
| GNU Info | `.info` | `info` |
| Images (OCR) | `.png`, `.jpg`, `.tiff`, `.bmp`, `.webp`, `.gif` | `tesseract`, `easyocr`, `paddleocr`, `unstructured`, `openai_vision` |
| Audio / Video | `.mp3`, `.wav`, `.mp4`, `.mkv`, `.mov`, … | `openai_whisper`, `faster_whisper`, `whisper_local` |
| Archives | `.zip`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.7z`, `.rar` | `archive_recurse`, `7zip_recurse`, `rar_recurse` |
| Single-file compressed | `.gz`, `.bz2`, `.xz`, `.lzma` | `archive_recurse` (disabled by default, use `--allow-archive`) |

## Installation

Requires Python ≥ 3.11. Only `pyyaml` is installed by default; optional backends require their own dependencies.

```bash
# Minimal install (plain text, pandoc, pdftotext, groff — all external CLIs)
pip install all2txt

# With PyMuPDF (fast PDF)
pip install "all2txt[pymupdf]"

# With Apache Tika (PDF + Office, needs JVM)
pip install "all2txt[tika]"

# With unstructured (PDF + image OCR)
pip install "all2txt[unstructured]"
```

For legacy HTML/XHTML encodings handled by the `pandoc` backend, also install `chardet`:

```bash
uv pip install chardet
```

Using [uv](https://github.com/astral-sh/uv):

```bash
uv add all2txt
uv add "all2txt[pymupdf]"
uv sync --extra 7zip   # 7-Zip support
uv sync --extra rar    # RAR support (also needs: apt install unrar)
```

## Usage

```bash
# Extract text from one or more files
all2txt document.pdf report.docx image.png

# Force a specific MIME type
all2txt --mime text/x-rst README.rst

# Use a custom config file
all2txt --config ~/my-all2txt.yaml notes.epub

# Show backend selection info (INFO level)
all2txt --verbose document.pdf

# Enable debug logging
all2txt --debug mystery-file

# Enable archive/zip recursive extraction (disabled by default)
all2txt --allow-archive archive.zip
```

Output is written to stdout; errors go to stderr with exit code 1.

Notes:

- For `text/html` and `application/xhtml+xml`, the `pandoc` backend normalizes the source to UTF-8 before invoking pandoc.
- Header-declared encodings (`<meta charset>` / `http-equiv`) take precedence; `chardet` is only used as a fallback.

## Configuration (`all2txt.yaml`)

Place `all2txt.yaml` in the working directory, or pass `--config PATH`.

```yaml
# Override backend order per MIME type
mime:
  "application/pdf":
    backends: [pymupdf, tika, unstructured]
  "image/png":
    backends: [openai_vision, tesseract]

# Per-backend configuration
extractor:
  openai_vision:
    mode: extract_text    # extract_text | describe
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

# Extension overrides (when file(1) returns a generic MIME type)
extensions:
  .rst: text/x-rst
  .org: text/x-org
  .ipynb: application/x-ipynb+json
```

## Adding a Backend

1. Create `all2txt/backends/my_backend.py`
2. Inherit from `Extractor`, set `name` and `priority`
3. Decorate with `@registry.register("mime/type", ...)`
4. Add `from . import my_backend` to `backends/__init__.py`

No other files need to change.

## Development

```bash
# Format
make fmt

# Lint
make lint

# Syntax check
make build

# Unit tests with coverage
make unittest
```

Requires `uv` and the `dev` extras:

```bash
uv sync --extra dev
```

## Author

Shell.Xu

## License

MIT License — see [LICENSE](LICENSE) for details.
