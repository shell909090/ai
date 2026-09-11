# 模型选择

数据收纳几类模型：

1. 闭源最强大模型
2. 开源最强大模型
3. 公司可离线部署
4. 个人低成本独立部署
5. 闭源可执行任务廉价模型

其中：

- 公司离线部署的线，划定在了256G统一内存上。Q4量化的话，参数量大约在300-400B以下。同时，激活参数量最好在20B以下。基本只有GLM-5.3-Flash、Qwen3.8-Flash-Next和DeepSeek V4 Flash 0731。
- 个人低成本部署的线，划定在了32G统一内存上。Q4量化的话，参数量大约在40-50B以下。基本只有Qwen3.8-27B。
- 闭源可执行任务廉价模型，划定在了 API 输入价格低于 $0.5/百万 tokens、具备 agent 或工具执行能力，并且未归入公司或个人离线部署类别的闭源模型。当前共有2个：GPT-5.6 Luna和Gemini 3.8 Flash。上面两类列出的模型，显然也能满足廉价可执行任务要求。只不过不重复计算，因此不列入。

# 固有参数

| 模型 | 发布时间 | 开放性 | 参数量 | 激活参数量 | 多模态 | 上下文 | 下载 |
|---|---:|---:|---:|---:|---:|---:|---|
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | 2026-09-03 | 闭 | -- | -- | V | 1M | -- |
| [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) | 2026-07-09 | 闭 | -- | -- | V | 1M | -- |
| [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) | 2026-07-09 | 闭 | -- | -- | V | 1M | -- |
| [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) | 2026-07-09 | 闭 | -- | -- | V | 1M | -- |
| [Claude Fable 5.1](https://www.anthropic.com/claude-fable-and-mythos-5-1) | 2026-09-01 | 闭 | -- | -- | V | 1M | -- |
| [Claude Opus 5](https://www.anthropic.com/news/claude-opus-5) | 2026-07-24 | 闭 | -- | -- | V | 1M | -- |
| [Claude Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5) | 2026-06-30 | 闭 | -- | -- | V | 1M | -- |
| [Gemini 3.1 Pro Preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) | 2026-02-19 | 闭 | -- | -- | V/A | 1M | -- |
| [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) | 2026-09-02 | 闭 | -- | -- | V/A | 1M | -- |
| [Grok 4.6](https://docs.x.ai/developers/models/grok-4.6) | 2026-08-12 | 闭 | -- | -- | V | 500k | -- |
| [Meta Muse Spark 1.3](https://research.meta.ai/blog/introducing-muse-spark-1-3) | 2026-09-02 | 闭 | -- | -- | V | 1M | -- |
| [Kimi K3](https://www.kimi.com/blog/kimi-k3) | 2026-07-16 | 开 | 2.8T | 104B | V | 1M | [权重](https://huggingface.co/moonshotai/Kimi-K3) · [GGUF](https://huggingface.co/unsloth/Kimi-K3-GGUF) |
| [GLM-5.3](https://z.ai/blog/glm-5.3) | 2026-08-14 | 开 | 744B | 40B | -- | 1M | [权重](https://huggingface.co/zai-org/GLM-5.3) · [GGUF](https://huggingface.co/unsloth/GLM-5.3-GGUF) |
| [GLM-5.3-Flash](https://z.ai/blog/glm-5.3-flash) | 2026-08-26 | 开 | 320B | 18B | V | 1M | [权重](https://huggingface.co/zai-org/GLM-5.3-Flash) · [GGUF](https://huggingface.co/unsloth/GLM-5.3-Flash-GGUF) |
| [DeepSeek V4 Pro 0813](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813) | 2026-08-13 | 开 | 1.6T | 49B | -- | 1M | [权重](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813) · [GGUF](https://huggingface.co/unsloth/DeepSeek-V4-Pro-0813-GGUF) |
| [DeepSeek V4 Flash 0731](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) | 2026-07-31 | 开 | 284B | 13B | -- | 1M | [权重](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) · [GGUF](https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF) |
| [DeepSeek V4.1 Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) | 2026-09-10 | 开 | 552B/763B | 8B/16B | V | 1M | [权重](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) |
| [MiniMax M3](https://huggingface.co/MiniMaxAI/MiniMax-M3) | 2026-06-02 | 开 | 428B | 23B | V | 1M | [权重](https://huggingface.co/MiniMaxAI/MiniMax-M3) · [GGUF](https://huggingface.co/unsloth/MiniMax-M3-GGUF) |
| [Qwen3.8-2.4T-A95B](https://qwen.ai/blog?id=qwen3.8) | 2026-08-12 | 开 | 2.4T | 95B | -- | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-2.4T-A95B-GGUF) |
| [Qwen3.8-Flash-Next](https://qwen.ai/blog?id=qwen3.8-flash-next) | 2026-08-26 | 开 | 180B | 6B | V | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF) |
| [Qwen3.8-27B](https://qwen.ai/blog?id=qwen3.8) | 2026-08-14 | 开 | 27B | 27B | V | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-27B) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) |

- 多模态列仅记录非文本输入：`V` 表示视觉（图像或视频），`A` 表示音频，`--` 表示仅支持文本输入。
- Claude Mythos 5.1 与 Claude Fable 5.1 使用同一底层模型，仅安全策略和访问范围不同；Mythos 5.1 仅通过受信任访问计划提供，因此不在表中重复计入。
- 我们目前无法百分百确认 Qwen3.8-Flash 的底层就是 Qwen3.8-Flash-Next，但是目前有很强证据证明二者是一回事。因此表格内采用 Qwen3.8-Flash-Next 的名字和固有参数、Qwen3.8-Flash 的价格，以及 Qwen3.8-Flash-Next 的 Benchmark 分数，并将其列为开源模型。
- 同样，我们无法百分百的确定 Qwen3.8-Max 的底层就是 Qwen3.8-2.4T-A95B，但是同样有很强的证据表明两者是一回事。
- DeepSeek V4.1 Flash 的 552B 为 backbone 参数量，激活参数为 prefill 8B / decode 16B（因果编码器-解码器架构）；另含 196B Engram 条件记忆与视觉编码器，权重合计 763B。

# API 价格

| 模型 | 输入价格 | 输出价格 | 缓存读取 | 缓存写入 | 综合价格 | 性价比 |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra | \$10 | \$50 | \$1 | \$12.5 | \$47.5 | **98.0%** |
| GPT-5.6 Sol | \$4 | \$20 | \$0.4 | \$5 | \$19 | 81.2% |
| GPT-5.6 Terra | \$2 | \$12 | \$0.2 | \$2.5 | \$9.7 | 68.1% |
| GPT-5.6 Luna | \$0.2 | \$1.2 | \$0.02 | \$0.25 | \$0.97 | 75.2% |
| Claude Fable 5.1 | \$10 | \$50 | \$0.25 | \$12.5 | \$32.5 | **99.8%** |
| Claude Opus 5 | \$5 | \$25 | \$0.5 | \$6.25 | \$23.75 | **91.8%** |
| Claude Sonnet 5 | \$2 | \$10 | \$0.2 | \$2.5 | \$9.5 | 76.2% |
| Gemini 3.1 Pro Preview | \$2 | \$12 | \$0.2 | \$0.375 | \$7.575 | 60.9% |
| Gemini 3.8 Flash | \$0.375 | \$1.875 | \$0.0375 | \$0.020833 | \$1.33333 | 91.7% |
| Grok 4.6 | \$2 | \$6 | \$0.5 | -- | \$12.6 | 86.9% |
| Meta Muse Spark 1.3 | \$1.25 | \$4.25 | \$0.15 | -- | \$4.675 | **100.0%** |
| Kimi K3 | \$3 | \$15 | \$0.3 | -- | \$10.5 | 87.8% |
| GLM-5.3 | \$1.4 | \$4.4 | \$0.26 | -- | \$7.04 | 91.7% |
| GLM-5.3-Flash | \$0.15 | \$0.5 | \$0.03 | -- | \$0.8 | **96.9%** |
| DeepSeek V4 Pro 0813 | \$1.32 / \$0.66 | \$3.96 / \$1.98 | \$0.044 / \$0.022 | -- | \$1.947 | 78.8% |
| DeepSeek V4 Flash 0731 | \$0.30 / \$0.15 | \$1.20 / \$0.60 | \$0.006 / \$0.003 | -- | \$0.405 | 84.2% |
| DeepSeek V4.1 Flash | \$0.30 / \$0.15 | \$1.20 / \$0.60 | \$0.006 / \$0.003 | -- | \$0.405 | **96.3%** |
| MiniMax M3 | \$0.3 | \$1.2 | \$0.06 | -- | \$1.62 | 66.4% |
| Qwen3.8-2.4T-A95B | \$2 | \$6 | \$0.25 | -- | \$7.6 | 81.2% |
| Qwen3.8-Flash-Next | \$0.15 | \$0.47 | \$0.016 | \$0.2 | \$0.717 | **97.5%** |
| Qwen3.8-27B | \$0.425 | \$2.55 | \$0.085 | \$0.53125 | \$2.91125 | 72.7% |

- 不参考套餐/批量折扣/限时优惠价格，表中采用官方原价。
- 综合价格按“0.1 × 输出价格 + 输入价格 + 20 × 缓存读取价格 + 缓存写入价格”计算。未提供缓存写入价格的 `--` 在本项计算中按 0 计。它表示实际载荷每处理 1M 输入 tokens 对应的真实成本：与这 1M 输入对应的输出、缓存读取和缓存写入量，分别按实际比例乘以各自单价后，与输入成本相加。
- 有峰谷价格的，综合价格按峰谷价的平均数计算。
- 性价比从当前表中选出“相同或更低综合价格下不存在更高 AA 指数模型”的 7 个 Pareto 前沿模型，拟合 `预期 AA 指数 = 42.6991 + 2.5591 × ln(综合价格)`（R² = 0.930），最后计算“实际 AA 指数 / 预期 AA 指数 × 102.9031%”。该系数按当前模型集合中的最高原始性价比归一化，使最高分恰为 100%；其余分数均落在 0–100% 区间。该拟合是当前模型集合内的相对比较，模型或价格变化后需要重新筛选 Pareto 前沿并整体重算。
- Pareto模型的性价比已经被加粗。

# 指标选择

指标选择的要求是有公信力（不好刷题），有区分度（没有饱和），数据齐全（模型都有）。SWE-bench Pro 因该领域缺少更好的替代数据而保留，缺失成绩标记为 `--`。下面是几个参考指标。

- **SWE-bench Pro**：用仓库级软件工程任务衡量模型理解跨文件代码、定位问题并完成真实修改的能力。
- **SciCode**：用多个科学领域的高难编程问题衡量代码生成和算法实现能力，补足 SWE-bench Pro 偏仓库维护的视角。
- **Terminal-Bench 2.1**：用 89 项真实终端任务衡量 agent 的命令执行、环境操作、错误恢复和长流程完成能力。
- **τ³-Banking**：用银行业务中的非结构化知识库和多步工具调用，衡量 agent 检索规则、遵守约束并正确改变外部状态的能力。
- **HLE**：用 2500 道专家审核的跨学科前沿问题衡量知识与高难推理的综合能力，且当前分数尚未饱和。
- **CritPt**：用物理学研究者设计的 70 道未公开前沿问题衡量研究级科学推理能力，采用数值数组、符号表达式和 Python 函数等抗猜测答案格式。
- **AA 指数**：用独立统一执行的多项评测生成综合分，作为快速比较模型整体水平的摘要而不是新的独立能力维度。

# Benchmark 数据

| 模型 | SWE-bench Pro | SciCode | Terminal-Bench 2.1 | τ³-Banking | HLE | CritPt | AA指数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra | -- | 54.1% | 88.4% | 41.4% | 54.7% | 31.7% | 53 |
| GPT-5.6 Sol | 64.6% | 56.1% | 88.0% | 44.3% | 49.5% | 32.3% | 42 |
| GPT-5.6 Terra | 63.4% | 53.9% | 88.0% | 40.2% | 42.9% | 30.0% | 34 |
| GPT-5.6 Luna | 62.7% | 52.5% | 80.9% | 31.1% | 39.5% | 20.6% | 33 |
| Claude Fable 5.1 (with fallback) | -- | 62.0% | 91.4% | 47.2% | 59.1% | 29.7% | 53 |
| Claude Opus 5 | -- | 55.7% | 89.1% | 42.1% | 54.9% | 29.1% | 48 |
| Claude Sonnet 5 | 63.2% | 53.6% | 80.5% | 37.3% | 41.3% | 16.9% | 38 |
| Gemini 3.1 Pro Preview | 54.2% | 58.9% | 73.8% | 21.4% | 47.0% | 17.7% | 30 |
| Gemini 3.8 Flash | -- | 53.6% | 87.6% | 44.9% | 47.8% | 18.3% | 41 |
| Grok 4.6 | -- | 53.6% | 88.4% | 50.7% | 42.9% | 17.1% | 44 |
| Meta Muse Spark 1.3 | -- | 58.6% | 85.4% | 47.2% | 47.5% | 26.0% | 48 |
| Kimi K3 | -- | 58.7% | 85.0% | 46.0% | 46.9% | 23.4% | 44 |
| GLM-5.3 | -- | 56.5% | 83.9% | 50.3% | 42.3% | 19.1% | 45 |
| GLM-5.3-Flash | -- | 46.1% | 84.3% | 47.2% | 39.9% | 15.4% | 42 |
| DeepSeek V4 Pro 0813 | -- | 49.2% | 78.7% | 39.6% | 41.0% | 18.0% | 36 |
| DeepSeek V4 Flash 0731 | -- | 49.9% | 78.7% | 39.4% | 38.6% | 16.6% | 35 |
| DeepSeek V4.1 Flash | -- | -- | 90.6% | -- | 36.8% | -- | 40 |
| MiniMax M3 | 59.0% | 45.4% | 65.2% | 15.3% | 39.0% | 3.7% | 30 |
| Qwen3.8-2.4T-A95B | 67.7% | 51.6% | 82.0% | 49.1% | 42.4% | 20.0% | 40 |
| Qwen3.8-Flash-Next | 62.5% | 46.9% | 86.1% | 45.4% | 38.0% | 11.1% | 42 |
| Qwen3.8-27B | 61.7% | 44.7% | 79.8% | 48.0% | 33.9% | 5.4% | 34 |

# 注释

- 数据核对日期：2026-09-11；AA 指数版本：v4.3。AA 指数中 GPT-5.6 Luna 和 Qwen3.8-Flash-Next 的分数为官方 estimated 值。
- DeepSeek 于 2026-09-10 发布 DeepSeek V4.1 Flash 并下调 API 价格；V4 Flash 0731 的 API 已退役并由 V4.1 Flash 承接（请求路由），二者按同一 `deepseek-flash` 档价格计费。自 2026-09-14 12:00（北京时间）起，`deepseek-v4-pro` 的请求也将路由至 V4.1 Flash 并按其价格计费。
- DeepSeek V4.1 Flash 的 Terminal-Bench 2.1 和 HLE 成绩为发布当日官方自报；AA 指数由 [Artificial Analysis](https://artificialanalysis.ai/models/deepseek-v4-1-flash) v4.3 收录。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Fable 5.1 的 AA 评测启用了默认 fallback，因此单独标注。
