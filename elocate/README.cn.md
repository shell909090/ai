# elocate

elocate 是一个面向本地文档的语义搜索工具，类似 `mlocate`，但使用向量引擎进行语义匹配。

[English](README.md)

## 安装

```bash
pip install elocate
# 可选：支持 PDF、DOCX、图片等非纯文本格式
pip install elocate[all2txt]
# 可选：使用 OpenAI 兼容 Embedding API（ollama、OpenAI、LM Studio）
pip install elocate[openai]
```

## 使用方法

构建索引：

```bash
elocate-updatedb
```

语义搜索：

```bash
elocate "你的查询"
elocate "查询" -k 5                     # 返回前 5 条结果
elocate "查询" -p "正则"               # 正则二次过滤
elocate "查询" --config /path/to.yaml  # 指定配置文件
elocate "查询" --debug                 # 启用调试日志
```

## 配置文件

创建 `~/.config/elocate/config.yaml`：

```yaml
index_path: ~/.local/share/elocate/index
embedding_model: all-MiniLM-L6-v2
embedder_backend: local    # "local"（本地 CPU/GPU）或 "openai"（API）
top_k: 10
chunk_size: 500
chunk_overlap: 50

dirs:
  # 纯文本笔记
  - path: ~/notes
    extensions: [.md, .org, .txt]
    extractor: plaintext

  # PDF/Word 文档（需安装 all2txt）
  - path: ~/Documents
    extensions: [.pdf, .docx, .md]
    extractor: all2txt
```

### 使用 OpenAI 兼容 Embedding API

以 ollama（本地 GPU 推理）为例：

```yaml
embedder_backend: openai
embedding_model: nomic-embed-text
openai_base_url: http://localhost:11434/v1
openai_api_key: ""
```

以 OpenAI 官方 API 为例：

```yaml
embedder_backend: openai
embedding_model: text-embedding-3-small
openai_base_url: https://api.openai.com/v1
openai_api_key: sk-...
```

## 作者

Shell.Xu

## 版权与授权

MIT License. Copyright (c) 2026 Shell.Xu.
