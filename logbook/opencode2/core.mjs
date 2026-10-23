import { createHash } from 'node:crypto'
import { chmod, mkdir, open, readFile, rename, rm, stat } from 'node:fs/promises'
import { homedir } from 'node:os'
import { basename, join, resolve } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'

export const COMPACTION_INSTRUCTION = '摘要还会归档为可检索工作日志。请明确写出：本阶段目标、已完成、重要文件（保留准确路径）、测试与验证（保留命令和结果）、重要决策、未完成与后续。只写实际发生的事，不推测。'
const activityTypes = new Set(['user', 'assistant', 'synthetic', 'shell', 'skill'])
export const safeName = value => String(value).replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._]+|[._]+$/g, '').slice(0, 160) || 'unknown-session'
const quoted = value => JSON.stringify(value == null ? '' : String(value))
export function latestCompleted(messages) {
  return messages.findLast(item => item.type === 'compaction' && item.status === 'completed')
}
export function hasTail(messages) {
  const boundary = messages.findLastIndex(item => item.type === 'compaction' && item.status === 'completed')
  return messages.slice(boundary + 1).some(item => activityTypes.has(item.type))
}
const excluded = info => info.agent === 'logbook' || info.metadata?.logbook === true || info.metadata?.['logbook.skip'] === true

// Directory locks also serialize separate plugin instances sharing a log root.
async function lock(path) {
  for (let attempt = 0; attempt < 200; attempt++) {
    try {
      await mkdir(path, { mode: 0o700 })
      const owner = await open(join(path, 'owner'), 'wx', 0o600)
      try { await owner.writeFile(String(process.pid)) } finally { await owner.close() }
      return () => rm(path, { recursive: true, force: true })
    } catch (error) {
      if (error.code !== 'EEXIST') throw error
      try {
        const owner = Number(await readFile(join(path, 'owner'), 'utf8'))
        if (Number.isInteger(owner) && owner > 0) {
          try { process.kill(owner, 0) } catch (dead) {
            if (dead.code === 'ESRCH') await rm(path, { recursive: true, force: true })
          }
        }
      } catch (missing) {
        if (missing.code !== 'ENOENT') throw missing
        // Recover a process that died between mkdir and writing its owner.
        try { if (Date.now() - (await stat(path)).mtimeMs > 300_000) await rm(path, { recursive: true, force: true }) } catch {}
      }
      await sleep(25)
    }
  }
  throw new Error('timed out acquiring logbook file lock')
}

