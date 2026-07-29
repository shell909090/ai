# 模型选择

数据表分为几个区域

1. 闭源最强大模型
2. 开源最强大模型
3. 公司可离线部署
4. 个人低成本独立部署。

- 公司离线部署的线，划定在了256G统一内存上。Q4量化的话，参数量大约在300-400B以下。同时，激活参数量最好在20B以下。
- 个人低成本部署的线，划定在了32G统一内存上。Q4量化的话，参数量大约在40-50B以下。

# 指标选择

指标选择的要求是有公信力（不好刷题），有区分度（没有饱和），数据齐全（模型都有）。下面是几个参考指标。

- **SWE-bench Pro**：用仓库级软件工程任务衡量模型理解跨文件代码、定位问题并完成真实修改的能力。
- **SciCode**：用多个科学领域的高难编程问题衡量代码生成和算法实现能力，补足 SWE-bench Pro 偏仓库维护的视角。
- **HLE**：用 2500 道专家审核的跨学科前沿问题衡量知识与高难推理的综合能力，且当前分数尚未饱和。
- **Terminal-Bench 2.1**：用 89 项真实终端任务衡量 agent 的命令执行、环境操作、错误恢复和长流程完成能力。
- **τ³-Banking**：用银行业务中的非结构化知识库和多步工具调用，衡量 agent 检索规则、遵守约束并正确改变外部状态的能力。
- **AA 指数**：用独立统一执行的多项评测生成综合分，作为快速比较模型整体水平的摘要而不是新的独立能力维度。

# 数据

| 模型 | 开放性 | 总参数 | 激活参数 | Context | SWE-bench Pro | SciCode | HLE | Terminal-Bench 2.1 | τ³-Banking | AA指数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-5.6 Sol | 闭 | -- | -- | 1M | 64.6% | 56.1% | 47.2% | 88.0% | 33.0% | 59 |
| GPT-5.6 Terra | 闭 | -- | -- | 1M | 63.4% | 53.9% | 41.8% | 88.0% | 31.8% | 55 |
| Claude Fable 5 (with fallback) | 闭 | -- | -- | 1M | 80.0% | 60.2% | 53.3% | 84.6% | 26.8% | 60 |
| Claude Opus 4.8 | 闭 | -- | -- | 1M | 69.2% | 53.5% | 45.7% | 84.6% | 27.6% | 56 |
| Claude Sonnet 5 | 闭 | -- | -- | 1M | 63.2% | 53.6% | 39.6% | 80.5% | 28.2% | 53 |
| Gemini 3.1 Pro | 闭 | -- | -- | 1M | 54.2% | 58.9% | 44.7% | 73.8% | 16.5% | 47 |
| Gemini 3.5 Flash | 闭 | -- | -- | 1M | 55.1% | 53.1% | 41.0% | 78.7% | 25.4% | 50 |
| Kimi K3 | 开 | 2.8T | 104B | 1M | -- | 58.7% | 44.3% | 85.0% | 33.4% | 57 |
| GLM-5.2 | 开 | 744B | 40B | 1M | 62.1% | 50.5% | 40.1% | 77.9% | 26.8% | 51 |
| DeepSeek V4 Pro | 开 | 1.6T | 49B | 1M | 55.4% | 50.0% | 35.9% | 64.0% | 25.8% | 44 |
| DeepSeek V4 Flash | 开 | 284B | 13B | 1M | 52.6% | 44.9% | 32.1% | 61.8% | 22.9% | 40 |
| MiniMax M3 | 开 | 428B | 23B | 1M | 59.0% | 45.4% | 37.1% | 65.2% | 13.0% | 44 |
| Qwen3.6-35B-A3B | 开 | 36B | 3B | 262k | 49.5% | 35.8% | 20.2% | 44.9% | 8.7% | 32 |
| Qwen3.6-27B | 开 | 27B | 27B | 262k | 53.5% | 39.8% | 21.6% | 60.7% | 15.3% | 37 |

- 数据核对日期：2026-07-29。
- 模型规格优先采用厂商文档与官方模型卡：[OpenAI](https://platform.openai.com/docs/models)、[Anthropic](https://docs.anthropic.com/en/docs/about-claude/models/overview)、[Google](https://ai.google.dev/gemini-api/docs/models)、[Kimi K3](https://huggingface.co/moonshotai/Kimi-K3)、[GLM-5.2](https://huggingface.co/zai-org/GLM-5.2)、[DeepSeek V4](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)、[MiniMax M3](https://huggingface.co/MiniMaxAI/MiniMax-M3) 和 [Qwen3.6](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)。参数量使用模型架构口径，而不是量化权重文件的元素数或磁盘大小；模型商品名、厂商标称值和包含 embedding、MTP 等模块的精确权重计数可能略有不同。
- SWE-bench Pro 采用各模型发布材料中的成绩；不同厂商使用的 agent scaffold、上下文和任务修订可能不同，只适合粗略参考。其余分数来自 Artificial Analysis 的独立评测：[SciCode](https://artificialanalysis.ai/evaluations/scicode)、[HLE](https://artificialanalysis.ai/evaluations/humanitys-last-exam)、[Terminal-Bench 2.1](https://artificialanalysis.ai/evaluations/terminalbench-v2-1)、[τ³-Banking](https://artificialanalysis.ai/evaluations/tau3-banking) 和 [AA 指数](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)。百分比分数保留一位小数，AA 指数取整。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Fable 5 的 AA 评测启用了 Opus 4.8 fallback，因此单独标注。
