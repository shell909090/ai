# elocate

A local semantic document search tool using vector embeddings, similar to `mlocate` but with semantic matching.

elocate does not bundle any inference weights. Embedding is delegated entirely to an external OpenAI-compatible service (ollama, OpenAI, LM Studio, etc.).

[中文说明](README.cn.md)

## Installation

```bash
pip install elocate
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
elocate-updatedb --debug   # show batch-level extract/embed timing
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
summary_model: qwen3.5:4b
chunk_size: 2048
chunk_overlap: 200
embed_batch_files: 64
embed_batch_chars: 65536
rag_entropy_min: 4.5
rag_entropy_max: 8.8
rag_min_paragraph_length: 80

dirs:
  - path: ~/notes
    extensions: [.md, .org, .txt]
    exclude: [.venv, .git, __pycache__]

  - path: ~/Documents
    extensions:
      - .pdf
      - .docx
      - suffix:.tar.gz
    exclude:
      - .claude/*
      - "*.pyc"
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

### Exclude Rules

`dirs[].exclude` is optional and is evaluated before `extensions`:

- `.venv` — exclude any path segment with this exact name and prune that subtree
- `.claude/*` — exclude paths relative to the configured base directory
- `*.pyc` — exclude matching relative file paths

Use name rules for noisy directories such as `.venv`, `.git`, and `__pycache__`.
Use relative globs when you only want to skip part of a tree.

`all2txt` is now a required dependency and the only extraction path. Legacy
`extractor:` config values are ignored for compatibility.

### Indexing Batch Controls

- `summary_model` chooses the model used when a file is routed to summary-first indexing
- `rag_entropy_min` / `rag_entropy_max` bound the entropy band allowed for direct raw embedding
- `rag_min_paragraph_length` sets the median paragraph-length threshold for direct raw embedding
- `embed_batch_files` limits how many extracted files may wait in memory before a flush
- `embed_batch_chars` limits the total extracted character count before a flush
- `elocate-updatedb --debug` prints per-batch and overall timing so you can see whether
  extraction, chunking, embedding, or DB writes are the bottleneck
- `--debug` also shows the active semantic-routing thresholds, one route decision per file,
  and summary-model throughput as raw/source chars per second plus summary chars per second
- file writes emit `info` logs with the indexed path, route, action, and write status so you
  can see which files were persisted
- `--debug` also keeps `all2txt` backend-selection logs visible while still muting
  noisy `openai` / `httpx` / `httpcore` debug output

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
