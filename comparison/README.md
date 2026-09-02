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

| 模型 | 发布时间 | 开放性 | 参数量 | 激活参数量 | 多模态 | 上下文 | 下载 |
|---|---:|---:|---:|---:|---:|---:|---|
| [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) | 2026-07-09 | 闭 | -- | -- | V | 1M | -- |
| [GPT-5.6 Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra) | 2026-07-09 | 闭 | -- | -- | V | 1M | -- |
| [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) | 2026-07-09 | 闭 | -- | -- | V | 1M | -- |
| [Claude Fable 5.1](https://www.anthropic.com/claude-fable-and-mythos-5-1) | 2026-09-01 | 闭 | -- | -- | V | 1M | -- |
| [Claude Opus 5](https://www.anthropic.com/news/claude-opus-5) | 2026-07-24 | 闭 | -- | -- | V | 1M | -- |
| [Claude Sonnet 5](https://www.anthropic.com/news/claude-sonnet-5) | 2026-06-30 | 闭 | -- | -- | V | 1M | -- |
| [Gemini 3.1 Pro Preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) | 2026-02-19 | 闭 | -- | -- | V/A | 1M | -- |
| [Gemini 3.7 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash) | 2026-08-13 | 闭 | -- | -- | V/A | 1M | -- |
| [Grok 4.6](https://docs.x.ai/developers/models/grok-4.6) | 2026-08-12 | 闭 | -- | -- | V | 500k | -- |
| [Muse Glimmer 30B](https://huggingface.co/meta-models/Muse-Glimmer-30B) | 2026-08-10 | 开 | 29.6B | 29.6B | V | 131k | [权重](https://huggingface.co/meta-models/Muse-Glimmer-30B) · [GGUF（官方）](https://huggingface.co/meta-models/Muse-Glimmer-30B-GGUF) |
| [Kimi K3](https://www.kimi.com/blog/kimi-k3) | 2026-07-16 | 开 | 2.8T | 104B | V | 1M | [权重](https://huggingface.co/moonshotai/Kimi-K3) · [GGUF](https://huggingface.co/unsloth/Kimi-K3-GGUF) |
| [GLM-5.3](https://z.ai/blog/glm-5.3) | 2026-08-14 | 开 | 744B | 40B | -- | 1M | [权重](https://huggingface.co/zai-org/GLM-5.3) · [GGUF](https://huggingface.co/unsloth/GLM-5.3-GGUF) |
| [GLM-5.3-Flash](https://z.ai/blog/glm-5.3-flash) | 2026-08-26 | 开 | 320B | 18B | V | 1M | [权重](https://huggingface.co/zai-org/GLM-5.3-Flash) · [GGUF](https://huggingface.co/unsloth/GLM-5.3-Flash-GGUF) |
| [DeepSeek V4 Pro 0813](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813) | 2026-08-13 | 开 | 1.6T | 49B | -- | 1M | [权重](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813) · [GGUF](https://huggingface.co/unsloth/DeepSeek-V4-Pro-0813-GGUF) |
| [DeepSeek V4 Flash 0731](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) | 2026-07-31 | 开 | 284B | 13B | -- | 1M | [权重](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731) · [GGUF](https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF) |
| [MiniMax M3](https://huggingface.co/MiniMaxAI/MiniMax-M3) | 2026-06-02 | 开 | 428B | 23B | V | 1M | [权重](https://huggingface.co/MiniMaxAI/MiniMax-M3) · [GGUF](https://huggingface.co/unsloth/MiniMax-M3-GGUF) |
| [Qwen3.8-2.4T-A95B](https://qwen.ai/blog?id=qwen3.8) | 2026-08-12 | 开 | 2.4T | 95B | -- | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-2.4T-A95B-GGUF) |
| [Qwen3.8-Flash-Next](https://qwen.ai/blog?id=qwen3.8-flash-next) | 2026-08-26 | 开 | 180B | 6B | V | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF) |
| [Qwen3.8-27B](https://qwen.ai/blog?id=qwen3.8) | 2026-08-14 | 开 | 27B | 27B | V | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-27B) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) |

- 多模态列仅记录非文本输入：`V` 表示视觉（图像或视频），`A` 表示音频，`--` 表示仅支持文本输入。
- 我们目前无法百分百确认 Qwen3.8-Flash 的底层就是 Qwen3.8-Flash-Next，但是目前有很强证据证明二者是一回事。因此表格内采用 Qwen3.8-Flash-Next 的名字和固有参数、Qwen3.8-Flash 的价格，以及 Qwen3.8-Flash-Next 的 Benchmark 分数，并将其列为开源模型。

# API 价格

| 模型 | 输入价格 | 输出价格 | 缓存读取 | 缓存写入 | 性价比 |
|---|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | $4 | $20 | $0.4 | $5 | 99.1% |
| GPT-5.6 Terra | $2 | $12 | $0.2 | $2.5 | 99.2% |
| GPT-5.6 Luna | $0.2 | $1.2 | $0.02 | $0.25 | 102.3% |
| Claude Fable 5.1 | $10 | $50 | $0.25 | $12.5 | 99.6% |
| Claude Opus 5 | $5 | $25 | $0.5 | $6.25 | 99.8% |
| Claude Sonnet 5 | $2 | $10 | $0.2 | $2.5 | 95.8% |
| Gemini 3.1 Pro Preview | $2 | $12 | $0.2 | $0.375 | 86.4% |
| Gemini 3.7 Flash | $0.375 | $1.875 | $0.0375 | $0.020833 | 109.8% |
| Grok 4.6 | $2 | $6 | $0.5 | -- | 105.5% |
| Muse Glimmer 30B | $0.3 | $1.2 | $0.04 | -- | 68.8% |
| Kimi K3 | $3 | $15 | $0.3 | -- | 105.2% |
| GLM-5.3 | $1.4 | $4.4 | $0.26 | -- | 108.8% |
| GLM-5.3-Flash | $0.15 | $0.5 | $0.03 | -- | 112.9% |
| DeepSeek V4 Pro 0813 | $1.32 / $0.66 | $3.96 / $1.98 | $0.044 / $0.022 | -- | 102.2% |
| DeepSeek V4 Flash 0731 | $0.44 / $0.22 | $1.32 / $0.66 | $0.014 / $0.007 | -- | 103.1% |
| MiniMax M3 | $0.3 | $1.2 | $0.06 | -- | 87.8% |
| Qwen3.8-2.4T-A95B | $2 | $6 | $0.25 | -- | 104.2% |
| Qwen3.8-Flash-Next | $0.15 | $0.47 | $0.016 | $0.2 | 110.7% |
| Qwen3.8-27B | $0.425 | $2.55 | $0.085 | $0.53125 | 98.9% |

- GLM-5.3-Flash 是新训练的原生多模态基座，采用稀疏注意力与线性注意力混合架构；表中采用官方原价。
- 性价比首先按“输入价格 + 10 × 缓存读取价格 + 缓存写入价格”计算综合价格，再以当前表中 19 个模型拟合 `预期 AA 指数 = 35.2329 + 9.1387 × ln(4.8562 + 综合价格)`（R² = 0.443），最后计算“实际 AA 指数 / 预期 AA 指数 × 100%”。高于 100% 表示相对划算，低于 100% 表示相对不划算。DeepSeek 分别计算峰价和谷价的综合价格后取算术平均；未提供缓存写入价格的 `--` 在本项计算中按 0 计。该拟合是当前模型集合内的相对比较，模型或价格变化后需要整体重算。

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
| GPT-5.6 Sol | 64.6% | 56.1% | 88.0% | 44.3% | 49.5% | 32.3% | 61 |
| GPT-5.6 Terra | 63.4% | 53.9% | 88.0% | 40.2% | 42.9% | 30.0% | 57 |
| GPT-5.6 Luna | 62.7% | 52.5% | 80.9% | 31.1% | 39.5% | 20.6% | 52 |
| Claude Fable 5.1 (with fallback) | -- | 62.0% | 91.4% | 47.2% | 59.1% | 29.7% | 66 |
| Claude Opus 5 | -- | 55.7% | 89.1% | 42.1% | 54.9% | 29.1% | 63 |
| Claude Sonnet 5 | 63.2% | 53.6% | 80.5% | 37.3% | 41.3% | 16.9% | 55 |
| Gemini 3.1 Pro Preview | 54.2% | 58.9% | 73.8% | 21.4% | 47.0% | 17.7% | 48 |
| Gemini 3.7 Flash | -- | 56.8% | 85.8% | 32.8% | 47.9% | 14.3% | 56 |
| Grok 4.6 | -- | 53.6% | 88.4% | 50.7% | 42.9% | 17.1% | 61 |
| Muse Glimmer 30B | 51.2% | 43.6% | 51.7% | 23.5% | 22.0% | 2.6% | 35 |
| Kimi K3 | -- | 58.7% | 85.0% | 46.0% | 46.9% | 23.4% | 60 |
| GLM-5.3 | -- | 56.5% | 83.9% | 50.3% | 42.3% | 19.1% | 60 |
| GLM-5.3-Flash | -- | 46.1% | 84.3% | 47.2% | 39.9% | 15.4% | 57 |
| DeepSeek V4 Pro 0813 | -- | 49.2% | 78.7% | 39.6% | 41.0% | 18.0% | 53 |
| DeepSeek V4 Flash 0731 | -- | 49.9% | 78.7% | 39.4% | 38.6% | 16.6% | 52 |
| MiniMax M3 | 59.0% | 45.4% | 65.2% | 15.3% | 39.0% | 3.7% | 45 |
| Qwen3.8-2.4T-A95B | 67.7% | 51.6% | 82.0% | 49.1% | 42.4% | 20.0% | 58 |
| Qwen3.8-Flash-Next | 62.5% | 46.9% | 86.1% | 45.4% | 38.0% | 11.1% | 56 |
| Qwen3.8-27B | 61.7% | 44.7% | 79.8% | 48.0% | 33.9% | 5.4% | 52 |

# 注释

- 数据核对日期：2026-09-02；AA 指数版本：v4.1.1。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Fable 5.1 的 AA 评测启用了默认 fallback，因此单独标注。
