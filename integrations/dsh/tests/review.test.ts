import type { Agent } from '@deepseek-ai/dsh-agent'
import type { AskUserQuestionAnswer, AskUserQuestionRequest } from '@deepseek-ai/dsh-user-questions'
import { afterEach, describe, expect, it } from 'vitest'
import { Finance } from '../src/finance.ts'
import type { Change } from '../src/format.ts'
import { approvalDetail, approvalQuestion, decisionOf, reviewRequest } from '../src/review.ts'
import { defaultLedgerState } from '../src/state.ts'
import { reviewTool } from '../src/tools.ts'
import type { BeancountView } from '../src/types.ts'
import { stubService } from './helpers.ts'

let service: Awaited<ReturnType<typeof stubService>> | undefined
afterEach(async () => { await service?.close(); service = undefined })

const purchase: Change = {
  id: 'c1', ledger_id: 'personal', status: 'pending', note: 'Split lunch with Sam', created_at: '2026-11-26T10:00:00Z',
  caller: { actor: 'agent', client_id: 'dsh', session_id: 's' },
  operation: { kind: 'add_transaction', transaction: { date: '2026-11-26', payee: 'Cafe', narration: 'Lunch', postings: [
    { account: 'Expenses:Food', units: { number: '12.50', currency: 'GBP' } },
    { account: 'Assets:Cash', units: { number: '-12.50', currency: 'GBP' } },
  ] } },
} as unknown as Change

const labels = { approve: 'Approve', reject: 'Reject' }

