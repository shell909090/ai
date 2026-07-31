# 模型选择

数据表分为几个区域

1. 闭源最强大模型
2. 开源最强大模型
3. 公司可离线部署
4. 个人低成本独立部署。

- 公司离线部署的线，划定在了256G统一内存上。Q4量化的话，参数量大约在300-400B以下。同时，激活参数量最好在20B以下。
- 个人低成本部署的线，划定在了32G统一内存上。Q4量化的话，参数量大约在40-50B以下。

# 固有参数

| 模型 | 开放性 | 参数量 | 激活参数量 | 上下文 | 发布时间 | 输入价格 | 输出价格 | 缓存读取 | 缓存写入 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 闭 | -- | -- | 1M | 2026-07-09 | $5 | $30 | $0.5 | $6.25 |
| GPT-5.6 Terra | 闭 | -- | -- | 1M | 2026-07-09 | $1 | $6 | $0.1 | $1.25 |
| Claude Fable 5 | 闭 | -- | -- | 1M | 2026-06-09 | $10 | $50 | $1 | $12.5 |
| Claude Opus 5 | 闭 | -- | -- | 1M | 2026-07-24 | $5 | $25 | $0.5 | $6.25 |
| Claude Sonnet 5 | 闭 | -- | -- | 1M | 2026-06-30 | $2 | $10 | $0.2 | $2.5 |
| Gemini 3.1 Pro | 闭 | -- | -- | 1M | 2026-02-19 | $2 | $12 | $0.2 | $0.375 |
| Gemini 3.6 Flash | 闭 | -- | -- | 1M | 2026-07-21 | $1.5 | $7.5 | $0.15 | $0.0833 |
| Grok 4.5 | 闭 | -- | -- | 500k | 2026-07-08 | $2 | $6 | $0.3 | -- |
| Kimi K3 | 开 | 2.8T | 104B | 1M | 2026-07-17 | $3 | $15 | $0.3 | -- |
| GLM-5.2 | 开 | 744B | 40B | 1M | 2026-06-16 | $1.19 | $3.74 | $0.221 | -- |
| DeepSeek V4 Pro | 开 | 1.6T | 49B | 1M | 2026-04-22 | $0.435 | $0.87 | $0.003625 | -- |
| DeepSeek V4 Flash | 开 | 284B | 13B | 1M | 2026-04-22 | $0.14 | $0.28 | $0.028 | -- |
| MiniMax M3 | 开 | 428B | 23B | 1M | 2026-06-02 | $0.3 | $1.2 | $0.06 | -- |
| MiniMax M2.7 | 开 | 230B | 10B | 205k | 2026-03-18 | $0.25 | $1 | $0.05 | -- |
| Qwen3.6-35B-A3B | 开 | 36B | 3B | 262k | 2026-04-15 | $0.14 | $1 | -- | -- |
| Qwen3.6-27B | 开 | 27B | 27B | 262k | 2026-04-21 | $0.3 | $2 | $0.15 | -- |

# 指标选择

指标选择的要求是有公信力（不好刷题），有区分度（没有饱和），数据齐全（模型都有）。下面是几个参考指标。

- **SWE-bench Pro**：用仓库级软件工程任务衡量模型理解跨文件代码、定位问题并完成真实修改的能力。
- **SciCode**：用多个科学领域的高难编程问题衡量代码生成和算法实现能力，补足 SWE-bench Pro 偏仓库维护的视角。
- **HLE**：用 2500 道专家审核的跨学科前沿问题衡量知识与高难推理的综合能力，且当前分数尚未饱和。
- **Terminal-Bench 2.1**：用 89 项真实终端任务衡量 agent 的命令执行、环境操作、错误恢复和长流程完成能力。
- **τ³-Banking**：用银行业务中的非结构化知识库和多步工具调用，衡量 agent 检索规则、遵守约束并正确改变外部状态的能力。
- **GDPval-AA v2**：用 44 种职业、9 个行业的真实工作交付物衡量模型完成经济价值任务的能力。它是 **AA 指数的组成评测之一**，单列是为了观察职业任务表现，不应当作与 AA 指数完全独立的能力维度。
- **AA 指数**：用独立统一执行的多项评测生成综合分，作为快速比较模型整体水平的摘要而不是新的独立能力维度。

# Benchmark 数据