export function createLogbook(ctx, options = {}) {
  const root = options.logRoot || ctx.options?.logRoot || process.env.AGENT_LOGBOOK_DIR || join(homedir(), '.agents', 'logbooks')
  const directory = resolve(ctx.location.directory)
  const report = options.report || (error => console.error('[logbook-v2]', error))
  const queues = new Map()
  let closing = false
  const controller = new AbortController()
  const request = { signal: controller.signal }

  async function infoFor(sessionID, event) {
    if (event?.location?.directory && resolve(event.location.directory) !== directory) return null
    const info = await ctx.session.get({ sessionID }, request)
    if (!info.location?.directory || resolve(info.location.directory) !== directory || excluded(info)) return null
    return info
  }

  async function append(info, summary, source) {
    if (typeof summary !== 'string' || !summary.trim()) throw new Error(`empty completed compaction summary for ${info.id}`)
    summary = summary.trim()
    const digest = createHash('sha256').update(summary).digest('hex')
    const marker = `<!-- opencode2-summary-sha256: ${digest} -->`
    await mkdir(root, { recursive: true, mode: 0o700 })
    await chmod(root, 0o700)
    const locks = join(root, '.locks')
    await mkdir(locks, { recursive: true, mode: 0o700 })
    const release = await lock(join(locks, `opencode_${safeName(info.id)}.lock`))
    const path = join(root, `opencode_${safeName(info.id)}.md`)
    try {
      let previous = ''
      try { previous = await readFile(path, 'utf8') } catch (error) { if (error.code !== 'ENOENT') throw error }
      if (previous.includes(marker)) return false
      const timestamp = new Date().toISOString()
      const header = previous ? '' : [
        '---', `session_id: ${quoted(info.id)}`, 'agent: opencode', 'opencode_version: 2',
        `created_at: ${quoted(timestamp)}`, `cwd: ${quoted(directory)}`,
        `project: ${quoted(basename(directory))}`, `model: ${quoted(info.model?.id)}`,
        `provider: ${quoted(info.model?.providerID)}`, '---', '', '# Session Logbook', '',
      ].join('\n')
      const page = ['---', '', `## ${timestamp}`, '', marker,
        `<!-- opencode2-source: ${safeName(source)} -->`, '', summary, ''].join('\n')
      const temp = `${path}.tmp-${process.pid}-${createHash('sha256').update(String(Math.random())).digest('hex').slice(0, 12)}`
      try {
        const file = await open(temp, 'wx', 0o600)
        try { await file.writeFile(previous + header + page); await file.sync() } finally { await file.close() }
        await rename(temp, path)
        await chmod(path, 0o600)
        const folder = await open(root, 'r')
        try { await folder.sync() } finally { await folder.close() }
      } finally { await rm(temp, { force: true }) }
      return true
    } finally { await release() }
  }

  function enqueue(sessionID, task) {
    if (closing) return Promise.resolve()
    const current = (queues.get(sessionID) || Promise.resolve()).catch(() => {}).then(task)
    queues.set(sessionID, current)
    current.catch(report).finally(() => { if (queues.get(sessionID) === current) queues.delete(sessionID) })
    return current
  }

  async function archive(sessionID, event) {
    let info = await infoFor(sessionID, event)
    if (!info || info.time?.archived == null) return
    await ctx.session.wait({ sessionID }, request)
    info = await infoFor(sessionID, event)
    if (!info || info.time?.archived == null) return
    const before = await ctx.session.context({ sessionID }, request)
    const latest = latestCompleted(before)
    if (latest) await append({ ...info, model: latest.model || info.model }, latest.summary, latest.id)
    if (!hasTail(before)) return
    await ctx.session.compact({ sessionID }, request)
    await ctx.session.wait({ sessionID }, request)
    const after = await ctx.session.context({ sessionID }, request)
    const completed = latestCompleted(after)
    if (!completed || completed.id === latest?.id) throw new Error(`archive compaction did not complete for ${sessionID}`)
    await append({ ...info, model: completed.model || info.model }, completed.summary, completed.id)
    // Its compaction.ended event is queued separately; the content marker makes it a no-op.
  }

  function handleEvent(event) {
    if (event.type !== 'session.compaction.ended' && event.type !== 'session.archived') return Promise.resolve()
    const sessionID = event.data?.sessionID
    if (!sessionID) return Promise.resolve()
    return enqueue(sessionID, async () => {
      if (event.type === 'session.archived') return archive(sessionID, event)
      const info = await infoFor(sessionID, event)
      if (info) await append({ ...info, model: event.data.model || info.model }, event.data.text, event.id)
    })
  }

  async function beforeCompaction(input) {
    const info = await infoFor(input.sessionID)
    if (info) input.system.push({ type: 'text', text: COMPACTION_INSTRUCTION })
  }

  async function start() {
    const hook = await ctx.session.hook('compaction', beforeCompaction)
    const subscription = ctx.event.subscribe({ signal: controller.signal })
    const listener = (async () => {
      try {
        for await (const event of subscription) {
          // Do not await per-session work here: archive can generate more events.
          handleEvent(event).catch(() => {})
        }
        if (!closing) report(new Error('event subscription ended unexpectedly; logbook events may be missed'))
      } catch (error) { if (!closing) report(error) }
    })()
    return async () => {
      closing = true
      controller.abort()
      await hook.dispose()
      await listener
      await Promise.allSettled([...queues.values()])
    }
  }
  return { start, handleEvent, beforeCompaction, drain: () => Promise.allSettled([...queues.values()]) }
}
