import { afterEach, describe, expect, it } from 'vitest'
import { Finance } from '../src/finance.ts'
import { createRoutes, type CredentialStatus, type SessionHandle } from '../src/routes.ts'
import { initialState } from '../src/state.ts'
import type { BeancountView, StateRecord } from '../src/types.ts'
import { stubService } from './helpers.ts'

let service: Awaited<ReturnType<typeof stubService>> | undefined
afterEach(async () => { await service?.close(); service = undefined })

const pending = (id: string, created: string) => ({
  id, ledger_id: 'personal', status: 'pending', note: null, created_at: created,
  caller: { actor: 'agent', client_id: 'dsh', session_id: null },
  operation: { kind: 'close_account', account: 'Assets:Old', date: '2026-11-26' },
})

async function setup(routes: Parameters<typeof stubService>[0]) {
  service = await stubService(routes)
  const finance = new Finance(() => ({ baseUrl: service?.url ?? '', tokenRef: 'T', timeoutMs: 2000, guard: true, guardPaths: [] }), async () => 'tok')
  let state: BeancountView = initialState()
  const updates: StateRecord[] = []
  const handle: SessionHandle = {
    state: () => state,
    update: async (change) => {
      updates.push(change)
      state = { ...state, ...(change.ledger === undefined ? {} : { ledger: change.ledger }), groups: { ...state.groups, ...change.groups } }
    },
  }
  const credential = { stored: false as boolean }
  const status = async (): Promise<CredentialStatus> => ({ configured: credential.stored, writable: true })
  const routes_ = createRoutes({
    finance,
    session: id => (id === 's1' ? handle : undefined),
    credential: { status, set: async () => { credential.stored = true }, unset: async () => { credential.stored = false } },
  })
  const call = async (path: string, init?: { method?: string; body?: unknown }) => {
    const route = routes_.find(item => item.path === path.split('?')[0])
    if (route === undefined) throw new Error(`no route ${path}`)
    const request = new Request(`http://x/api/beancount${path}`, {
      method: init?.method ?? 'GET',
      ...(init?.body === undefined ? {} : { body: JSON.stringify(init.body), headers: { 'content-type': 'application/json' } }),
    })
    const response = await route.handle(request)
    return { status: response.status, body: await response.json() as any }
  }
  return { call, updates, state: () => state }
}

