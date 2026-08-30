# Session Logbook

把 Codex 与 OpenCode session 的 compact 摘要保存为按 session 分文件的 Markdown 工作日志。默认输出到 `~/.agents/logbooks/`，可用 `AGENT_LOGBOOK_DIR` 改写。

## 文件

- `codex/codex_logbook.py`：Codex `PostCompact`/`SessionEnd` command hook。
- `codex/hooks.json`：Codex 用户级 hook 配置模板。
- `codex/config.example.json`：Codex 日志摘要后端配置示例。
- `opencode/logbook.ts`：OpenCode 全局插件。
- `tests/test_codex_logbook.py`：不调用模型的提取、增量 marker 测试。

没有提取本机的 provider、MCP、鉴权配置、Codex hook 信任 hash、session transcript 或既有日志。这些内容要么无关，要么不可移植或可能包含敏感信息。

## 行为

| Agent | compact | session 结束 |
| --- | --- | --- |
| Codex | `PostCompact` 后增量读取 transcript，调用配置的摘要后端并追加日志 | `SessionEnd` 的 3 秒窗口内启动后台 worker，再执行同一增量流程 |
| OpenCode | compact 前补充摘要格式要求；`session.compacted` 后保存 OpenCode 自己生成的 summary | session 被 archive 时主动 summarize，随后通过 `session.compacted` 保存 |

OpenCode 的普通 CLI/服务退出没有对应的结束事件。当前插件只把 archive 视为 session 结束；`dispose` 只等待已经开始的写入，不会为尚未 compact/archive 的 session 新建摘要。

日志名分别为 `codex_<session-id>.md` 和 `opencode_<session-id>.md`。文件包含 session 元数据、每次摘要时间和幂等 marker；日志文件权限为 `0600`，目录和锁目录为 `0700`。同 session 的写入通过锁串行化。

## 安装

先检查目标位置已有配置。安装目标遇到内容不同的脚本、hook 或插件会拒绝覆盖；它也不会覆盖已有的 `~/.agents/logbook-hooks/config.json`：

```sh
make check
make install
```

也可以只安装一端：

```sh
make install-codex
make install-opencode
```

如果 `~/.codex/hooks.json` 已有其他 hook，应手工合并 `codex/hooks.json`；安装目标会提示并停止。Codex 会对 hook 定义按内容 hash 记录信任；安装或修改后，在 CLI 中用 `/hooks` 检查来源并确认信任。不要复制另一台机器 `config.toml` 里的 `hooks.state`/`trusted_hash`。事件、超时和信任流程见 [Codex Hooks 官方说明](https://developers.openai.com/codex/hooks/)。

Codex adapter 需要带 `fcntl` 的 Python 3，因此主要面向 Unix。`SessionEnd` 优先用 `systemd-run --user` 启动后台摘要；没有可用的 user systemd 时会退回到独立子进程。

OpenCode 会自动发现全局配置目录下 `plugins/*.ts`，无需把插件写入 `opencode.json`。插件依赖 OpenCode/Bun runtime，以及当前 SDK 中的 `experimental.session.compacting`、`session.updated`、`session.compacted`、`client.session.messages` 和 `client.session.summarize` 接口；升级 OpenCode 后应重新执行一次实际 compact/archive 验证兼容性。

## Codex 摘要后端

默认示例使用 OpenCode：

```json
{
  "backend": "opencode",
  "opencode": {
    "model": "opencode-go/deepseek-v4-flash",
    "agent": "logbook"
  }
}
```

需要安装可执行的 `opencode`，且该 model 在目标机器可用。临时 `logbook` agent 禁用工具并拒绝权限，摘要完成后删除临时 OpenCode session。

也可改用 Codex 自身作为摘要后端：

```json
{
  "backend": "codex",
  "codex": {
    "model": null
  }
}
```

`model: null` 表示优先沿用当前 session model。脚本用 `codex exec --ephemeral --disable hooks --sandbox read-only` 运行摘要，避免再次触发日志 hook。

配置优先级是环境变量高于 `~/.agents/logbook-hooks/config.json`。支持：

- `AGENT_LOGBOOK_DIR`：日志输出目录。
- `AGENT_LOGBOOK_CONFIG`：配置文件位置。
- `AGENT_LOGBOOK_BACKEND`：`opencode` 或 `codex`。
- `AGENT_LOGBOOK_MODEL`：覆盖摘要 model。
- `AGENT_LOGBOOK_OPENCODE_AGENT`、`AGENT_LOGBOOK_OPENCODE_BIN`、`AGENT_LOGBOOK_CODEX_BIN`：覆盖 agent 或命令位置。

## 输出与失败处理

Codex 摘要固定包含：本阶段目标、已完成、重要文件、测试与验证、重要决策、未完成与后续。它只提取用户/助手消息和工具调用，不提取工具输出；测试结果只有在对话文字中出现时才会进入日志。每项和总活动有长度限制，过长内容会截断。

摘要后端失败时，Codex hook 仍会写入最多 12,000 字符的可检索活动摘录。无论摘要成功与否，日志都可能包含源码片段、路径、命令参数和用户输入等敏感内容；不要把 `~/.agents/logbooks/` 自动提交到公共仓库。

排查时先看：

```sh
rg -n '自动摘要失败|logbook-summarizer' ~/.agents/logbooks
journalctl --user -u 'codex-logbook-*'
```

Codex transcript JSONL 是实现所依赖的内部格式，不是稳定的 hook API。Codex 或 OpenCode 升级后，至少分别触发一次 compact，并对 OpenCode 再执行一次 archive，确认新增页面、marker 和 frontmatter 正常。
