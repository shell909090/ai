# 模型选择

数据收纳几类模型：

1. 闭源最强大模型
2. 开源最强大模型
3. 公司可离线部署
4. 个人低成本独立部署
5. 闭源可执行任务廉价模型

- 公司离线部署的线，划定在了256G统一内存上。Q4量化的话，参数量大约在300-400B以下。同时，激活参数量最好在20B以下。基本只有GLM-5.3-Flash、Qwen3.8-Flash-Next和DeepSeek V4 Flash 0731。
- 个人低成本部署的线，划定在了32G统一内存上。Q4量化的话，参数量大约在40-50B以下。基本只有Qwen3.8-27B和Muse Glimmer 30B。
- 闭源可执行任务廉价模型，划定在了 API 输入价格低于 $0.5/百万 tokens、具备 agent 或工具执行能力，并且未归入公司或个人离线部署类别的闭源模型。当前共有2个：GPT-5.6 Luna和Gemini 3.7 Flash。上面两类列出的模型，显然也能满足廉价可执行任务要求。只不过不重复计算，因此不列入。

# 固有参数

| 模型 | 发布时间 | 开放性 | 参数量 | 激活参数量 | 多模态 | 上下文 |
|---|---:|---:|---:|---:|---:|---:|
| [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) | 2026-07-09 | 闭 | -- | -- | V | 1M |
| [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) | 2026-07-09 | 闭 | -- | -- | V | 1M |
| [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) | 2026-07-09 | 闭 | -- | -- | V | 1M |
| [Claude Fable 5](https://www.anthropic.com/news/redeploying-fable-5) | 2026-06-09 | 闭 | -- | -- | V | 1M |
| [Claude Opus 5](https://www.anthropic.com/news/claude-opus-5) | 2026-07-24 | 闭 | -- | -- | V | 1M |
| [Claude Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5) | 2026-06-30 | 闭 | -- | -- | V | 1M |
| [Gemini 3.1 Pro Preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) | 2026-02-19 | 闭 | -- | -- | V/A | 1M |
| [Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash) | 2026-08-13 | 闭 | -- | -- | V/A | 1M |
| [Grok 4.6](https://docs.x.ai/developers/models/grok-4.6) | 2026-08-12 | 闭 | -- | -- | V | 500k |
| [Muse Glimmer 30B](https://huggingface.co/meta-models/Muse-Glimmer-30B) | 2026-08-10 | 开 | 29.6B | 29.6B | V | 131k |
| [Kimi K3](https://www.kimi.com/blog/kimi-k3) | 2026-07-16 | 开 | 2.8T | 104B | V | 1M |
| [GLM-5.3](https://z.ai/blog/glm-5.3) | 2026-08-14 | 开 | 744B | 40B | -- | 1M |
| [GLM-5.3-Flash](https://huggingface.co/zai-org/GLM-5.3-Flash) | 2026-08-26 | 开 | 320B | 18B | V | 1M |
| [DeepSeek V4 Pro 0813](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813) | 2026-08-13 | 开 | 1.6T | 49B | -- | 1M |
| [DeepSeek V4 Flash 0731](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) | 2026-07-31 | 开 | 284B | 13B | -- | 1M |
| [MiniMax M3](https://huggingface.co/MiniMaxAI/MiniMax-M3) | 2026-06-02 | 开 | 428B | 23B | V | 1M |
| [Qwen3.8-2.4T-A95B](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) | 2026-08-12 | 开 | 2.4T | 95B | -- | 262k |
| [Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) | 2026-08-26 | 开 | 180B | 6B | V | 262k |
| [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) | 2026-08-14 | 开 | 27B | 27B | V | 262k |

- 多模态列仅记录非文本输入：`V` 表示视觉（图像或视频），`A` 表示音频，`--` 表示仅支持文本输入。
- 我们目前无法百分百确认 Qwen3.8-Flash 的底层就是 Qwen3.8-Flash-Next，但是目前有很强证据证明二者是一回事。因此表格内采用 Qwen3.8-Flash-Next 的名字和固有参数、Qwen3.8-Flash 的价格，以及 Qwen3.8-Flash-Next 的 Benchmark 分数，并将其列为开源模型。

# API 价格

| 模型 | 输入价格 | 输出价格 | 缓存读取 | 缓存写入 | 性价比 |
|---|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | $4 | $20 | $0.4 | $5 | 101.4% |
| GPT-5.6 Terra | $2 | $12 | $0.2 | $2.5 | 99.8% |
| GPT-5.6 Luna | $0.2 | $1.2 | $0.02 | $0.25 | 101.8% |
| Claude Fable 5 | $10 | $50 | $1 | $12.5 | 95.8% |
| Claude Opus 5 | $5 | $25 | $0.5 | $6.25 | 102.9% |
| Claude Sonnet 5 | $2 | $10 | $0.2 | $2.5 | 96.3% |
| Gemini 3.1 Pro Preview | $2 | $12 | $0.2 | $0.375 | 86.3% |
| Gemini 3.7 Flash | $0.375 | $1.875 | $0.0375 | $0.020833 | 109.2% |
| Grok 4.6 | $2 | $6 | $0.5 | -- | 106.2% |
| Muse Glimmer 30B | $0.3 | $1.2 | $0.04 | -- | 68.4% |
| Kimi K3 | $3 | $15 | $0.3 | -- | 105.6% |
| GLM-5.3 | $1.4 | $4.4 | $0.26 | -- | 108.5% |
| GLM-5.3-Flash | $0.075 | $0.25 | $0.015 | -- | 113.6% |
| DeepSeek V4 Pro 0813 | $1.32 / $0.66 | $3.96 / $1.98 | $0.044 / $0.022 | -- | 101.5% |
| DeepSeek V4 Flash 0731 | $0.44 / $0.22 | $1.32 / $0.66 | $0.014 / $0.007 | -- | 102.7% |
| MiniMax M3 | $0.3 | $1.2 | $0.06 | -- | 87.3% |
| Qwen3.8-2.4T-A95B | $2 | $6 | $0.25 | -- | 104.1% |
| Qwen3.8-Flash-Next | $0.15 | $0.47 | $0.016 | $0.2 | 110.2% |
| Qwen3.8-27B | $0.425 | $2.55 | $0.085 | $0.53125 | 98.3% |

- 性价比首先按“输入价格 + 10 × 缓存读取价格 + 缓存写入价格”计算综合价格，再以当前表中 19 个模型拟合 `预期 AA 指数 = 45.2425 + 5.4821 × ln(2.2439 + 综合价格)`（R² = 0.368），最后计算“实际 AA 指数 / 预期 AA 指数 × 100%”。高于 100% 表示相对划算，低于 100% 表示相对不划算。DeepSeek 分别计算峰价和谷价的综合价格后取算术平均；未提供缓存写入价格的 `--` 在本项计算中按 0 计。该拟合是当前模型集合内的相对比较，模型或价格变化后需要整体重算。

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
| GPT-5.6 Sol | 64.6% | 56.1% | 49.5% | 88.0% | 44.3% | 1711 | 61 |
| GPT-5.6 Terra | 63.4% | 53.9% | 42.9% | 88.0% | 40.2% | 1570 | 57 |
| GPT-5.6 Luna | 62.7% | 52.5% | 39.5% | 80.9% | 31.1% | 1575 | 52 |
| Claude Fable 5 (with fallback) | 80.0% | 60.2% | 55.5% | 84.6% | 38.1% | 1723 | 62 |
| Claude Opus 5 | -- | 55.7% | 54.9% | 89.1% | 42.1% | 1831 | 63 |
| Claude Sonnet 5 | 63.2% | 53.6% | 41.3% | 80.5% | 37.3% | 1587 | 55 |
| Gemini 3.1 Pro Preview | 54.2% | 58.9% | 47.0% | 73.8% | 21.4% | 965 | 48 |
| Gemini 3.7 Flash | -- | 56.8% | 47.9% | 85.8% | 32.8% | 1523 | 56 |
| Grok 4.6 | -- | 53.6% | 42.9% | 88.4% | 50.7% | 1736 | 61 |
| Muse Glimmer 30B | 51.2% | 43.6% | 22.0% | 51.7% | 23.5% | 955 | 35 |
| Kimi K3 | -- | 58.7% | 46.9% | 85.0% | 46.0% | 1675 | 60 |
| GLM-5.3 | -- | 56.5% | 42.3% | 83.9% | 50.3% | 1763 | 60 |
| GLM-5.3-Flash | -- | 46.1% | 39.9% | 84.3% | 47.2% | 1769 | 57 |
| DeepSeek V4 Pro 0813 | -- | 49.2% | 41.0% | 78.7% | 39.6% | 1580 | 53 |
| DeepSeek V4 Flash 0731 | -- | 49.9% | 38.6% | 78.7% | 39.4% | 1553 | 52 |
| MiniMax M3 | 59.0% | 45.4% | 39.0% | 65.2% | 15.3% | 1382 | 45 |
| Qwen3.8-2.4T-A95B | 67.7% | 51.6% | 42.4% | 82.0% | 49.1% | 1717 | 58 |
| Qwen3.8-Flash-Next | 62.5% | 46.9% | 38.0% | 86.1% | 45.4% | 1743 | 56 |
| Qwen3.8-27B | 61.7% | 44.7% | 33.9% | 79.8% | 48.0% | 1539 | 52 |

# 注释

- 数据核对日期：2026-08-29；AA 指数版本：v4.1.1。
- 模型规格和发布时间优先采用“固有参数”表中链接的厂商文档、官方发布页与官方模型卡。发布时间按模型首次公开发布或上线日期统计；参数量使用模型架构口径，而不是量化权重文件的元素数或磁盘大小。模型商品名、厂商标称值和包含 embedding、MTP 等模块的精确权重计数可能略有不同。
- DeepSeek V4 直接以版本号区分；Flash 0731 和 Pro 0813 均为正式版开放权重模型。
- GLM-5.3 沿用 GLM-5.2 的基座结构。官方计划在发布两周后开放权重；截至核对日权重尚未发布，开放性按官方承诺记为“开”。
- GLM-5.3-Flash 是新训练的原生多模态基座，采用稀疏注意力与线性注意力混合架构；表中价格为官方限时五折价，原价为输入 $0.15、输出 $0.5、缓存读取 $0.03。
- Qwen3.8-2.4T-A95B 一行的参数量、开放性、多模态和原生上下文采用开放权重模型口径；API 价格和 Benchmark 对应基于该权重、增加视觉输入和默认 1M 上下文等服务能力的 Qwen3.8-Max 托管版本。
- Qwen3.8-Flash-Next 的 180B 总参数由 125B 语言模型主体、51B n-gram embedding 和 4B MTP 组成，6B 为主体每 token 激活参数量；表中记录其 262k 原生上下文，扩展上下文可达 1M。API 价格采用 [Qwen3.8-Flash 托管服务](https://www.qwencloud.com/models/qwen3.8-flash)的价格。
- Muse Glimmer 30B 是面向个人设备本地 agent 的稠密多模态模型。官方提供约 17GB 的 4-bit 量化版本，并验证其可在 24GB 或 32GB 内存配置中连同视觉编码器、KV cache 和推测解码模型一起运行。
- OpenAI 模型采用 [OpenAI 官方标准实时 API 价格](https://developers.openai.com/api/docs/pricing)；自 2026-07-30 起 Terra 降价 20%、Luna 降价 80%，自 2026-08-21 起 Sol 降价至输入 $4、输出 $20，变更见 [OpenAI Changelog](https://developers.openai.com/api/docs/changelog)。DeepSeek Flash 0731 和 Pro 0813 采用 [DeepSeek 官方 API 价格](https://api-docs.deepseek.com/quick_start/pricing)，表内依次列出“峰 / 谷”价格：峰时为 UTC 01:00–04:00 和 06:00–10:00，其余时段为谷时；新价格自 2026-08-16 16:00 UTC 起生效。GLM-5.3 和 GLM-5.3-Flash 采用 [Z.AI 官方 API 价格](https://docs.z.ai/guides/overview/pricing)。其余模型价格来自 [OpenRouter Models API](https://openrouter.ai/api/v1/models) 的普通实时模型，统一换算为美元/百万 tokens；不采用 batch、fast 或 pro 变体。缓存价格对应缓存读取和写入计费，`--` 表示数据源未提供该计费项；模型特有的 1 小时缓存写入、缓存存储、图片、音频、搜索等费用未列入表格。
- SWE-bench Pro 采用各模型发布材料中的成绩；不同厂商使用的 agent scaffold、上下文和任务修订可能不同，只适合粗略参考。没有公开同口径成绩的模型标记为 `--`。其余分数来自 Artificial Analysis 的独立评测：[SciCode](https://artificialanalysis.ai/evaluations/scicode)、[HLE](https://artificialanalysis.ai/evaluations/humanitys-last-exam)、[Terminal-Bench 2.1](https://artificialanalysis.ai/evaluations/terminalbench-v2-1)、[τ³-Banking](https://artificialanalysis.ai/evaluations/tau3-banking)、[GDPval-AA v2](https://artificialanalysis.ai/evaluations/gdpval-aa) 和 [AA 指数](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)。新增模型还可在 [GLM-5.3-Flash](https://artificialanalysis.ai/models/glm-5-3-flash)、[Qwen3.8-Flash-Next](https://artificialanalysis.ai/models/qwen3-8-flash-next) 和 [Muse Glimmer](https://artificialanalysis.ai/models/muse-glimmer) 页面中核对，DeepSeek 的版本数据还可在 [V4 Pro 0813](https://artificialanalysis.ai/models/deepseek-v4-pro) 和 [V4 Flash 0731](https://artificialanalysis.ai/models/deepseek-v4-flash) 页面中核对。GDPval-AA v2 是 AA 指数的组成评测之一，单列后与 AA 指数存在信息重叠；百分比分数保留一位小数，GDPval-AA v2 的 Elo 和 AA 指数取整。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Fable 5 的 AA 评测启用了 Opus 4.8 fallback，因此单独标注。
