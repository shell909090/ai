---
name: oc-task
description: 使用 oc-task 向 OpenCode 2 服务提交前台或后台任务，并配置、检查 systemd 用户定时任务。
---

# oc-task

Python 3 标准库 HTTP 客户端，需要兼容的 OpenCode 2 服务；不启动 OpenCode CLI，不兼容 V1 API。使用 PATH 上已安装的 `oc-task`。完整配置、认证及 JSON 字段见 [README.md](../../README.md)。

## 提交与结果

```sh
oc-task -m provider/model --dir /path/to/workspace '执行指定任务'
oc-task -b -m provider/model --dir /path/to/workspace '执行指定任务'
printf '%s\n' '任务内容' | oc-task --format json --timeout 300 --stdin
```

后一个例子需要预先配置模型。默认服务地址为 `http://127.0.0.1:4096`，默认目录为当前目录，没有内置模型。`--dir` 必须在客户端存在并可由服务端访问。`--name` 设置会话标题前缀；`--agent` 选择服务端已有 agent，不创建 agent。

- 前台等待结果并输出 assistant 文本；成功退出 0，API/模型失败 1，参数错误 2，权限批准或交互表单阻塞 3，超时 124，SIGINT 130，SIGTERM 143。不要自动批准无人值守任务遇到的权限请求。
- 超时、中断及交互阻塞时尝试取消服务端任务；无法确认取消时根据 session ID 核对。取消和清理可能使总耗时超过 `--timeout`。
- `-b` 提交确认后立即退出；退出 0 只表示提交成功。没有独立等待进程或最终结果日志，使用输出的 Web 入口和 session ID 检查最终结果。
- 请求结果不确定时先核对会话，再决定是否重试，避免重复执行。
- `--stdin` 与位置 prompt 互斥。`--format json` 输出单个结果对象，诊断写 stderr；同时检查退出码及 JSON，参数或配置错误可能没有 JSON。
- `--cleanup` 在前台结束后尝试删除本次新建会话，包括失败情况；清理失败使整体返回非零。需要保留排查记录时不使用它。`-b` 不能与 `--timeout` 或 `--cleanup` 同用。

## 配置与认证

配置默认读取 `~/.config/oc-task/config.json`，支持 XDG_CONFIG_HOME 或 OC_TASK_CONFIG。CLI 优先于 OC_TASK_* 环境变量，环境优先于配置；模型另支持 MODEL。字段与环境变量映射见 README。

密码优先读取 OPENCODE_SERVER_PASSWORD，否则在脚本内部加载指定 env 文件，或默认 OpenCode 配置目录的 web.env.gpg，再回退 web.env。它们按受信任 Bash 代码执行，GPG 文件需要 Bash、GnuPG 及可无人值守解密的环境。不要把部署凭证加入项目，不要手工解密并输出凭证。

## systemd 用户定时任务

流程写入任务 Markdown，service 的 prompt 指向它；工作目录和文档路径变动时同时更新 prompt 与 ConditionPathExists。

在 `~/.config/systemd/user/` 建立 service/timer；下例的路径、服务名、模型、时间均需按部署替换，注释独占一行。

```ini
# oc-example.service
[Unit]
Description=Submit a scheduled OpenCode task
Wants=network-online.target opencode.service
After=network-online.target opencode.service
ConditionPathExists=/path/to/task.md

[Service]
Type=oneshot
ExecStart=/path/to/oc-task -b --dir /path/to/workspace -m provider/model "执行 /path/to/task.md 中的流程"
TimeoutStartSec=infinity
```

```ini
# oc-example.timer
[Unit]
Description=Schedule an OpenCode task
[Timer]
OnCalendar=*-*-* 12:30:00
AccuracySec=1min
RandomizedDelaySec=2min
Persistent=false
Unit=oc-example.service
[Install]
WantedBy=timers.target
```

根据部署配置 PATH、认证环境和服务就绪检查；After 只约束启动顺序，不保证 HTTP 已就绪。按用户要求安装定时任务后，运行 `systemctl --user daemon-reload` 和 `systemctl --user enable --now oc-example.timer`，检查 list-timers。修改已启动 timer 后需 restart。手动 start service 会执行实际任务，仅在任务执行已获授权时验证。

Condition 不满足时 service 跳过；查看 status 的 Condition 行。后台模式下 systemd 成功只证明提交成功，需要最终退出码时使用前台模式。重启 OpenCode 服务会中断其正在运行的会话，不能作为无影响的诊断步骤。