describe('the approval card', () => {
  it('shows the exact postings, the ledger and the note', () => {
    const detail = approvalDetail(purchase)
    expect(detail).toMatch(/Proposal `c1` in ledger `personal`\./)
    expect(detail).toMatch(/\| account \| amount \|/)
    expect(detail).toMatch(/\| `Expenses:Food` \| 12\.50 GBP \|/)
    expect(detail).toMatch(/\| `Assets:Cash` \| -12\.50 GBP \|/)
    expect(detail).toMatch(/> Split lunch with Sam/)
    expect(detail).toMatch(/rejecting leaves the ledger untouched/)
  })

  it('describes every operation kind it knows, and quotes the rest', () => {
    const open = { ...purchase, operation: { kind: 'open_account', account: 'Expenses:Rent', type: 'expense', currencies: ['GBP'], date: '2026-11-26' } } as unknown as Change
    expect(approvalDetail(open)).toMatch(/\*\*Open `Expenses:Rent`\*\* \(expense\) · GBP · 2026-11-26/)
    const batch = { ...purchase, operation: { kind: 'batch', operations: [purchase.operation, { kind: 'close_account', account: 'Assets:Old', date: '2026-11-26' }] } } as unknown as Change
    const both = approvalDetail(batch)
    expect(both).toMatch(/\*\*Close `Assets:Old`\*\* · 2026-11-26/)
    expect(both.match(/\| account \| amount \|/g)?.length).toBe(1)
    const unknown = { ...purchase, operation: { kind: 'something_new' } } as unknown as Change
    expect(approvalDetail(unknown)).toMatch(/```/)
  })

  it('asks about the operation unless the caller words the question', () => {
    expect(approvalQuestion(purchase, undefined)).toBe('Approve "Lunch"?')
    expect(approvalQuestion(purchase, '  Shall I record this?  ')).toBe('Shall I record this?')
    expect(reviewRequest(purchase, labels, undefined)).toMatchObject({
      id: 'review-c1',
      options: [{ label: 'Approve' }, { label: 'Reject' }],
    })
  })

  it('reads the answer as a decision, never as a guess', () => {
    expect(decisionOf({ answers: [{ id: 'review-c1', selected: ['Approve'] }] }, 'review-c1', labels)).toBe('approve')
    expect(decisionOf({ answers: [{ id: 'review-c1', selected: ['Reject'] }] }, 'review-c1', labels)).toBe('reject')
    expect(decisionOf({ answers: [{ id: 'review-c1', selected: [] }] }, 'review-c1', labels)).toBe('dismiss')
    expect(decisionOf({ answers: [{ id: 'another', selected: ['Approve'] }] }, 'review-c1', labels)).toBe('dismiss')
    expect(decisionOf({ answers: [{ id: 'review-c1', selected: [], custom: 'Approve' }] }, 'review-c1', labels)).toBe('approve')
    expect(decisionOf({ answers: [{ id: 'review-c1', selected: [], custom: 'Later' }] }, 'review-c1', labels)).toBe('dismiss')
  })
})

describe('finance_review', () => {
  async function setup(routes: Parameters<typeof stubService>[0], answer: (request: AskUserQuestionRequest) => AskUserQuestionAnswer | undefined) {
    service = await stubService(routes)
    const finance = new Finance(() => ({ baseUrl: service?.url ?? '', tokenRef: 'T', timeoutMs: 2000, guard: true, guardPaths: [] }), async () => 'tok')
    const state: BeancountView = { ...defaultLedgerState(), ledger: 'personal', turns: 0 }
    const asked: AskUserQuestionRequest[] = []
    const tool = reviewTool({
      finance,
      stateOf: () => state,
      ask: async (request) => {
        asked.push(request)
        const reply = answer(request)
        if (reply === undefined) throw new Error('the card was closed')
        return reply
      },
    })
    const agent = { session: { id: 'session-1' } } as unknown as Agent
    const run = (args: Record<string, unknown> = {}) =>
      tool.execute(args, { agent, signal: new AbortController().signal } as never) as Promise<string>
    return { run, asked, requests: () => service?.requests ?? [] }
  }

  it('records the approval the user chose, as the user', async () => {
    const { run, asked, requests } = await setup({
      'GET /agent/proposals': { body: [purchase] },
      'POST /ledgers/personal/changes/c1/approve': { body: { status: 'approved' } },
    }, () => ({ answers: [{ id: 'review-c1', selected: ['批准'] }] }))
    expect(await run({ change: 'c1', question: 'Record lunch?', approve: '批准', reject: '拒绝' })).toBe('Approved: approved. The ledger records it now.')
    const card = asked[0]?.questions[0]
    expect(card?.question).toBe('Record lunch?')
    expect(card?.detail).toMatch(/Expenses:Food/)
    expect(card?.options).toEqual([{ label: '批准' }, { label: '拒绝' }])
    expect(requests()[0]?.query).toBe('?ledger=personal&status=pending')
    expect(requests()[1]?.path).toBe('/ledgers/personal/changes/c1/approve')
    expect(requests()[1]?.headers['x-actor']).toBe('user')
    expect(requests()[1]?.headers['x-client-id']).toBe('dsh-ui')
  })

  it('rejects only when the user says so, and reports a dismissal without touching the ledger', async () => {
    const rejected = await setup({
      'GET /agent/proposals': { body: [purchase] },
      'POST /ledgers/personal/changes/c1/reject': { body: { status: 'rejected' } },
    }, () => ({ answers: [{ id: 'review-c1', selected: ['Reject'] }] }))
    expect(await rejected.run()).toBe('Rejected: rejected. Nothing was recorded.')
    expect(rejected.requests().some(item => item.path.endsWith('/approve'))).toBe(false)

    const dismissed = await setup({ 'GET /agent/proposals': { body: [purchase] } }, () => ({ answers: [{ id: 'review-c1', selected: [] }] }))
    expect(await dismissed.run({ change: 'c1' })).toMatch(/dismissed without an answer/)
    expect(dismissed.requests().length).toBe(1)

    const said = await setup({ 'GET /agent/proposals': { body: [purchase] } }, () => ({ answers: [{ id: 'review-c1', selected: [], custom: 'Ask me tomorrow' }] }))
    expect(await said.run({ change: 'c1' })).toMatch(/answered "Ask me tomorrow"/)
  })

  it('refuses to invent a proposal to review', async () => {
    const { run, asked, requests } = await setup({ 'GET /agent/proposals': { body: [] } }, () => ({ answers: [] }))
    await expect(run()).rejects.toThrow(/no pending proposal to review/)
    await expect(run({ change: 'gone' })).rejects.toThrow(/no pending proposal "gone"/)
    expect(asked).toEqual([])
    expect(requests().length).toBe(2)
  })
})