| 模型 | SWE-bench Pro | SciCode | HLE | Terminal-Bench 2.1 | τ³-Banking | GDPval-AA v2 (Elo) | AA指数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 64.6% | 56.1% | 47.2% | 88.0% | 33.0% | 1736 | 59 |
| GPT-5.6 Terra | 63.4% | 53.9% | 41.8% | 88.0% | 31.8% | 1583 | 55 |
| Claude Fable 5 (with fallback) | 80.0% | 60.2% | 53.3% | 84.6% | 26.8% | 1746 | 60 |
| Claude Opus 5 | -- | 55.7% | 52.6% | 89.1% | 30.3% | 1861 | 61 |
| Claude Sonnet 5 | 63.2% | 53.6% | 39.6% | 80.5% | 28.2% | 1601 | 53 |
| Gemini 3.1 Pro | 54.2% | 58.9% | 44.7% | 73.8% | 16.5% | 965 | 47 |
| Gemini 3.6 Flash | -- | 52.7% | 38.3% | 77.5% | 24.5% | 1423 | 50 |
| Grok 4.5 | -- | 54.1% | 40.3% | 81.6% | 32.6% | 1528 | 54 |
| Kimi K3 | -- | 58.7% | 44.3% | 85.0% | 33.4% | 1687 | 57 |
| GLM-5.2 | 62.1% | 50.5% | 40.1% | 77.9% | 26.8% | 1510 | 51 |
| DeepSeek V4 Pro | 55.4% | 50.0% | 35.9% | 64.0% | 25.8% | 1306 | 44 |
| DeepSeek V4 Flash | 52.6% | 44.9% | 32.1% | 61.8% | 22.9% | 1189 | 40 |
| MiniMax M3 | 59.0% | 45.4% | 37.1% | 65.2% | 13.0% | 1390 | 44 |
| MiniMax M2.7 | 56.2% | 47.0% | 28.1% | 55.4% | 8.9% | 1158 | 38 |
| Qwen3.6-35B-A3B | 49.5% | 35.8% | 20.2% | 44.9% | 8.7% | 1052 | 32 |
| Qwen3.6-27B | 53.5% | 39.8% | 21.6% | 60.7% | 15.3% | 1138 | 37 |

# 注释

- 数据核对日期：2026-07-31。
- 模型规格和发布时间优先采用厂商文档、官方发布页与官方模型卡：[OpenAI](https://developers.openai.com/api/docs/changelog)、[Anthropic](https://www.anthropic.com/news)、[Google](https://ai.google.dev/gemini-api/docs/changelog)、[xAI](https://docs.x.ai/developers/models)、[Kimi K3](https://www.kimi.com/blog/kimi-k3)、[GLM-5.2](https://z.ai/blog/glm-5.2)、[DeepSeek V4](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)、[MiniMax M3](https://huggingface.co/MiniMaxAI/MiniMax-M3)、[MiniMax M2.7](https://huggingface.co/MiniMaxAI/MiniMax-M2.7) 和 [Qwen3.6](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)。发布时间按模型首次公开发布或上线日期统计；参数量使用模型架构口径，而不是量化权重文件的元素数或磁盘大小。模型商品名、厂商标称值和包含 embedding、MTP 等模块的精确权重计数可能略有不同。
- 价格来自 [OpenRouter Models API](https://openrouter.ai/api/v1/models) 的普通实时模型，统一换算为美元/百万 tokens；不采用 batch、fast 或 pro 变体。缓存价格直接对应 API 的 `input_cache_read` 和 `input_cache_write` 字段，`--` 表示 OpenRouter 未提供该计费项；模型特有的 1 小时缓存写入、缓存存储、图片、音频、搜索等费用未列入表格。
- SWE-bench Pro 采用各模型发布材料中的成绩；不同厂商使用的 agent scaffold、上下文和任务修订可能不同，只适合粗略参考。没有公开同口径成绩的模型标记为 `--`。其余分数来自 Artificial Analysis 的独立评测：[SciCode](https://artificialanalysis.ai/evaluations/scicode)、[HLE](https://artificialanalysis.ai/evaluations/humanitys-last-exam)、[Terminal-Bench 2.1](https://artificialanalysis.ai/evaluations/terminalbench-v2-1)、[τ³-Banking](https://artificialanalysis.ai/evaluations/tau3-banking)、[GDPval-AA v2](https://artificialanalysis.ai/evaluations/gdpval-aa) 和 [AA 指数](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)。GDPval-AA v2 是 AA 指数的组成评测之一，单列后与 AA 指数存在信息重叠；百分比分数保留一位小数，GDPval-AA v2 的 Elo 和 AA 指数取整。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Fable 5 的 AA 评测启用了 Opus 4.8 fallback，因此单独标注。
