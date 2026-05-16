# eval — 模型评估目录

本目录包含针对 little-agent 所配置后端和模型的评估工具。与 `tests/`（单元测试）和 `ci_tests/`（集成测试）不同，这里关注**模型行为质量**，而非框架功能正确性。

评估工具不依赖 pytest，使用 `make` 或直接 `uv run python eval/<file>.py` 运行。

---

## 快速开始（对新模型重跑）

所有评估脚本通过 `--config` 指向 little-agent 配置文件，配置文件决定使用哪个后端和模型。对新模型重跑只需两步：

```bash
# 1. 准备配置文件（指向目标模型）
cp ~/.config/little_agent/config.yaml ~/.config/little_agent/config_newmodel.yaml
# 编辑 config_newmodel.yaml，修改 backends.primary.model 和 api_key_env

# 2. 用 ARGS 或直接指定 --config 跑任意评估
make compress    CONFIG=~/.config/little_agent/config_newmodel.yaml
make basic-gradient && make basic-conflict  CONFIG=~/.config/little_agent/config_newmodel.yaml
make fence       CONFIG=~/.config/little_agent/config_newmodel.yaml
```

报告文件按模型命名：`report_<供应商_模型>.md`，参照 `report_step3.6.md` 的章节结构填写。

---

## 评估体系

### 第一组：模型能力类（compress / tools）

测试模型在特定任务上的质量表现。

| 文件 | 类型 | 说明 |
|------|------|------|
| `2.0-compress.md` | 文档 | 压缩场景设计 |
| `2.0-compress_gen_baseline.py` | 脚本 | 生成基线对话 |
| `2.1-compress_quality.py` | 脚本 | 压缩质量评估（9指令×2数据集×3重复=54次） |
| `compress_baseline.jsonl` | 产物 | 不入 git |
| `compress_results.csv` | 产物 | 不入 git |
| `3.0-tools.md` | 文档 | 工具选择场景设计 |
| `3.1-tools_swap.py` | 脚本 | 名称/描述/历史信号优先级（8组×6次=48次） |
| `3.2-tools_select.py` | 脚本 | 功能重叠偏好 + 随机名实验 |
| `tools_verify_history.py` | 脚本 | 历史偏向修改实验（单次手动） |

```bash
make compress-baseline         # 生成压缩基线
make compress-quality             # 运行压缩评估
uv run python eval/3.1-tools_swap.py --config $(CONFIG)
uv run python eval/3.2-tools_select.py --config $(CONFIG)
```

### 第二组：指令遵从与工具调用（prompt_*）

测试模型对指令的遵从稳定性和工具调用行为。设计文档见 `5.0-system.md`。

| 脚本 | 章节 | 内容 | 调用量 |
|------|------|------|--------|
| `1.3-basic_gradient.py` / `1.4-basic_conflict.py` | 一 | 指令遵从性（清晰度梯度 + system/user 冲突） | ~50 |
| `3.3-tools_capability.py` | 二 | 渐进禁令穷举工具路径（9题×8轮） | ~50 |
| `5.1-system_compliance.py` | 三 | 系统提示词遵从（S0–S7，8个场景） | ~200 |
| `5.2-system_fence.py` | 四 | 系统提示词围栏/数据注入（S8，5次×2组） | ~300 |

```bash
make basic-gradient && make basic-conflict       # 第一章
make tools-capability       # 第二章（渐进禁令，exit=1 表示遇到未知方法）
make system-compliance       # 第三章（S0–S7，可 ARGS="--scenario S4"）
make fence            # 第四章 S8（S8-A 基准 + S8-B 注入）
make fence-baseline   # 仅 S8-A
make fence-inject     # 仅 S8-B
```

`3.3-tools_capability.py` 遇到未知工具路径会打印 `UNKNOWN METHOD` 并以 exit code 1 退出——需将新关键词加入 `KEYWORD_BANS` 后重跑。

### 第三组：压力测试（pressure_*）

测试模型在长对话/持续工具调用下的稳定性边界。设计文档见 `4.0-pressure.md`。

| 脚本 | 内容 | 失控判定 |
|------|------|---------|
| `4.1-pressure_turns.py` | 轮次 vs token 量：Mode A（短问题）/ Mode B（长内容） | elapsed≥300s 或 output_tokens≥20000 |
| `4.3-pressure_tools.py` | 工具调用压力：T-small（~10tok）/ T-large（~80tok） | 同上 |

```bash
make pressure-turns                   # Mode A（默认）
make pressure-turns ARGS="--mode B"   # Mode B
make pressure-tools                   # T-small + T-large
make pressure                         # 全部
```

---

## 通用参数

所有脚本均支持：

| 参数 | 说明 | 默认 |
|------|------|------|
| `--config PATH` | little-agent 配置文件路径 | `~/.config/little_agent/config.yaml` |
| `--loglevel LEVEL` | 日志级别（建议运行时用 INFO，调试用 DEBUG） | WARNING |

部分脚本额外支持：`--scenario`、`--variant`、`--mode`、`--runs`、`--max-turns`、`--problems` 等，见各脚本 `--help`。

---

## 报告模板

新模型报告参照 `report_step3.6.md` 章节结构：

```
# 内部测试报告：<供应商> <模型>

**供应商**：...
**模型**：...
**测试日期**：...
**测试框架**：little-agent eval

## 测试体系概览
（同结构表格）

## 一、压缩能力测试
...（各章节）...

## 九、综合结论
```

每章节写：测试方法（1-2句）、原始数据表格、主要发现。结论章节汇总信号优先级、约束稳定性、攻击向量排名。
