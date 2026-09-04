import { createHash } from "node:crypto"
import { appendFileSync, chmodSync, existsSync, mkdirSync } from "node:fs"
import { homedir } from "node:os"
import { join } from "node:path"
import type { Plugin } from "@opencode-ai/plugin"
import { Database } from "bun:sqlite"

const OPENCODE_NAMESPACE = "d80166ed-d0d3-54b5-be3f-a1ebf39c91c0"

function uuidBytes(value: string): Buffer {
  const hex = value.replaceAll("-", "")
  if (!/^[0-9a-f]{32}$/i.test(hex)) throw new Error(`Invalid UUID namespace: ${value}`)
  return Buffer.from(hex, "hex")
}

function formatUuid(bytes: Buffer): string {
  const hex = bytes.toString("hex")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function uuidv5(name: string, namespace = OPENCODE_NAMESPACE): string {
  const bytes = createHash("sha1")
    .update(uuidBytes(namespace))
    .update(name, "utf8")
    .digest()
    .subarray(0, 16)
  bytes[6] = 0x50 | (bytes[6] & 0x0f)
  bytes[8] = 0x80 | (bytes[8] & 0x3f)
  return formatUuid(bytes)
}

function cacheKeyForSession(sessionID: string): string {
  return uuidv5(sessionID)
}

function applies(input: {
  model?: { providerID?: string; id?: string }
}): boolean {
  return input.model?.id?.toLowerCase().startsWith("gpt") === true
}

function tokenCount(value: unknown): number {
  const count = Number(value)
  return Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : 0
}

function numericCost(value: unknown): number {
  const cost = Number(value)
  return Number.isFinite(cost) ? Math.max(0, cost) : 0
}

export const OpenAICacheAffinity: Plugin = async () => {
  const dataRoot = process.env.XDG_DATA_HOME || join(homedir(), ".local", "share")
  const usageDirectory = join(dataRoot, "opencode", "cache-usage")
  const usagePath = join(usageDirectory, "usage.sqlite")
  const debugMarker = join(usageDirectory, "debug.enabled")
  const debugPath = join(usageDirectory, "plugin-debug.jsonl")
  mkdirSync(usageDirectory, { recursive: true, mode: 0o700 })
  chmodSync(usageDirectory, 0o700)

  const debug = (event: string, fields: Record<string, unknown> = {}) => {
    if (!existsSync(debugMarker)) return
    try {
      appendFileSync(debugPath, `${JSON.stringify({ timestamp: new Date().toISOString(), event, ...fields })}\n`, {
        encoding: "utf8",
        mode: 0o600,
      })
      chmodSync(debugPath, 0o600)
    } catch (error) {
      console.error("[openai-cache-affinity] failed to write debug log", error)
    }
  }

  const database = new Database(usagePath, { create: true })
  chmodSync(usagePath, 0o600)
  database.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    PRAGMA busy_timeout = 5000;

    CREATE TABLE IF NOT EXISTS message_usage (
      message_id TEXT PRIMARY KEY,
      session_id TEXT NOT NULL,
      provider_id TEXT NOT NULL,
      model_id TEXT NOT NULL,
      input_tokens INTEGER NOT NULL,
      uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
      output_tokens INTEGER NOT NULL,
      cached_tokens INTEGER NOT NULL,
      cache_write_tokens INTEGER NOT NULL,
      reasoning_tokens INTEGER NOT NULL,
      cost REAL NOT NULL,
      finish TEXT,
      is_summary INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      completed_at INTEGER NOT NULL,
      updated_at INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS message_usage_session_model
      ON message_usage (session_id, provider_id, model_id);

    DROP VIEW IF EXISTS session_usage;
  `)

  const columns = database.query("PRAGMA table_info(message_usage)").all() as Array<{ name: string }>
  if (!columns.some((column) => column.name === "uncached_input_tokens")) {
    database.exec("ALTER TABLE message_usage ADD COLUMN uncached_input_tokens INTEGER NOT NULL DEFAULT 0")
  }

  database.exec(`
    CREATE VIEW session_usage AS
      SELECT
        session_id,
        provider_id,
        model_id,
        COUNT(*) AS response_count,
        SUM(input_tokens) AS input_tokens,
        SUM(uncached_input_tokens) AS uncached_input_tokens,
        SUM(output_tokens) AS output_tokens,
        SUM(cached_tokens) AS cached_tokens,
        SUM(cache_write_tokens) AS cache_write_tokens,
        SUM(reasoning_tokens) AS reasoning_tokens,
        SUM(cost) AS cost,
        SUM(CASE WHEN cached_tokens > 0 THEN 1 ELSE 0 END) AS cache_hit_responses,
        CAST(SUM(cached_tokens) AS REAL) / NULLIF(SUM(input_tokens), 0) AS cache_hit_rate,
        CAST(SUM(CASE WHEN cached_tokens > 0 THEN 1 ELSE 0 END) AS REAL)
          / NULLIF(COUNT(*), 0) AS cache_hit_response_rate,
        MIN(created_at) AS first_response_at,
        MAX(completed_at) AS last_response_at
      FROM message_usage
      WHERE input_tokens > 0 OR output_tokens > 0
      GROUP BY session_id, provider_id, model_id;
  `)

  const saveUsage = database.query(`
    INSERT INTO message_usage (
      message_id, session_id, provider_id, model_id,
      input_tokens, uncached_input_tokens, output_tokens,
      cached_tokens, cache_write_tokens, reasoning_tokens,
      cost, finish, is_summary, created_at, completed_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(message_id) DO UPDATE SET
      session_id = excluded.session_id,
      provider_id = excluded.provider_id,
      model_id = excluded.model_id,
      input_tokens = excluded.input_tokens,
      uncached_input_tokens = excluded.uncached_input_tokens,
      output_tokens = excluded.output_tokens,
      cached_tokens = excluded.cached_tokens,
      cache_write_tokens = excluded.cache_write_tokens,
      reasoning_tokens = excluded.reasoning_tokens,
      cost = excluded.cost,
      finish = excluded.finish,
      is_summary = excluded.is_summary,
      created_at = excluded.created_at,
      completed_at = excluded.completed_at,
      updated_at = excluded.updated_at
  `)

  debug("initialized", { usagePath })

  return {
    "chat.params": async (input, output) => {
      const applied = applies(input)
      const cacheKey = applied ? cacheKeyForSession(input.sessionID) : null
      debug("chat.params", {
        inputKeys: Object.keys(input),
        sessionID: input.sessionID,
        providerID: input.model?.providerID ?? null,
        modelID: input.model?.id ?? null,
        providerContextID: input.provider?.info?.id ?? null,
        applied,
        cacheKey,
      })
      if (!applied || !cacheKey) return
      output.options.promptCacheKey = cacheKey
    },

    "chat.headers": async (input, output) => {
      const applied = applies(input)
      const cacheKey = applied ? cacheKeyForSession(input.sessionID) : null
      debug("chat.headers", {
        inputKeys: Object.keys(input),
        sessionID: input.sessionID,
        providerID: input.model?.providerID ?? null,
        modelID: input.model?.id ?? null,
        providerContextID: input.provider?.info?.id ?? null,
        applied,
        cacheKey,
      })
      if (!applied || !cacheKey) return
      output.headers["x-session-affinity"] = cacheKey
      // Match OpenCode's casing so the final object merge replaces its default key.
      output.headers["X-Session-Id"] = cacheKey
    },

    event: async ({ event }) => {
      if (event.type !== "message.updated") return
      const info = event.properties.info
      if (info.role !== "assistant" || info.time.completed === undefined) return

      const uncachedInput = tokenCount(info.tokens.input)
      const cachedInput = tokenCount(info.tokens.cache.read)
      const cacheWrite = tokenCount(info.tokens.cache.write)
      const reasoningOutput = tokenCount(info.tokens.reasoning)
      const totalInput = uncachedInput + cachedInput + cacheWrite
      const totalOutput = tokenCount(info.tokens.output) + reasoningOutput
      const cost = numericCost(info.cost)
      if (totalInput === 0 && totalOutput === 0 && cost === 0) {
        debug("usage.skipped", {
          messageID: info.id,
          sessionID: info.sessionID,
          reason: "zero usage",
        })
        return
      }

      saveUsage.run(
        info.id,
        info.sessionID,
        info.providerID,
        info.modelID,
        totalInput,
        uncachedInput,
        totalOutput,
        cachedInput,
        cacheWrite,
        reasoningOutput,
        cost,
        info.finish ?? null,
        info.summary ? 1 : 0,
        tokenCount(info.time.created),
        tokenCount(info.time.completed),
        Date.now(),
      )
      debug("usage.saved", {
        messageID: info.id,
        sessionID: info.sessionID,
        providerID: info.providerID,
        modelID: info.modelID,
        inputTokens: totalInput,
        cachedTokens: cachedInput,
        outputTokens: totalOutput,
      })
    },

    dispose: async () => {
      debug("disposed")
      database.close()
    },
  }
}

export default OpenAICacheAffinity
