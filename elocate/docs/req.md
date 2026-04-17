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
| `embedding_model` | `str` | `"all-MiniLM-L6-v2"` | sentence-transformers 模型名 |

## 非功能需求

- 语言：Python 3.11+，使用 uv 管理依赖
- 向量数据库：LanceDB（本地，无需服务端）
- 嵌入模型：sentence-transformers（本地推理，无需网络）
- 仅提供 CLI 接口，无 GUI 或 Web 界面
