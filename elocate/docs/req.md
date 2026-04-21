# elocate 需求文档

## 概述

elocate 是一个面向用户文档的本地语义搜索工具，类似 mlocate，但使用向量引擎进行语义匹配。
目标文件类型包括 `.md`、`.txt`、`.rst`、`.org` 等多种纯文本格式。
文件格式转换由外部工具完成，elocate 仅处理纯文本内容。

## 功能需求

### 搜索模式

**Mode 1（当前实现目标）**

1. 用户执行 `elocate-updatedb` 构建向量索引
2. 用户执行 `elocate <query>` 进行语义搜索
3. 系统通过 LanceDB 向量索引召回 Top-K 文档
4. 可选：通过正则表达式对召回结果做二次过滤

**Mode 2（规划中，暂不实现）**

在无索引文件的情况下，先使用 ripgrep 做关键词一级过滤，再对候选集做向量相似度排序。
核心挑战：如何从语义查询中提取适合 rg 的关键词。

### CLI 接口

```
elocate <query> [-k TOP_K] [-p PATTERN] [--debug]
```
语义搜索，输出匹配文档列表（含相似度分数）。

```
elocate-updatedb [--debug]
```
扫描配置目录，构建或全量更新向量索引。

### 索引触发

`elocate-updatedb` 由用户通过外部机制触发（如用户级 cron），不在本项目范围内。

### 配置

用户级配置文件，位于 `~/.config/elocate/config.toml`：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `index_dirs` | `list[str]` | `[]` | 需要索引的目录列表 |
| `index_path` | `str` | `~/.local/share/elocate/index` | 索引存储路径 |
| `file_extensions` | `list[str]` | `[".md",".txt",".rst",".org"]` | 支持的扩展名 |
| `top_k` | `int` | `10` | 默认召回数量 |
| `embedding_model` | `str` | `"all-MiniLM-L6-v2"` | 模型名（local 为 sentence-transformers 名；openai 为 API 模型名） |
| `embedder_backend` | `str` | `"local"` | 嵌入后端：`"local"`（sentence-transformers 本地推理）或 `"openai"`（OpenAI 兼容 API，支持 ollama 等） |
| `openai_base_url` | `str` | `""` | OpenAI 兼容 API 的 base URL，例如 `http://localhost:11434/v1`（ollama）或 `https://api.openai.com/v1` |
| `openai_api_key` | `str` | `""` | API key；ollama 可留空或填任意字符串 |

### 扩展名匹配

当前仅支持显式列举扩展名的方式不足以覆盖复合扩展名和归档文件场景，需要补充扩展名模糊匹配能力：

1. 配置中的扩展名规则除精确匹配外，还必须支持模糊匹配。
2. 扩展名匹配必须基于完整文件名后缀，不得只看最后一段后缀；应能覆盖 `.tar.gz`、`.tar.bz2`、`.tar.xz` 等复合扩展名。
3. 用户不应被迫为同一类文件手工枚举大量扩展名变体；应能用少量规则覆盖一组相关扩展名。
4. 具体模糊匹配语法在设计阶段确定，但必须保持配置可读、可维护，并与现有 `extensions` 配置兼容。

### 文本抽取依赖

当前将 `all2txt` 作为可选依赖会导致配置可用但运行时报缺依赖，不符合“开箱可用”的目标，需要调整为必选能力：

1. `all2txt` 必须作为 elocate 的默认安装依赖随项目一起安装。
2. 文本抽取必须统一通过 `all2txt` 执行，不再保留独立的 `plaintext` 抽取路径。
3. 配置层不得要求用户在常规使用场景下区分 `plaintext` 与 `all2txt` 两套 extractor。
4. 旧配置若显式写了 `extractor` 字段，系统应兼容读取并忽略该字段，不影响运行。

### 批量嵌入调度与性能观测

当前索引流程先收集全部待嵌入文本再统一调用 embedding，内存占用和失败恢复都不理想，需要补充分批调度与性能观测能力：

1. 系统必须先扫描全部文件并过滤无需处理的文件，再对待处理文件逐个抽取文本。
2. 系统必须按“待嵌入文件数”与“待嵌入文本字符总量”两个阈值触发批量 embedding，任一阈值达到即立刻 flush。
3. 单个文件若抽取后文本量已超过字符阈值，必须允许其单独成批执行 embedding。
4. 阈值必须放入配置文件，并提供默认值；用户可按模型窗口和机器性能调整。
5. 抽取失败只能影响当前文件，不得导致已成功 flush 的批次失效。
6. `--debug` 模式下必须输出索引性能计数，至少能观察抽取、切分、embedding、写库各阶段的吞吐与耗时。
7. `--debug` 不得无差别放开第三方库的调试日志；OpenAI、httpx、httpcore 等外部依赖的 debug 输出必须默认抑制，避免冲掉批次性能信息。
8. `--debug` 需要定向开放 `all2txt` 的 backend 选择日志，至少应能看到文件 MIME、可用 backend 与最终采用的 backend，便于定位 OCR 和格式抽取问题。

### 扫描排除规则

当前目录扫描只支持按 `path + extensions` 纳入文件，无法排除 `.venv`、`.git`、`__pycache__`、`.claude` 等无关目录，导致误扫和性能浪费，需要补充排除能力：

1. 每个目录配置必须支持独立的 `exclude` 规则列表，作用域仅限该 `path` 对应的扫描树。
2. 排除规则必须同时支持“目录/文件名快捷排除”和“相对路径模式排除”，以便用少量规则覆盖 `.venv`、`*.pyc`、`.claude/**` 等场景。
3. 被 `exclude` 命中的目录必须在扫描阶段直接停止向下遍历，避免进入其子树。
4. 被 `exclude` 命中的文件不得进入扩展名匹配、文本抽取、embedding 与写库阶段。
5. `exclude` 与 `extensions` 同时存在时，`exclude` 优先级更高。
6. 配置语法必须保持可读，并与现有 `dirs` 配置兼容；未配置 `exclude` 时行为必须保持现状。

## 非功能需求

- 语言：Python 3.11+，使用 uv 管理依赖
- 向量数据库：LanceDB（本地，无需服务端）
- 嵌入后端：支持两种模式
  - `local`：sentence-transformers 本地推理（默认，无需网络，适合 CPU/GPU/MPS）
  - `openai`：OpenAI 兼容 Embeddings API（适合 ollama、OpenAI、任何兼容服务）；需安装 `openai` 可选依赖
- 文本抽取依赖：`all2txt` 为必选依赖，默认安装必须可用
- 可观测性：debug 日志必须包含索引性能计数，便于用户判断瓶颈与吞吐
- 仅提供 CLI 接口，无 GUI 或 Web 界面
