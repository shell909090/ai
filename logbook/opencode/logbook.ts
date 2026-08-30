import type { Plugin } from "@opencode-ai/plugin"
import { chmod, mkdir, open, readFile, rename, rmdir, stat, unlink, writeFile } from "node:fs/promises"
import { homedir } from "node:os"
import { basename, join } from "node:path"

const logRoot = process.env.AGENT_LOGBOOK_DIR || join(homedir(), ".agents", "logbooks")
const lockRoot = join(logRoot, ".locks")
const pending = new Set<Promise<void>>()
const queues = new Map<string, Promise<void>>()
const archived = new Map<string, string>()

function safeName(value: string): string {
  return value.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "").slice(0, 160) || "unknown-session"
}

function yamlString(value: unknown): string {
  return JSON.stringify(value == null ? "" : String(value))
}

function localISO(date = new Date()): string {
  const offsetMinutes = -date.getTimezoneOffset()
  const shifted = new Date(date.getTime() + offsetMinutes * 60_000).toISOString().replace("Z", "")
  const sign = offsetMinutes >= 0 ? "+" : "-"
  const absolute = Math.abs(offsetMinutes)
  const offset = `${String(Math.floor(absolute / 60)).padStart(2, "0")}:${String(absolute % 60).padStart(2, "0")}`
  return `${shifted}${sign}${offset}`
}

async function acquireLock(path: string): Promise<() => Promise<void>> {
  await mkdir(lockRoot, { recursive: true, mode: 0o700 })
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      await mkdir(path, { mode: 0o700 })
      return async () => { await rmdir(path).catch(() => undefined) }
    } catch (error: any) {
      if (error?.code !== "EEXIST") throw error
      try {
        const info = await stat(path)
        if (Date.now() - info.mtimeMs > 120_000) await rmdir(path)
      } catch {
        // Another writer may have released the lock between stat and rmdir.
      }
      await Bun.sleep(50)
    }
  }
  throw new Error(`timed out waiting for logbook lock: ${path}`)
}

async function atomicAppend(path: string, content: string): Promise<void> {
  let previous = ""
  try {
    previous = await readFile(path, "utf8")
  } catch (error: any) {
    if (error?.code !== "ENOENT") throw error
  }
  const temp = `${path}.tmp-${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`
  try {
    await writeFile(temp, previous + content, { encoding: "utf8", mode: 0o600 })
    const handle = await open(temp, "r")
    try { await handle.sync() } finally { await handle.close() }
    await rename(temp, path)
    await chmod(path, 0o600)
  } catch (error) {
    await unlink(temp).catch(() => undefined)
    throw error
  }
}

function track(sessionID: string, task: () => Promise<void>): void {
  const prior = queues.get(sessionID) || Promise.resolve()
  const current = prior.catch(() => undefined).then(task)
  queues.set(sessionID, current)
  pending.add(current)
  current.catch((error) => console.error("[logbook]", error)).finally(() => {
    pending.delete(current)
    if (queues.get(sessionID) === current) queues.delete(sessionID)
  })
}

export const Logbook: Plugin = async ({ client, directory, project }) => ({
  "experimental.session.compacting": async (_input, output) => {
    output.context.push(
      "摘要还会归档为可检索工作日志。请明确写出：本阶段目标、已完成、重要文件（保留准确路径）、测试与验证（保留命令和结果）、重要决策、未完成与后续。只写实际发生的事，不推测。",
    )
  },

  event: async ({ event }) => {
    if (event.type === "session.updated") {
      const info: any = event.properties.info
      const sessionID = String(info?.id || "")
      const archivedAt = info?.time?.archived
      if (!sessionID) return
      if (archivedAt == null) {
        archived.delete(sessionID)
        return
      }

      const archiveKey = String(archivedAt)
      if (archived.get(sessionID) === archiveKey) return
      archived.set(sessionID, archiveKey)
      track(sessionID, async () => {
        try {
          const response: any = await client.session.messages({ path: { id: sessionID }, query: { directory } })
          const messages: any[] = response.data || []
          const lastUser = messages.findLast((item) => item.info?.role === "user" && item.info?.model)
          const model = lastUser?.info?.model || info?.model
          const providerID = model?.providerID
          const modelID = model?.modelID
          if (!providerID || !modelID) throw new Error(`no model found for archived session ${sessionID}`)

          const result: any = await client.session.summarize({
            path: { id: sessionID },
            query: { directory },
            body: { providerID, modelID },
          })
          if (result.error) throw new Error(`failed to compact archived session ${sessionID}: ${JSON.stringify(result.error)}`)
        } catch (error) {
          archived.delete(sessionID)
          throw error
        }
      })
      return
    }

    if (event.type !== "session.compacted") return
    const sessionID = event.properties.sessionID
    track(sessionID, async () => {
      const query = { directory, limit: 20 }
      let response: any = await client.session.messages({ path: { id: sessionID }, query })
      let messages: any[] = response.data || []
      let summaries = messages.filter((item) =>
        item.info?.role === "assistant" && item.info?.summary === true && item.info?.finish && !item.info?.error,
      )
      if (!summaries.length) {
        response = await client.session.messages({ path: { id: sessionID }, query: { directory } })
        messages = response.data || []
        summaries = messages.filter((item) =>
          item.info?.role === "assistant" && item.info?.summary === true && item.info?.finish && !item.info?.error,
        )
      }
      summaries.sort((a, b) => {
        const time = (a.info?.time?.created || 0) - (b.info?.time?.created || 0)
        return time || String(a.info?.id || "").localeCompare(String(b.info?.id || ""))
      })
      const latest = summaries.at(-1)
      if (!latest) throw new Error(`no completed compaction summary found for ${sessionID}`)
      const messageID = String(latest.info.id)
      const summary = latest.parts
        .filter((part: any) => part.type === "text" && part.text?.trim())
        .map((part: any) => part.text.trim())
        .join("\n\n")
      if (!summary) throw new Error(`compaction summary ${messageID} has no text`)

      await mkdir(logRoot, { recursive: true, mode: 0o700 })
      const path = join(logRoot, `opencode_${safeName(sessionID)}.md`)
      const lockPath = join(lockRoot, `opencode_${safeName(sessionID)}.lock`)
      const release = await acquireLock(lockPath)
      try {
        let existing = ""
        try { existing = await readFile(path, "utf8") } catch (error: any) {
          if (error?.code !== "ENOENT") throw error
        }
        const marker = `<!-- compaction_message_id: ${messageID} -->`
        if (existing.includes(marker)) return
        const created = localISO()
        const info = latest.info || {}
        const header = existing ? "" : [
          "---",
          `session_id: ${yamlString(sessionID)}`,
          "agent: opencode",
          `created_at: ${yamlString(created)}`,
          `cwd: ${yamlString(info.path?.cwd || directory)}`,
          `project: ${yamlString(basename(project.worktree || directory))}`,
          `model: ${yamlString(info.modelID || info.model?.modelID)}`,
          `provider: ${yamlString(info.providerID || info.model?.providerID)}`,
          "---",
          "",
          "# Session Logbook",
          "",
        ].join("\n")
        const page = ["---", "", `## ${created}`, "", marker, "", summary, ""].join("\n")
        await atomicAppend(path, header + page)
      } finally {
        await release()
      }
    })
  },

  dispose: async () => {
    await Promise.allSettled([...pending])
  },
})

export default Logbook
