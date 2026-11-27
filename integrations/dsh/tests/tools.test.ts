import type { Agent } from '@deepseek-ai/dsh-agent'
import { afterEach, describe, expect, it } from 'vitest'
import { Finance } from '../src/finance.ts'
import { defaultLedgerState } from '../src/state.ts'
import { financeTools } from '../src/tools.ts'
import type { BeancountView, StateRecord } from '../src/types.ts'
import { stubService } from './helpers.ts'

let service: Awaited<ReturnType<typeof stubService>> | undefined
afterEach(async () => { await service?.close(); service = undefined })

const change = {
  id: 'c1', ledger_id: 'personal', status: 'pending', note: null, created_at: '2026-11-26T10:00:00Z',
  caller: { actor: 'agent', client_id: 'dsh', session_id: 's' },
  operation: { kind: 'add_transaction', transaction: { date: '2026-11-26', payee: null, narration: 'Lunch', postings: [
    { account: 'Expenses:Food', units: { number: '12.50', currency: 'GBP' } },
    { account: 'Assets:Cash', units: { number: '-12.50', currency: 'GBP' } },
  ] } },
}

async function setup(routes: Parameters<typeof stubService>[0], ledger: string | null = 'personal') {
  service = await stubService(routes)
  const finance = new Finance(() => ({ baseUrl: service?.url ?? '', tokenRef: 'T', timeoutMs: 2000, guard: true, guardPaths: [] }), async () => 'tok')
  let state: BeancountView = { ...defaultLedgerState(), ledger, turns: 0 }
  const updates: StateRecord[] = []
  const tools = financeTools({
    finance,
    stateOf: () => state,
    update: async (_agent, patch) => { updates.push(patch); if (patch.ledger !== undefined) state = { ...state, ledger: patch.ledger } },
  })
  const agent = { session: { id: 'session-1' } } as unknown as Agent
  const run = (name: string, args: Record<string, unknown> = {}) => {
    const tool = tools.find(item => item.definition.name === name)
    if (tool === undefined) throw new Error(`no tool ${name}`)
    return tool.definition.execute(args, { agent, signal: new AbortController().signal } as never) as Promise<string>
  }
  return { tools, run, updates, state: () => state }
}

