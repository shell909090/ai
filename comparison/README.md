# 模型选择

数据收纳几类模型：

1. 闭源最强大模型。两个：Claude Opus 5.5和Claude Sonnet 5.5。
2. 开源最强大模型。三个：MiMo v2.6 Pro、GLM-5.3和Kimi K3。
3. 个人低成本独立部署。一个：Qwen3.8-27B。
4. 公司可离线部署。两个：GLM-5.3-Flash和Qwen3.8-Flash-Next。
5. 可执行任务廉价模型。一个：DeepSeek V4.1 Flash。

其中：

- 个人低成本部署的线，划定在了32G统一内存上。Q4量化的话，参数量大约在40-50B以下。
- 公司离线部署的线，划定在了256G统一内存上。Q4量化的话，参数量大约在300-400B以下。同时，激活参数量最好在20B以下。
- 可执行任务廉价模型，划定在 API 综合价格低于 $1/百万 tokens、具备 agent 或工具执行能力、且未归入上述任何类别的模型。

# 固有参数

| 模型 | 发布时间 | 开放性 | 参数量 | 激活参数量 | 多模态 | 上下文 | 下载 |
|---|---:|---:|---:|---:|---:|---:|---|
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | 2026-09-03 | 闭 | -- | -- | V | 1M | -- |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | 2026-09-29 | 闭 | -- | -- | V | 1.05M | -- |
| [Claude Opus 5.5](https://www.anthropic.com/claude-opus-5-5) | 2026-09-22 | 闭 | -- | -- | V | 1M | -- |
| [Claude Sonnet 5.5](https://www.anthropic.com/claude-sonnet-5-5) | 2026-09-28 | 闭 | -- | -- | V | 1M | -- |
| [Gemini 4 Argon](https://blog.google/intl/zh-tw/products/explore-get-answers/gemini-4-argon/) | 2026-09-30 | 闭 | -- | -- | V/A | 1M | -- |
| [Grok 4.7](https://x.ai/news/grok-4-7) | 2026-09-21 | 闭 | -- | -- | V | 500k | -- |
| [Meta Muse Spark 1.3](https://research.meta.ai/blog/introducing-muse-spark-1-3) | 2026-09-02 | 闭 | -- | -- | V | 1M | -- |
| [MiMo v2.6 Pro](https://mimo.mi.com/docs/zh-CN/news/latest/v2-6) | 2026-09-21 | 开 | 1.02T | 42B | V/A | 1M | [权重](https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Pro-RL) |
| [Kimi K3](https://www.kimi.com/blog/kimi-k3) | 2026-07-16 | 开 | 2.8T | 104B | V | 1M | [权重](https://huggingface.co/moonshotai/Kimi-K3) · [GGUF](https://huggingface.co/unsloth/Kimi-K3-GGUF) |
| [GLM-5.3](https://z.ai/blog/glm-5.3) | 2026-08-14 | 开 | 744B | 40B | -- | 1M | [权重](https://huggingface.co/zai-org/GLM-5.3) · [GGUF](https://huggingface.co/unsloth/GLM-5.3-GGUF) |
| [GLM-5.3-Flash](https://z.ai/blog/glm-5.3-flash) | 2026-08-26 | 开 | 320B | 18B | V | 1M | [权重](https://huggingface.co/zai-org/GLM-5.3-Flash) · [GGUF](https://huggingface.co/unsloth/GLM-5.3-Flash-GGUF) |
| [DeepSeek V4.1 Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) | 2026-09-10 | 开 | 552B/763B | 8B/16B | V | 1M | [权重](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) |
| [Qwen3.8-Flash-Next](https://qwen.ai/blog?id=qwen3.8-flash-next) | 2026-08-26 | 开 | 180B | 6B | V | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF) |
| [Qwen3.8-27B](https://qwen.ai/blog?id=qwen3.8) | 2026-08-14 | 开 | 27B | 27B | V | 262k | [权重](https://huggingface.co/Qwen/Qwen3.8-27B) · [GGUF](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF) |

- 多模态列仅记录非文本输入：`V` 表示视觉（图像或视频），`A` 表示音频，`--` 表示仅支持文本输入。
- 我们目前无法百分百确认 Qwen3.8-Flash 的底层就是 Qwen3.8-Flash-Next，但是目前有很强证据证明二者是一回事。因此表格内采用 Qwen3.8-Flash-Next 的名字和固有参数、Qwen3.8-Flash 的价格，以及 Qwen3.8-Flash-Next 的 Benchmark 分数，并将其列为开源模型。
- DeepSeek V4.1 Flash 的 552B 为 backbone 参数量，激活参数为 prefill 8B / decode 16B（因果编码器-解码器架构）；另含 196B Engram 条件记忆与视觉编码器，权重合计 763B。

# API 价格

| 模型 | 输入价格 | 输出价格 | 缓存读取 | 缓存写入 | 综合价格 | 性价比 |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra | \$10 | \$50 | \$1 | \$12.5 | \$47.5 | 79.5% |
| GPT-6.1 Sol | \$2 | \$10 | \$0.1 | \$2.5 | \$7.5 | 89.9% |
| Claude Opus 5.5 | \$4 | \$20 | \$0.2 | \$5 | \$15 | **94.4%** |
| Claude Sonnet 5.5 | \$2 | \$10 | \$0.2 | \$2.5 | \$9.5 | **95.0%** |
| Gemini 4 Argon | \$2 | \$10 | \$0.1 | -- | \$5 | **94.1%** |
| Grok 4.7 | \$2 | \$6 | \$0.5 | -- | \$12.6 | 77.0% |
| Meta Muse Spark 1.3 | \$1.25 | \$4.25 | \$0.15 | -- | \$4.675 | **86.4%** |
| MiMo v2.6 Pro | \$0.435 | \$0.87 | \$0.0036 | -- | \$0.594 | **100.0%** |
| Kimi K3 | \$3 | \$15 | \$0.3 | -- | \$10.5 | 73.4% |
| GLM-5.3 | \$1.4 | \$4.4 | \$0.26 | -- | \$7.04 | 77.8% |
| GLM-5.3-Flash | \$0.15 | \$0.5 | \$0.03 | -- | \$0.8 | 87.7% |
| DeepSeek V4.1 Flash | \$0.30 / \$0.15 | \$1.20 / \$0.60 | \$0.006 / \$0.003 | -- | \$0.405 | **88.7%** |
| Qwen3.8-Flash-Next | \$0.15 | \$0.47 | \$0.016 | \$0.2 | \$0.717 | 84.4% |
| Qwen3.8-27B | \$0.425 | \$2.55 | \$0.085 | \$0.53125 | \$2.91125 | 62.9% |

- 不参考套餐/批量折扣/限时优惠价格，表中采用官方原价。
- 综合价格按“0.1 × 输出价格 + 输入价格 + 20 × 缓存读取价格 + 缓存写入价格”计算。未提供缓存写入价格的 `--` 在本项计算中按 0 计。它表示实际载荷每处理 1M 输入 tokens 对应的真实成本：与这 1M 输入对应的输出、缓存读取和缓存写入量，分别按实际比例乘以各自单价后，与输入成本相加。
- 有峰谷价格的，综合价格按峰谷价的平均数计算。
- Gemini 4 Argon 采用 Google 公告中的优惠期价格；公告未提供缓存写入价格，因此按 `--` 计 0。优惠期结束后，输入/输出价格恢复为 \$4/\$20，未用于本表。
- Grok 4.7 的 prompt ≥200K 长文档位（输入/输出/缓存读取翻倍）与 2 倍价格的 fast 变体均未计入，综合价格按 <200K 标准档计算。
- 性价比从当前表中选出“相同或更低综合价格下不存在更高 AA 指数模型”的 6 个 Pareto 前沿模型，拟合得到 `预期 AA 指数 = 45.3058 + 4.2423 × ln(综合价格)`（R² = 0.867），最后计算“实际 AA 指数 / 预期 AA 指数 × 92.8004%”。该系数按当前模型集合中的最高原始性价比 92.8004% 归一化，使最高分恰为 100%；其余分数均落在 0–100% 区间。该拟合是当前模型集合内的相对比较，模型或价格变化后需要重新筛选 Pareto 前沿并整体重算。
- Pareto模型的性价比已经被加粗。
- 价格-AA 关系图（横轴为对数综合价格，纵轴为 AA 指数，红点为 Pareto 前沿模型，红色虚线为 Pareto 拟合线）：

  ![价格-AA关系图](price_vs_aa.png)

# 指标选择

指标选择的要求是有公信力（不好刷题），有区分度（没有饱和），数据齐全（模型都有）。Scicode 与其他评测中个别缺失的成绩标记为 `--`。下面是几个参考指标。

- **SciCode**：用多个科学领域的高难编程问题衡量代码生成和算法实现能力。
- **Terminal-Bench 4.0**：用 66 项更难的真实终端任务衡量 agent 的命令执行、环境操作、错误恢复和长流程完成能力，调整了计算资源和时间限制，并改进指令、运行环境与验证器。
- **AutomationBench**：用 657 个模拟 SaaS 工作流衡量 agent 的跨应用工具调用、业务规则执行、状态修改和安全约束遵守能力；当前表采用 AA 的 AutomationBench-AA 分数。
- **HLE**：用 2500 道专家审核的跨学科前沿问题衡量知识与高难推理的综合能力，且当前分数尚未饱和。
- **CritPt**：用物理学研究者设计的 70 道未公开前沿问题衡量研究级科学推理能力，采用数值数组、符号表达式和 Python 函数等抗猜测答案格式。
- **AA 指数**：用独立统一执行的多项评测生成综合分，作为快速比较模型整体水平的摘要而不是新的独立能力维度。
- 五个基础指标按能力分组为：SciCode、Terminal-Bench 4.0（代码）；AutomationBench（Agent 执行）；HLE、CritPt（推理）。AA 指数单独作为综合指标保留。

# Benchmark 数据

| 模型 | SciCode | Terminal-Bench 4.0 | AutomationBench | HLE | CritPt | AA指数 |
|---|---:|---:|---:|---:|---:|---:|
| GPT-6 Astra | 56.5% | 59.1% | 68.5% | 54.7% | 31.7% | 52.7% |
| GPT-6.1 Sol | 54.2% | 56.1% | 64.9% | 52.9% | 31.7% | 52.0% |
| Claude Opus 5.5 (with fallback) | 67.0% | 59.6% | 69.5% | 61.0% | 32.0% | 57.6% |
| Claude Sonnet 5.5 (with fallback) | 61.0% | 63.6% | 71.3% | 64.5% | 31.4% | 56.0% |
| Gemini 4 Argon | 61.8% | 57.1% | 77.5% | 57.1% | 27.1% | 52.7% |
| Grok 4.7 | 57.4% | 24.7% | 63.5% | 43.1% | 17.7% | 46.4% |
| Meta Muse Spark 1.3 | 58.8% | 33.3% | 57.9% | 48.7% | 24.9% | 48.1% |
| MiMo v2.6 Pro | 61.0% | 34.8% | 58.6% | 49.0% | 27.0% | 46.3% |
| Kimi K3 | 59.5% | 12.6% | 58.3% | 46.9% | 23.4% | 43.6% |
| GLM-5.3 | 59.0% | 41.9% | 62.2% | 42.3% | 19.1% | 44.8% |
| GLM-5.3-Flash | 51.6% | 32.8% | 60.4% | 39.9% | 15.0% | 41.8% |
| DeepSeek V4.1 Flash | 51.9% | 26.8% | 68.9% | 39.3% | 14.3% | 39.5% |
| Qwen3.8-Flash-Next | 50.6% | 25.3% | 55.9% | 38.0% | 11.1% | 39.8% |
| Qwen3.8-27B | 46.6% | 5.6% | 48.2% | 33.9% | 5.4% | 33.7% |

- 数据核对日期：2026-10-01；AA 指数版本：v4.3.2。表中 AA 指数保留一位小数。
- 数据优先采用AA独立评测，其次采用官方模型卡/报告。两者均不存在时，参考采信第三方评价或官方估计值。
- 闭源推理模型使用表中成绩对应的高推理档位；Claude Opus 5.5 的 AA 评测启用了默认 fallback，因此单独标注。
- GPT-6 Astra、GPT-6.1 Sol、Claude Opus/Sonnet 5.5 和 Muse Spark 1.3 使用 Max 档，Gemini 4 Argon 和 Grok 4.7 使用 High 档，其余使用各自默认推理档位。

# 用户反馈收集

- 闭源里面，Opus 5.5是偏好评的。
- Opus 5.5反馈逆天，号称“全球最好用模型”，“老实干活儿的老二回来了，还当了老大”。
- Astra的评价极度两极分化。
- Grok被吐槽“只有NSFW是刚需”。而且这批人还在流向Qwen3.8-27B。
- 开源里面，MiMo v2.6 Pro中评偏差。评价是“性价比高跑分漂亮，然而不能干活儿”。
- GLM-5.3/GLM-5.3-Flash好评。前者便宜，后者可本地部署。缺点是不知为何，坚信自己是claude。
- K3评价两极分化。主要优点是细节封神，主要缺点是贵且慢。
- DeepSeek V4.1 Flash也是两极分化。速度封神，编码拉胯。而且啰里八嗦的。
- Qwen3.8-Flash-Next意外的强。但只有一个供应商。
- Qwen3.8-27B，低成本本地执行的唯一选择，也无需在意评价了。

# 点评

- 最强阵营里，Astra->Sonnet/Opus依次向高智能高性价比进发。
  - OpenAI这边是全面拉胯，
- 第二集群里，K3->GLM-5.3->Spark1.3依次进发。当然，Spark1.3闭源。
  - 同行太给力，Spark 1.3性价比都不高了。
- 第三集群主打高性价比。里面MiMo v2.6 Pro一枝独秀，甚至压住了不少第二集群选手。当然，评价就是另一回事儿了。
  - 去掉一个最高分，巅峰二位是GLM-5.3-Flash和DeepSeek V4.1 Flash。
- Qwen3.8-27B自己一桌吃饭。
