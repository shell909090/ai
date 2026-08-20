# 模型选择

数据收纳几类模型：

1. 闭源最强大模型
2. 开源最强大模型
3. 公司可离线部署
4. 个人低成本独立部署

- 公司离线部署的线，划定在了256G统一内存上。Q4量化的话，参数量大约在300-400B以下。同时，激活参数量最好在20B以下。基本只有MiniMax M2.7和DeepSeek V4 Flash 0731。
- 个人低成本部署的线，划定在了32G统一内存上。Q4量化的话，参数量大约在40-50B以下。基本只有Qwen3.8-27B和Qwen3.6-35B-A3B。

# 固有参数

| 模型 | 发布时间 | 开放性 | 参数量 | 激活参数量 | 多模态 | 上下文 | 输入价格 | 输出价格 | 缓存读取 | 缓存写入 | 模型链接 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 2026-07-09 | 闭 | -- | -- | V | 1M | $5 | $30 | $0.5 | $6.25 | [官方](https://developers.openai.com/api/docs/models/gpt-5.6-sol) |
| GPT-5.6 Terra | 2026-07-09 | 闭 | -- | -- | V | 1M | $2 | $12 | $0.2 | $2.5 | [官方](https://developers.openai.com/api/docs/models/gpt-5.6-terra) |
| GPT-5.6 Luna | 2026-07-09 | 闭 | -- | -- | V | 1M | $0.2 | $1.2 | $0.02 | $0.25 | [官方](https://developers.openai.com/api/docs/models/gpt-5.6-luna) |
| Claude Fable 5 | 2026-06-09 | 闭 | -- | -- | V | 1M | $10 | $50 | $1 | $12.5 | [官方](https://www.anthropic.com/news/redeploying-fable-5) |
| Claude Opus 5 | 2026-07-24 | 闭 | -- | -- | V | 1M | $5 | $25 | $0.5 | $6.25 | [官方](https://www.anthropic.com/news/claude-opus-5) |
| Claude Sonnet 5 | 2026-06-30 | 闭 | -- | -- | V | 1M | $2 | $10 | $0.2 | $2.5 | [官方](https://www.anthropic.com/news/claude-sonnet-5) |
| Gemini 3.1 Pro Preview | 2026-02-19 | 闭 | -- | -- | V/A | 1M | $2 | $12 | $0.2 | $0.375 | [官方](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) |
| Gemini 3.7 Flash | 2026-08-13 | 闭 | -- | -- | V/A | 1M | $0.375 | $1.875 | $0.0375 | $0.020833 | [官方](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash) |
| Grok 4.6 | 2026-08-12 | 闭 | -- | -- | V | 500k | $2 | $6 | $0.5 | -- | [官方](https://docs.x.ai/developers/models/grok-4.6) |
| Muse Spark 1.2 | 2026-08-05 | 闭 | -- | -- | V/A | 1M | $1.25 | $4.25 | $0.15 | -- | [官方](https://ai.developer.meta.com/docs/models/muse-spark-1.2) |
| Kimi K3 | 2026-07-16 | 开 | 2.8T | 104B | V | 1M | $3 | $15 | $0.3 | -- | [官方](https://www.kimi.com/blog/kimi-k3) |
| GLM-5.3 | 2026-08-14 | 开 | 744B | 40B | -- | 1M | $1.4 | $4.4 | $0.26 | -- | [官方](https://z.ai/blog/glm-5.3) |
| DeepSeek V4 Pro 0813 | 2026-08-13 | 开 | 1.6T | 49B | -- | 1M | $1.32 / $0.66 | $3.96 / $1.98 | $0.044 / $0.022 | -- | [模型卡](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813) |
| DeepSeek V4 Flash 0731 | 2026-07-31 | 开 | 284B | 13B | -- | 1M | $0.44 / $0.22 | $1.32 / $0.66 | $0.014 / $0.007 | -- | [模型卡](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) |
| MiniMax M3 | 2026-06-02 | 开 | 428B | 23B | V | 1M | $0.3 | $1.2 | $0.06 | -- | [模型卡](https://huggingface.co/MiniMaxAI/MiniMax-M3) |
| MiniMax M2.7 | 2026-03-18 | 开 | 230B | 10B | -- | 205k | $0.25 | $1 | $0.05 | -- | [模型卡](https://huggingface.co/MiniMaxAI/MiniMax-M2.7) |
| Qwen3.8-2.4T-A95B | 2026-08-12 | 开 | 2.4T | 95B | -- | 262k | $2 | $6 | $0.25 | -- | [模型卡](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) |
| Qwen3.8-27B | 2026-08-14 | 开 | 27B | 27B | V | 262k | $0.45 | $3.2 | $0.05 | -- | [模型卡](https://huggingface.co/Qwen/Qwen3.8-27B) |
| Qwen3.6-35B-A3B | 2026-04-15 | 开 | 36B | 3B | V | 262k | $0.14 | $1 | -- | -- | [模型卡](https://huggingface.co/Qwen/Qwen3.6-35B-A3B) |

- 多模态列仅记录非文本输入：`V` 表示视觉（图像或视频），`A` 表示音频，`--` 表示仅支持文本输入。

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
| GPT-5.6 Sol | 64.6% | 56.1% | 49.5% | 88.0% | 44.3% | 1723 | 61 |
| GPT-5.6 Terra | 63.4% | 53.9% | 42.9% | 88.0% | 40.2% | 1576 | 57 |
| GPT-5.6 Luna | 62.7% | 52.5% | 39.5% | 80.9% | 31.1% | 1578 | 52 |
| Claude Fable 5 (with fallback) | 80.0% | 60.2% | 55.5% | 84.6% | 38.1% | 1738 | 62 |
| Claude Opus 5 | -- | 55.7% | 54.9% | 89.1% | 42.1% | 1845 | 63 |
| Claude Sonnet 5 | 63.2% | 53.6% | 41.3% | 80.5% | 37.3% | 1595 | 55 |
| Gemini 3.1 Pro Preview | 54.2% | 58.9% | 47.0% | 73.8% | 21.4% | 965 | 48 |
| Gemini 3.7 Flash | -- | 56.8% | 47.9% | 85.8% | 32.8% | 1532 | 56 |
| Grok 4.6 | -- | 53.6% | 42.9% | 88.4% | 50.7% | 1747 | 61 |
| Muse Spark 1.2 | -- | 56.4% | 45.5% | 80.1% | 34.8% | 1628 | 57 |
| Kimi K3 | -- | 58.7% | 46.9% | 85.0% | 46.0% | 1681 | 60 |
| GLM-5.3 | -- | 56.5% | 42.3% | 83.9% | 50.3% | 1769 | 60 |
| DeepSeek V4 Pro 0813 | -- | 49.2% | 41.0% | 78.7% | 39.6% | 1590 | 53 |
| DeepSeek V4 Flash 0731 | -- | 49.9% | 38.6% | 78.7% | 39.4% | 1559 | 52 |
| MiniMax M3 | 59.0% | 45.4% | 39.0% | 65.2% | 15.3% | 1387 | 45 |
| MiniMax M2.7 | 56.2% | 47.0% | 29.6% | 55.4% | 9.9% | 1160 | 39 |
| Qwen3.8-2.4T-A95B | 67.7% | 51.6% | 42.4% | 82.0% | 49.1% | 1720 | 58 |
| Qwen3.8-27B | 61.7% | 44.7% | 33.9% | 79.8% | 48.0% | 1546 | 52 |
| Qwen3.6-35B-A3B | 49.5% | 35.8% | 22.2% | 44.9% | 9.3% | 1055 | 32 |

# 注释

- 数据核对日期：2026-08-20。
- 模型规格和发布时间优先采用“固有参数”表中链接的厂商文档、官方发布页与官方模型卡。发布时间按模型首次公开发布或上线日期统计；参数量使用模型架构口径，而不是量化权重文件的元素数或磁盘大小。模型商品名、厂商标称值和包含 embedding、MTP 等模块的精确权重计数可能略有不同。
- DeepSeek V4 直接以版本号区分；Flash 0731 和 Pro 0813 均为正式版开放权重模型。
- GLM-5.3 沿用 GLM-5.2 的基座结构。官方计划在发布两周后开放权重；截至核对日权重尚未发布，开放性按官方承诺记为“开”。
- Qwen3.8-2.4T-A95B 一行的参数量、开放性、多模态和原生上下文采用开放权重模型口径；API 价格和 Benchmark 对应基于该权重、增加视觉输入和默认 1M 上下文等服务能力的 Qwen3.8-Max 托管版本。
- OpenAI 模型采用 [OpenAI 官方标准实时 API 价格](https://developers.openai.com/api/docs/pricing)；自 2026-07-30 起 Terra 降价 20%，Luna 降价 80%，变更见 [OpenAI Changelog](https://developers.openai.com/api/docs/changelog)。DeepSeek Flash 0731 和 Pro 0813 采用 [DeepSeek 官方 API 价格](https://api-docs.deepseek.com/quick_start/pricing)，表内依次列出“峰 / 谷”价格：峰时为 UTC 01:00–04:00 和 06:00–10:00，其余时段为谷时；新价格自 2026-08-16 16:00 UTC 起生效。GLM-5.3 采用 [Z.AI 官方 API 价格](https://docs.z.ai/guides/overview/pricing)。其余模型价格来自 [OpenRouter Models API](https://openrouter.ai/api/v1/models) 的普通实时模型，统一换算为美元/百万 tokens；不采用 batch、fast 或 pro 变体。缓存价格对应缓存读取和写入计费，`--` 表示数据源未提供该计费项；模型特有的 1 小时缓存写入、缓存存储、图片、音频、搜索等费用未列入表格。
- SWE-bench Pro 采用各模型发布材料中的成绩；不同厂商使用的 agent scaffold、上下文和任务修订可能不同，只适合粗略参考。没有公开同口径成绩的模型标记为 `--`。其余分数来自 Artificial Analysis 的独立评测：[SciCode](https://artificialanalysis.ai/evaluations/scicode)、[HLE](https://artificialanalysis.ai/evaluations/humanitys-last-exam)、[Terminal-Bench 2.1](https://artificialanalysis.ai/evaluations/terminalbench-v2-1)、[τ³-Banking](https://artificialanalysis.ai/evaluations/tau3-banking)、[GDPval-AA v2](https://artificialanalysis.ai/evaluations/gdpval-aa) 和 [AA 指数](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)；AA 指数整列按 2026-08-20 的 v4.1.1 版本统一核对。DeepSeek 的版本数据还可在 [V4 Pro 0813](https://artificialanalysis.ai/models/deepseek-v4-pro) 和 [V4 Flash 0731](https://artificialanalysis.ai/models/deepseek-v4-flash) 页面中核对。GDPval-AA v2 是 AA 指数的组成评测之一，单列后与 AA 指数存在信息重叠；百分比分数保留一位小数，GDPval-AA v2 的 Elo 和 AA 指数取整。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Fable 5 的 AA 评测启用了 Opus 4.8 fallback，因此单独标注。