describe('dock routes', () => {
  it('give an overview of the active ledger, read as the user and with full details', async () => {
    const { call, updates } = await setup({
      'GET /agent/ledgers': { body: [{ id: 'personal', version: 'v' }] },
      'GET /ledgers/personal/accounts': { body: [{ name: 'Assets:Bank', details: { account_number: '12345678' } }, { name: 'Assets:Gone', close_date: '2026-01-01', details: {} }] },
      'GET /ledgers/personal/balances': { body: [{ account: 'Assets:Bank', balances: { GBP: '1' } }] },
    })
    const result = await call('/overview?session=s1')
    expect(result.status).toBe(200)
    expect(result.body.active).toBe('personal')
    expect(result.body.accounts.map((a: { name: string }) => a.name)).toEqual(['Assets:Bank'])
    expect(result.body.accounts[0].details.account_number).toBe('12345678')
    expect(service?.requests.every(request => request.headers['x-actor'] === 'user')).toBe(true)
    expect(updates).toEqual([])
  })

  it('show an overview even when the service is down', async () => {
    service = await stubService({})
    const { call } = await setup({})
    await service?.close()
    service = undefined
    const down = await call('/overview?session=s1').catch(() => undefined)
    expect(down === undefined || down.status === 200).toBe(true)
  })

  it('refuse an unknown session', async () => {
    const { call } = await setup({})
    expect((await call('/overview?session=nope')).status).toBe(400)
  })

  it('switch ledger only to a known one, and switch tool groups', async () => {
    const { call, updates, state } = await setup({ 'GET /agent/ledgers': { body: [{ id: 'personal', version: 'v' }] } })
    expect((await call('/ledger', { method: 'POST', body: { session: 's1', ledger: 'nope' } })).status).toBe(400)
    expect((await call('/ledger', { method: 'POST', body: { session: 's1', ledger: 'personal' } })).body.ledger).toBe('personal')
    expect((await call('/groups', { method: 'POST', body: { session: 's1', group: 'analysis', enabled: true } })).body.groups.analysis).toBe(true)
    expect((await call('/groups', { method: 'POST', body: { session: 's1', group: 'bogus', enabled: true } })).status).toBe(400)
    expect((await call('/groups', { method: 'POST', body: { session: 's1', group: 'record', enabled: 'yes' } })).status).toBe(400)
    expect(updates).toEqual([{ ledger: 'personal' }, { groups: { analysis: true } }])
    expect(state().ledger).toBe('personal')
  })

  it('list pending proposals across ledgers, oldest first, as text for review', async () => {
    const { call } = await setup({
      'GET /agent/ledgers': { body: [{ id: 'personal', version: 'v' }, { id: 'work', version: 'v' }] },
      'GET /ledgers/personal/changes': { body: [pending('late', '2026-11-26T12:00:00Z')] },
      'GET /ledgers/work/changes': { body: [pending('early', '2026-11-26T09:00:00Z')] },
    })
    const result = await call('/pending')
    expect(result.body.map((item: { change: { id: string } }) => item.change.id)).toEqual(['early', 'late'])
    expect(result.body[0].text).toMatch(/close Assets:Old/)
    expect(service?.requests.filter(request => request.path.endsWith('/changes')).every(request => request.query === '?status=pending')).toBe(true)
  })

  it('approve and reject as the user, with a JSON body the service requires', async () => {
    const { call } = await setup({
      'POST /ledgers/personal/changes/c1/approve': { body: { status: 'approved' } },
      'POST /ledgers/personal/changes/c2/reject': { body: { status: 'rejected' } },
    })
    expect((await call('/resolve', { method: 'POST', body: { ledger: 'personal', id: 'c1', verb: 'approve' } })).body.status).toBe('approved')
    await call('/resolve', { method: 'POST', body: { ledger: 'personal', id: 'c2', verb: 'reject', note: 'wrong' } })
    const [approve, reject] = service?.requests ?? []
    expect(JSON.parse(approve?.body ?? '')).toEqual({ note: null })
    expect(JSON.parse(reject?.body ?? '')).toEqual({ note: 'wrong' })
    expect(approve?.headers['x-actor']).toBe('user')
    expect((await call('/resolve', { method: 'POST', body: { ledger: 'personal', id: 'c1', verb: 'delete' } })).status).toBe(400)
  })

  it('pass the service\'s refusal to the page with its status', async () => {
    const { call } = await setup({ 'POST /ledgers/personal/changes/c1/approve': { status: 409, body: { detail: 'changed since it was proposed' } } })
    const result = await call('/resolve', { method: 'POST', body: { ledger: 'personal', id: 'c1', verb: 'approve' } })
    expect(result.status).toBe(409)
    expect(result.body.message).toBe('changed since it was proposed')
  })

  it('say whether the service answers and accepts the token, without raising an error', async () => {
    const { call } = await setup({ 'GET /agent/ledgers': { body: [{ id: 'personal', version: 'v' }] } })
    expect((await call('/status')).body).toEqual({ ok: true, ledgers: ['personal'], credential: { configured: false, writable: true } })
    const refused = await setup({ 'GET /agent/ledgers': { status: 401, body: { detail: 'missing or invalid bearer token' } } })
    const answer = await refused.call('/status')
    expect(answer.status).toBe(200)
    expect(answer.body).toMatchObject({ ok: false, message: 'missing or invalid bearer token', status: 401 })
  })

  it('store and remove the token without ever returning it', async () => {
    const { call } = await setup({})
    expect((await call('/credential')).body).toEqual({ configured: false, writable: true })
    const saved = await call('/credential', { method: 'POST', body: { value: 'secret-token' } })
    expect(saved.body).toEqual({ configured: true, writable: true })
    expect(JSON.stringify(saved.body)).not.toContain('secret-token')
    expect((await call('/credential', { method: 'POST', body: { value: '' } })).body.configured).toBe(false)
  })
})
