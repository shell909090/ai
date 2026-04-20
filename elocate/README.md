# elocate

A local semantic document search tool using vector embeddings, similar to `mlocate` but with semantic matching.

elocate does not bundle any inference weights. Embedding is delegated entirely to an external OpenAI-compatible service (ollama, OpenAI, LM Studio, etc.).

[中文说明](README.cn.md)

## Installation

```bash
pip install elocate
# Optional: for non-plaintext file support (PDF, DOCX, images, etc.)
pip install elocate[all2txt]
```

An OpenAI-compatible embedding service must be running before indexing or searching.
For local CPU inference, [ollama](https://ollama.com) is recommended:

```bash
ollama pull qwen3-embedding:4b
ollama serve
```

## Usage

Build the index:

```bash
elocate-updatedb
```

Search documents:

```bash
elocate "your query here"
elocate "query" -k 5                    # top 5 results
elocate "query" -p "pattern"            # regex post-filter
elocate "query" --config /path/to.yaml  # custom config file
elocate "query" --debug                 # enable debug logging
```

## Configuration

Create `~/.config/elocate/config.yaml`:

```yaml
index_path: ~/.local/share/elocate/index
embedding_model: qwen3-embedding:4b
openai_base_url: http://localhost:11434/v1
openai_api_key: ""
top_k: 10
chunk_size: 500
chunk_overlap: 50

dirs:
  - path: ~/notes
    extensions: [.md, .org, .txt]
    extractor: plaintext

  - path: ~/Documents
    extensions:
      - .pdf
      - .docx
      - suffix:.tar.gz
    extractor: all2txt
```

### Extension Rules

`dirs[].extensions` supports three rule forms:

- `.md` — exact match on the last extension segment
- `suffix:.tar.gz` — full filename suffix match for compound extensions
- `glob:*.*` — shell-style glob match on `Path.name`

Examples:

```yaml
dirs:
  - path: ~/mixed-data
    extensions:
      - glob:*.*
    extractor: all2txt
    extractor_config:
      extractors:
        archive_recurse:
          enabled: true
        7zip_recurse:
          enabled: true
        rar_recurse:
          enabled: true
```

Use `glob:*.*` when you want elocate to pass nearly all dotted filenames to `all2txt`
and let MIME detection choose the backend. Use `suffix:` when you need precise control
for names such as `.tar.gz` or `.user.js`.

### Using OpenAI API

```yaml
embedding_model: text-embedding-3-small
openai_base_url: https://api.openai.com/v1
openai_api_key: sk-...
```

## Author

Shell.Xu

## License

MIT License. Copyright (c) 2026 Shell.Xu.
