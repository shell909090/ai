# OpenCode Cache Affinity

这是一个 OpenCode 全局插件，用于改善 GPT 模型请求的提示词缓存亲和性，并按 session 持久化 token 用量与缓存命中数据。

插件解决的是 OpenCode 自定义 `ses_...` session ID 与部分 OpenAI 兼容服务缓存路由之间的兼容问题。它不会保证每次请求命中缓存；上游仍可能因为负载、overflow 或缓存节点状态不同而出现缓存深度回退。

> **Provider 前提：必须使用 `@ai-sdk/openai`，不要使用 `@ai-sdk/openai-compatible`。** OpenCode 配置中的准确值是 `"npm": "@ai-sdk/openai"`。本插件的缓存效果是在 OpenAI Responses 路径上验证的。

`@ai-sdk/openai-compatible` 不会把插件设置的 camelCase `promptCacheKey` 转换为 OpenAI wire 字段 `prompt_cache_key`。在 OpenCode 1.18.21 搭配 `@ai-sdk/openai-compatible` 2.0.41 时，它会作为未知的 camelCase body 字段传入兼容接口，并默认走 `/chat/completions`；OpenAI 通常不会把它当作缓存路由键。因此 UUIDv5 缓存 affinity 的核心效果基本不起作用。插件添加的两个 HTTP header 和 SQLite 用量统计仍会工作，但受控实验没有发现两个 header 单独对缓存产生可测影响，不能把它们视为替代方案。

## 工作方式

对 model ID 以 `gpt` 开头的请求（忽略大小写），插件会：

1. 用固定 namespace 和完整 OpenCode session ID 确定性生成 UUIDv5。
2. 在 `chat.params` 中设置 `output.options.promptCacheKey`。使用 `@ai-sdk/openai` 时，AI SDK 会把它序列化为请求 body 的 `prompt_cache_key`。
3. 在 `chat.headers` 中将同一个 UUIDv5 写入 `x-session-affinity` 和 `X-Session-Id`。

独立于缓存键改写，插件还会监听所有已完成的 assistant message，并将用量按 session/provider/model 写入本地 SQLite。因此数据库也可能包含非 GPT 模型；这些记录只表示用量统计，不表示该模型应用了 UUIDv5 affinity。

同一 session 跨 OpenCode 重启仍会得到同一个 UUIDv5，不需要维护随机 UUID 映射表、TTL 或会话删除逻辑。插件不判断 provider，因此可用于不同 provider 下的 GPT 模型；非 GPT 模型完全不修改。

插件只原地添加或覆盖上述缓存字段，不替换 options 或 headers 对象，也不会删除 `x-opencode-session`、`x-opencode-request`、`x-opencode-client` 等业务 headers。

## 安装

OpenCode 会自动加载 `~/.config/opencode/plugins/` 下的 `.ts` 插件，不需要在 `opencode.json` 中注册。

先确认目标 provider 使用正确的 SDK：

```json
{
  "provider": {
    "your-provider": {
      "npm": "@ai-sdk/openai",
      "options": {
        "baseURL": "https://example.com/openai/v1",
        "apiKey": "{env:OPENAI_API_KEY}"
      }
    }
  }
}
```

`your-provider`、`baseURL` 和环境变量名按实际情况替换。Provider ID 可以自定义；插件不判断 provider ID。

在本目录执行：

```sh
mkdir -p ~/.config/opencode/plugins
install -m 0644 openai-cache-affinity.ts ~/.config/opencode/plugins/openai-cache-affinity.ts
```

然后完全退出并重新启动 OpenCode。已经运行的进程不会可靠地热加载插件。

升级插件时重复执行 `install`，再重启 OpenCode。卸载时删除 `~/.config/opencode/plugins/openai-cache-affinity.ts` 并重启；历史 SQLite 数据不会随插件删除。

## 生效条件与预期效果

- 缓存 affinity 生效条件：`input.model.id` 以 `gpt` 开头，不区分大小写；用量统计覆盖所有形成已完成 assistant message 的模型。
- `promptCacheKey` 的 wire 序列化要求 `@ai-sdk/openai`。不要把 `@ai-sdk/openai-compatible` 当作等价替代；后者不会生成正确的 `prompt_cache_key`。
- UUIDv5 是兼容性 workaround。OpenAI 并未规定 `prompt_cache_key` 必须是 UUID，也没有承诺相同 key 固定到同一台缓存机器。
- 实测 UUIDv5 与 UUIDv7 没有可重复的性能差异。选用 UUIDv5 是因为它能从 session ID 稳定派生。
- 连续对话预热后，实测 Terra 的最近四轮 token 缓存率为 82.02%，4/4 请求有非零命中；单次请求仍可能发生缓存深度回退。
- 大量新代码、文件内容、工具结果、subagent 输出、summary 或 compaction 会引入新前缀，实际缓存率低于纯聊天属于正常现象。

## 用量数据库

插件默认写入：

