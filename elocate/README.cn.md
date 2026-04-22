# elocate

elocate 是一个面向本地文档的语义搜索工具，类似 `mlocate`，但使用向量引擎进行语义匹配。

elocate 不内含任何推理权重，embedding 推理完全委托给外部 OpenAI 兼容服务（ollama、OpenAI、LM Studio 等）。

[English](README.md)

## 安装

```bash
pip install elocate
```

索引和搜索前需要先启动 OpenAI 兼容的 embedding 服务。
本地 CPU 推理推荐使用 [ollama](https://ollama.com)：

```bash
ollama pull qwen3-embedding:4b
ollama serve
```

## 使用方法

构建索引：

```bash
elocate-updatedb
elocate-updatedb --debug   # 查看分批抽取/嵌入耗时
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
  # 纯文本笔记
  - path: ~/notes
    extensions: [.md, .org, .txt]
    exclude: [.venv, .git, __pycache__]

  # PDF/Word 文档
  - path: ~/Documents
    extensions:
      - .pdf
      - .docx
      - suffix:.tar.gz
    exclude:
      - .claude/*
      - "*.pyc"
```

### 扩展名规则

`dirs[].extensions` 现在支持三种规则：

- `.md`：按最后一段扩展名精确匹配
- `suffix:.tar.gz`：按完整文件名后缀匹配，适合复合扩展名
- `glob:*.*`：按 `Path.name` 做 shell 风格 glob 匹配

示例：

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

当你希望把绝大多数“带点文件名”都交给 `all2txt` 自动做 MIME 判断时，可以用
`glob:*.*`。当你需要精确覆盖 `.tar.gz`、`.user.js` 这类复合后缀时，用 `suffix:`
更合适。

### 排除规则

`dirs[].exclude` 是可选项，并且优先级高于 `extensions`：

- `.venv`：排除任意路径段名称为 `.venv` 的目录或文件；命中目录时会直接停止向下扫描
- `.claude/*`：按相对于当前 `path` 的路径做 glob 排除
- `*.pyc`：排除匹配到的相对路径文件

像 `.venv`、`.git`、`__pycache__` 这类噪音目录，推荐直接写名称规则；只想排除局部
路径时，再用相对路径 glob。

`all2txt` 现在是必选依赖，也是唯一的文本抽取路径。旧配置中的 `extractor:`
字段会被兼容忽略。

### 索引批处理控制

- `summary_model`：指定走摘要索引路径时使用的总结模型
- `rag_entropy_min` / `rag_entropy_max`：限制允许直接 raw embedding 的信息熵区间
- `rag_min_paragraph_length`：典型段落长度中位数低于该值时，改走 summary 路径
- `embed_batch_files`：限制单批在内存中等待嵌入的文件数量
- `embed_batch_chars`：限制单批在内存中等待嵌入的文本字符总量
- `elocate-updatedb --debug` 会输出批次级和全局级性能计数，方便判断瓶颈是在
  抽取、切分、embedding 还是写库
- `--debug` 还会保留 `all2txt` 的 backend 选择日志，同时继续抑制
  `openai` / `httpx` / `httpcore` 的噪音调试输出

### 使用 OpenAI 官方 API

```yaml
embedding_model: text-embedding-3-small
openai_base_url: https://api.openai.com/v1
openai_api_key: sk-...
```

## 作者

Shell.Xu

## 版权与授权

MIT License. Copyright (c) 2026 Shell.Xu.