describe('the finance tools', () => {
  it('take no ledger except the one that chooses it, and have no way to approve', async () => {
    const { tools } = await setup({})
    const names = tools.map(tool => tool.definition.name)
    expect(names.length).toBeGreaterThan(15)
    expect(names.every(name => name.startsWith('finance_'))).toBe(true)
    expect(names.filter(name => /approve|reject|resolve/.test(name))).toEqual([])
    for (const { definition } of tools.filter(tool => tool.definition.name !== 'finance_use_ledger')) {
      expect(JSON.stringify(definition.parameters)).not.toMatch(/"ledger"/)
    }
  })

  it('put recording and analysis in groups a person can switch, and leave reading always on', async () => {
    const { tools } = await setup({})
    const group = (name: string) => tools.find(tool => tool.definition.name === name)?.group
    expect(group('finance_accounts')).toBe('core')
    expect(group('finance_use_ledger')).toBe('core')
    expect(group('finance_expense')).toBe('record')
    expect(group('finance_due')).toBe('analysis')
    expect(group('finance_position')).toBe('analysis')
    expect(group('finance_open_items')).toBe('analysis')
  })

  it('send the session\'s ledger with each request and tell the model the proposal waits', async () => {
    const { run } = await setup({ 'POST /agent/expenses': { status: 201, body: change } })
    const text = await run('finance_expense', { from_account: 'Cash', expense_account: 'Food', amount: '12.50 GBP', narration: 'Lunch' })
    const [sent] = service?.requests ?? []
    expect(JSON.parse(sent?.body ?? '{}')).toEqual({ ledger: 'personal', from_account: 'Cash', expense_account: 'Food', amount: '12.50 GBP', narration: 'Lunch' })
    expect(sent?.headers['x-session-id']).toBe('session-1')
    expect(sent?.headers.authorization).toBe('Bearer tok')
    expect(text).toMatch(/Expenses:Food {2}12.50 GBP/)
    expect(text).toMatch(/waiting for the user to approve/)
  })

  it('leave the ledger out when none is chosen, and explain a refusal to name one', async () => {
    const { run } = await setup({ 'GET /agent/accounts': { status: 422, body: { detail: 'name the ledger: home, work' } } }, null)
    await expect(run('finance_accounts')).rejects.toThrow(/Several ledgers exist \(home, work\)\. Call finance_use_ledger/)
    expect(service?.requests[0]?.query).toBe('')
  })

  it('switch ledger only to one that exists', async () => {
    const { run, updates, state } = await setup({ 'GET /agent/ledgers': { body: [{ id: 'home', version: 'v' }, { id: 'work', version: 'v' }] } }, null)
    await expect(run('finance_use_ledger', { ledger: 'nope' })).rejects.toThrow(/There is no ledger "nope"\. The ledgers are: home, work/)
    expect(updates).toEqual([])
    expect(await run('finance_use_ledger', { ledger: 'work' })).toMatch(/Now working on ledger work/)
    expect(updates).toEqual([{ ledger: 'work' }])
    expect(state().ledger).toBe('work')
  })

  it('read accounts and balances as short text', async () => {
    const { run } = await setup({
      'GET /agent/accounts': { body: [{ name: 'Assets:Bank:Current', type: 'checking', currencies: ['GBP'], description: 'Everyday', recipes: ['spend'], details: { sort_code: '••••34' } }] },
      'GET /agent/balances': { body: [{ account: 'Assets:Bank:Current', balances: { GBP: '48469.17' } }] },
    })
    const accounts = await run('finance_accounts')
    expect(accounts).toMatch(/Assets:Bank:Current \(checking, GBP\)/)
    expect(accounts).toMatch(/sort code ••••34/)
    expect(await run('finance_balances', { account: 'Assets' })).toBe('Assets:Bank:Current  48469.17 GBP')
    expect(service?.requests[1]?.query).toBe('?ledger=personal&account=Assets')
  })

  it('summarises the financial position without presenting reference values as entries', async () => {
    const { run } = await setup({ 'GET /agent/financial-position': { body: {
      base_currency: 'GBP', interval: 'month',
      points: [{ date: '2026-11-26', assets: { original: { GBP: '100' }, reference_value: { number: '100.00', currency: 'GBP' } }, liabilities: { original: { USD: '20' }, reference_value: { number: '16.00', currency: 'GBP' } }, net: { original: { GBP: '100', USD: '-20' }, reference_value: { number: '84.00', currency: 'GBP' } } }],
      valuation: { state: 'fresh', observed_on: '2026-11-25', missing_currencies: [] },
    } } })
    const text = await run('finance_position', { interval: 'month', points: 12 })
    expect(text).toMatch(/Net position: 100 GBP, -20 USD \(approximately 84.00 GBP\)/)
    expect(text).toMatch(/not ledger entries/)
    expect(service?.requests[0]?.query).toBe('?ledger=personal&interval=month&points=12')
  })

  it('amend and delete address the transaction by id', async () => {
    const { run } = await setup({
      'POST /agent/transactions/abc/amend': { status: 201, body: change },
      'POST /agent/transactions/abc/deletion': { status: 201, body: change },
    })
    await run('finance_amend', { id: 'abc', date: '2026-11-25' })
    await run('finance_delete', { id: 'abc', note: 'duplicate' })
    expect(JSON.parse(service?.requests[0]?.body ?? '{}')).toEqual({ ledger: 'personal', date: '2026-11-25' })
    expect(JSON.parse(service?.requests[1]?.body ?? '{}')).toEqual({ ledger: 'personal', note: 'duplicate' })
  })
})