```text
~/.local/share/opencode/cache-usage/usage.sqlite
```

如果设置了 `XDG_DATA_HOME`，路径改为：

```text
$XDG_DATA_HOME/opencode/cache-usage/usage.sqlite
```

数据库目录权限为 `0700`，数据库权限为 `0600`，启用 WAL 和 5 秒 busy timeout。

### `message_usage`

每个完成的 assistant message 一行，以 `message_id` 为主键；重复事件使用 UPSERT，不会重复计数。主要字段：

- `session_id`、`provider_id`、`model_id`
- `input_tokens`：总输入 token
- `uncached_input_tokens`：未缓存输入 token
- `cached_tokens`：cache read token
- `cache_write_tokens`：cache write token
- `output_tokens`：总输出，包含 reasoning
- `reasoning_tokens`：reasoning 输出子集
- `cost`、`finish`、`is_summary`
- `created_at`、`completed_at`、`updated_at`：Unix 毫秒时间戳

### `session_usage`

这是按 `(session_id, provider_id, model_id)` 聚合的视图，额外提供：

- `response_count`
- `cache_hit_responses`
- `cache_hit_rate`：`cached_tokens / input_tokens`，即 token 缓存率
- `cache_hit_response_rate`：存在任意 cache read 的响应占比
- `first_response_at`、`last_response_at`

判断成本效果时优先看 `cache_hit_rate`。`cache_hit_response_rate=100%` 只代表每次至少命中了一小段前缀，不代表缓存了大部分输入。

## 查看统计

需要安装 `sqlite3` 命令行工具。

查看最近的 session 汇总：

```sh
sqlite3 -header -column ~/.local/share/opencode/cache-usage/usage.sqlite "
SELECT
  session_id,
  provider_id,
  model_id,
  response_count,
  input_tokens,
  uncached_input_tokens,
  cached_tokens,
  output_tokens,
  printf('%.2f%%', 100.0 * cache_hit_rate) AS token_cache_rate,
  printf('%.2f%%', 100.0 * cache_hit_response_rate) AS response_hit_rate,
  datetime(last_response_at / 1000, 'unixepoch', 'localtime') AS last_response
FROM session_usage
ORDER BY last_response_at DESC;
"
```

查看某个 session 的逐响应缓存变化（替换示例 session ID）：

```sh
sqlite3 -header -column ~/.local/share/opencode/cache-usage/usage.sqlite "
SELECT
  message_id,
  input_tokens,
  uncached_input_tokens,
  cached_tokens,
  output_tokens,
  printf('%.2f%%', 100.0 * cached_tokens / NULLIF(input_tokens, 0)) AS token_cache_rate,
  datetime(completed_at / 1000, 'unixepoch', 'localtime') AS completed
FROM message_usage
WHERE session_id = 'ses_replace_me'
ORDER BY completed_at;
"
```

查看分模型累计统计：

```sh
sqlite3 -header -column ~/.local/share/opencode/cache-usage/usage.sqlite "
SELECT
  provider_id,
  model_id,
  COUNT(*) AS responses,
  SUM(input_tokens) AS input_tokens,
  SUM(cached_tokens) AS cached_tokens,
  printf('%.2f%%', 100.0 * SUM(cached_tokens) / NULLIF(SUM(input_tokens), 0)) AS token_cache_rate
FROM message_usage
GROUP BY provider_id, model_id
ORDER BY input_tokens DESC;
"
```

## 调试日志

调试默认关闭。创建标记文件即可启用：

```sh
mkdir -p ~/.local/share/opencode/cache-usage
touch ~/.local/share/opencode/cache-usage/debug.enabled
chmod 0600 ~/.local/share/opencode/cache-usage/debug.enabled
```

日志位置：

```text
~/.local/share/opencode/cache-usage/plugin-debug.jsonl
```

查看实时日志：

```sh
tail -f ~/.local/share/opencode/cache-usage/plugin-debug.jsonl
```

停止调试时删除 `debug.enabled`。调试日志记录 hook、session ID、provider/model、派生 UUID、是否应用以及 token 计数；不记录 prompt、response、Authorization、Cookie 或 API key。

## 统计口径和限制

OpenCode assistant message 中，`tokens.input` 是未缓存输入，`tokens.cache.read` 和 `tokens.cache.write` 单独提供。因此插件使用：

```text
input_tokens = tokens.input + tokens.cache.read + tokens.cache.write
```

这与 OpenAI Responses 原始 usage 不同：OpenAI 的 `input_tokens` 已包含 cached token，读取原始 API usage 时不能再次相加。

插件只统计形成已完成 assistant message 的调用，并跳过 input/output/cost 全为零的事件。某些 title 等辅助请求如果不形成这类消息，可能不会进入数据库，因此这里的总量不保证与 provider 的全局账单完全相同。

SQLite 保存 session ID 和用量，不保存 prompt、response、认证信息或派生 UUID。只有显式启用的调试日志会保存派生 UUID。
