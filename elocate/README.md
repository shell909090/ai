# elocate

A local semantic document search tool using vector embeddings, similar to `mlocate` but with semantic matching.

[中文说明](README.cn.md)

## Installation

```bash
pip install elocate
# Optional: for non-plaintext file support (PDF, DOCX, images)
pip install elocate[all2txt]
```

## Usage

Build the index:

```bash
elocate-updatedb
```

Search documents:

```bash
elocate "your query here"
elocate "query" -k 5           # top 5 results
elocate "query" -p "pattern"   # regex post-filter
elocate "query" --debug        # enable debug logging
```

## Configuration

Create `~/.config/elocate/config.yaml`:

```yaml
index_path: ~/.local/share/elocate/index
embedding_model: all-MiniLM-L6-v2
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

  - path: ~/photos
    extensions: [.jpg, .png]
    extractor: all2txt
    extractor_config:
      mime:
        "image/jpeg":
          backends: [openai_vision]
      extractor:
        openai_vision:
          model: gpt-4o
```

## Author

Shell.Xu

## License

MIT License. Copyright (c) 2024 Shell.Xu.
