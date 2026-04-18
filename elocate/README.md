# elocate

A local semantic document search tool using vector embeddings, similar to `mlocate` but with semantic matching.

[中文说明](README.cn.md)

## Installation

```bash
pip install elocate
# Optional: for non-plaintext file support (PDF, DOCX, images)
pip install elocate[all2txt]
# Optional: for OpenAI-compatible embedding API (ollama, OpenAI, LM Studio)
pip install elocate[openai]
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
embedding_model: all-MiniLM-L6-v2
embedder_backend: local    # "local" (CPU/GPU) or "openai" (API)
top_k: 10
chunk_size: 500
chunk_overlap: 50

dirs:
  - path: ~/notes
    extensions: [.md, .org, .txt]
    extractor: plaintext

  - path: ~/Documents
    extensions: [.pdf, .docx, .md]
    extractor: all2txt
```

### Using OpenAI-compatible embedding API

For ollama (local GPU inference):

```yaml
embedder_backend: openai
embedding_model: nomic-embed-text
openai_base_url: http://localhost:11434/v1
openai_api_key: ""
```

For OpenAI:

```yaml
embedder_backend: openai
embedding_model: text-embedding-3-small
openai_base_url: https://api.openai.com/v1
openai_api_key: sk-...
```

## Author

Shell.Xu

## License

MIT License. Copyright (c) 2024 Shell.Xu.
