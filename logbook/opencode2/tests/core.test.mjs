import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import { join } from 'node:path'
import test from 'node:test'
import { createLogbook, hasTail, COMPACTION_INSTRUCTION } from '../core.mjs'

async function fixture(t) {
  await mkdir('/tmp/opencode', { recursive: true })
  const temp = await mkdtemp('/tmp/opencode/logbook-v2-test-')
  t.after(() => rm(temp, { recursive: true, force: true }))
  const calls = []
  const reports = []
  const info = { id: 's1', agent: 'build', location: { directory: '/workspace' }, time: { archived: 1 }, model: { providerID: 'provider', id: 'model' } }
  let messages = []
  let onCompact = () => { messages = [{ type: 'compaction', id: 'c2', status: 'completed', summary: 'final summary' }] }
  const ctx = {
    location: { directory: '/workspace' }, options: { logRoot: join(temp, 'logs') },
    session: {
      get: async () => { calls.push('get'); return info },
      context: async () => { calls.push('context'); return messages },
      wait: async () => { calls.push('wait') },
      compact: async () => { calls.push('compact'); await onCompact() },
      hook: async (_name, _callback) => ({ dispose: async () => {} }),
    },
  }
  const book = createLogbook(ctx, { report: error => reports.push(error) })
  const log = join(ctx.options.logRoot, 'opencode_s1.md')
  const ended = (text = 'summary', id = 'event1') => ({ type: 'session.compaction.ended', id, location: { directory: '/workspace' }, data: { sessionID: 's1', text } })
  const archive = () => book.handleEvent({ type: 'session.archived', id: 'archive1', data: { sessionID: 's1' } })
  return { book, ctx, info, reports, log, ended, archive, calls,
    messages: value => { messages = value }, compact: callback => { onCompact = callback } }
}

const completed = (id = 'c1', summary = 'summary', metadata = {}) => ({ type: 'compaction', status: 'completed', id, summary, metadata })

test('compaction text and content hash persist once across events and restarts', async t => {
  const f = await fixture(t)
  await Promise.all([f.book.handleEvent(f.ended()), f.book.handleEvent(f.ended('summary', 'event2'))])
  const restarted = createLogbook(f.ctx)
  await restarted.handleEvent(f.ended())
  const text = await readFile(f.log, 'utf8')
  assert.equal((text.match(/opencode2-summary-sha256:/g) || []).length, 1)
  assert.match(text, /opencode2-source: event1/)
  assert.match(text, /summary/)
  assert.equal((await stat(f.log)).mode & 0o777, 0o600)
  assert.equal((await stat(f.ctx.options.logRoot)).mode & 0o777, 0o700)
})

test('global foreign location, helper agents and unrelated events are ignored', async t => {
  const f = await fixture(t)
  await f.book.handleEvent({ ...f.ended(), location: { directory: '/other-project' } })
  assert.equal(f.calls.length, 0)
  f.info.agent = 'logbook'
  await f.book.handleEvent(f.ended())
  f.info.agent = 'build'
  f.info.metadata = { 'logbook.skip': true }
  await f.book.handleEvent(f.ended())
  await f.book.handleEvent({ type: 'session.deleted', data: { sessionID: 's1' } })
  await f.book.handleEvent({ type: 'session.idle', data: { sessionID: 's1' } })
  await assert.rejects(readFile(f.log), { code: 'ENOENT' })
})

test('compaction hook adds typed system instruction only to owned ordinary sessions', async t => {
  const f = await fixture(t)
  const input = { sessionID: 's1', system: [] }
  await f.book.beforeCompaction(input)
  assert.deepEqual(input.system, [{ type: 'text', text: COMPACTION_INSTRUCTION }])
  f.info.agent = 'logbook'
  await f.book.beforeCompaction(input)
  assert.equal(input.system.length, 1)
})

test('archive without tail backfills existing summary but never recompacts recent metadata', async t => {
  const f = await fixture(t)
  f.messages([completed('c1', 'summary', { recent: 'kept original user and assistant text' }), { type: 'idle', id: 'idle' }])
  await f.archive()
  await f.archive()
  assert.equal(f.calls.filter(value => value === 'compact').length, 0)
  assert.equal(((await readFile(f.log, 'utf8')).match(/opencode2-summary-sha256:/g) || []).length, 1)
})

test('archive with new activity compacts once and deduplicates its queued ended event', async t => {
  const f = await fixture(t)
  f.messages([completed(), { type: 'user', id: 'new-user' }, { type: 'assistant', id: 'reply' }])
  f.compact(() => {
    f.messages([completed('c2', 'final summary')])
    // Must not await the queued callback from inside the archive task.
    f.book.handleEvent(f.ended('final summary', 'generated-event')).catch(() => {})
  })
  await f.archive()
  await f.book.drain()
  await f.archive()
  assert.equal(f.calls.filter(value => value === 'compact').length, 1)
  assert.equal(((await readFile(f.log, 'utf8')).match(/opencode2-summary-sha256:/g) || []).length, 2)
  assert.ok(f.calls.indexOf('wait') < f.calls.indexOf('compact'))
})

test('empty sessions and unarchived sessions do not trigger archive compaction', async t => {
  const f = await fixture(t)
  await f.archive()
  f.messages([{ type: 'user', id: 'new-user' }])
  delete f.info.time.archived
  await f.archive()
  assert.equal(f.calls.filter(value => value === 'compact').length, 0)
  assert.equal(hasTail([completed(), { type: 'idle' }]), false)
})

test('failed compaction reports error and can be retried without poisoning session queue', async t => {
  const f = await fixture(t)
  f.messages([{ type: 'user', id: 'new-user' }])
  f.compact(() => {})
  await assert.rejects(f.archive(), /did not complete/)
  await f.book.drain()
  assert.equal(f.reports.length, 1)
  f.compact(() => f.messages([completed('c2', 'recovered')]))
  await f.archive()
  assert.match(await readFile(f.log, 'utf8'), /recovered/)
})

test('empty completed summary is observable and not persisted', async t => {
  const f = await fixture(t)
  await assert.rejects(f.book.handleEvent(f.ended(' ')), /empty completed/)
  assert.equal(f.reports.length, 1)
  await assert.rejects(readFile(f.log), { code: 'ENOENT' })
})

test('subscription ending unexpectedly is observable and hook is disposed', async t => {
  const f = await fixture(t)
  let disposed = false
  f.ctx.session.hook = async () => ({ dispose: async () => { disposed = true } })
  f.ctx.event = { subscribe: async function* () {} }
  const stop = await f.book.start()
  await new Promise(resolve => setImmediate(resolve))
  assert.match(String(f.reports[0]), /subscription ended unexpectedly/)
  await stop()
  assert.equal(disposed, true)
})


test('separate instances serialize the same file and preserve a v1 logbook', async t => {
  const f = await fixture(t)
  const { writeFile } = await import('node:fs/promises')
  await mkdir(f.ctx.options.logRoot, { recursive: true, mode: 0o700 })
  await writeFile(f.log, '# Existing v1 logbook\n<!-- compaction_message_id: old -->\n', { mode: 0o600 })
  const second = createLogbook(f.ctx)
  await Promise.all([f.book.handleEvent(f.ended('first summary')), second.handleEvent(f.ended('second summary'))])
  const text = await readFile(f.log, 'utf8')
  assert.match(text, /Existing v1 logbook/)
  assert.match(text, /first summary/)
  assert.match(text, /second summary/)
  assert.equal((text.match(/opencode2-summary-sha256:/g) || []).length, 2)
})
