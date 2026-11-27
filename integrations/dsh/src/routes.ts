/**
 * What the dock page asks of the host. These run as the signed-in user, never as the model. Approving from the page
 * happens only here; approving from the conversation goes through `finance_review` (tools.ts), which also resolves the
 * service call as the user and only after they answered its card. Each handler is a plain function of a Request, so it
 * is tested without DSH.
 */
import { describeChange } from '@beancount-mcp/client'
import { FinanceError, type Finance } from './finance.ts'
import type { AccountInfo, Balance, Change, DueItem, FinancialPosition, LedgerInfo } from './format.ts'
import { isGroup } from './state.ts'
import type { BeancountView, StateRecord } from './types.ts'

export interface SessionHandle {
  state(): BeancountView
  update(change: StateRecord): Promise<void>
}

export interface CredentialStatus {
  configured: boolean
  writable: boolean
  source?: string
}

export interface RouteDeps {
  finance: Finance
  session(id: string): SessionHandle | undefined
  credential: {
    status(): Promise<CredentialStatus>
    set(value: string): Promise<void>
    unset(): Promise<void>
  }
}

export interface Route {
  path: string
  methods: readonly ('GET' | 'POST')[]
  handle(request: Request): Promise<Response>
}

export const json = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } })

class BadRequest extends Error {}

async function body(request: Request): Promise<Record<string, unknown>> {
  try {
    const value: unknown = await request.json()
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>
  } catch { /* falls through to the refusal below */ }
  throw new BadRequest('the body must be a JSON object')
}

function text(values: Record<string, unknown>, key: string, required = true): string {
  const value = values[key]
  if (typeof value === 'string' && value !== '') return value
  if (required) throw new BadRequest(`${key} is required`)
  return ''
}

const id = (value: string): string => encodeURIComponent(value)

/** Wrap a handler so a failure becomes a JSON answer the page can show, never a bare 500. */
const guarded = (handler: (request: Request) => Promise<Response>) => async (request: Request): Promise<Response> => {
  try {
    return await handler(request)
  } catch (error) {
    if (error instanceof BadRequest) return json({ message: error.message }, 400)
    if (error instanceof FinanceError) return json({ message: error.message }, error.status !== undefined && error.status >= 400 && error.status < 600 ? error.status : 502)
    return json({ message: error instanceof Error ? error.message : String(error) }, 500)
  }
}

export function createRoutes(deps: RouteDeps): Route[] {
  const { finance } = deps

  const sessionOf = (value: string | null): SessionHandle => {
    const found = value === null ? undefined : deps.session(value)
    if (found === undefined) throw new BadRequest('no such session')
    return found
  }

  const route = (path: string, methods: Route['methods'], handler: (request: Request) => Promise<Response>): Route => ({ path, methods, handle: guarded(handler) })

  return [
    route('/overview', ['GET'], async (request) => {
      const url = new URL(request.url)
      const handle = sessionOf(url.searchParams.get('session'))
      const interval = url.searchParams.get('interval') ?? 'month'
      if (interval !== 'week' && interval !== 'month') throw new BadRequest('interval must be week or month')
      const state = handle.state()
      let ledgers: LedgerInfo[]
      try {
        ledgers = await finance.user<LedgerInfo[]>('GET', '/agent/ledgers')
      } catch (error) {
        return json({ state, service: error instanceof Error ? error.message : String(error), ledgers: [], accounts: [], balances: [], position: null, due: [] })
      }
      const active = state.ledger ?? (ledgers.length === 1 ? ledgers[0]?.id ?? null : null)
      if (active === null) return json({ state, service: 'ok', ledgers, active, accounts: [], balances: [], position: null, due: [] })
      // The reference valuations need an operating currency and a reachable rate provider, and a service older than
      // this route answers 404. Neither may cost the page its accounts and balances, so those two stay required only.
      const [accounts, balances, position, due] = await Promise.all([
        finance.user<AccountInfo[]>('GET', `/ledgers/${id(active)}/accounts`),
        finance.user<Balance[]>('GET', `/ledgers/${id(active)}/balances`),
        finance.user<FinancialPosition>('GET', `/ledgers/${id(active)}/financial-position`, { query: { interval, points: 12 } }).catch(() => null),
        finance.user<DueItem[]>('GET', `/ledgers/${id(active)}/due`, { query: { within_days: 30 } }).catch(() => []),
      ])
      return json({ state, service: 'ok', ledgers, active, accounts: accounts.filter(account => !account.close_date), balances, position, due })
    }),

    route('/ledger', ['POST'], async (request) => {
      const values = await body(request)
      const handle = sessionOf(text(values, 'session'))
      const ledger = text(values, 'ledger')
      const known = await finance.user<LedgerInfo[]>('GET', '/agent/ledgers')
      if (!known.some(item => item.id === ledger)) throw new BadRequest(`there is no ledger ${ledger}`)
      await handle.update({ ledger })
      return json(handle.state())
    }),

    route('/groups', ['POST'], async (request) => {
      const values = await body(request)
      const handle = sessionOf(text(values, 'session'))
      const group = text(values, 'group')
      if (!isGroup(group)) throw new BadRequest(`unknown tool group ${group}`)
      if (typeof values.enabled !== 'boolean') throw new BadRequest('enabled must be true or false')
      await handle.update({ groups: { [group]: values.enabled } })
      return json(handle.state())
    }),

    route('/pending', ['GET'], async () => {
      const ledgers = await finance.user<LedgerInfo[]>('GET', '/agent/ledgers')
      const lists = await Promise.all(ledgers.map(async ({ id: ledger }) => {
        const changes = await finance.user<Change[]>('GET', `/ledgers/${id(ledger)}/changes`, { query: { status: 'pending' } })
        return changes.map(change => ({ ledger, change, text: describeChange(change) }))
      }))
      return json(lists.flat().sort((a, b) => String(a.change.created_at).localeCompare(String(b.change.created_at))))
    }),

    route('/resolve', ['POST'], async (request) => {
      const values = await body(request)
      const verb = text(values, 'verb')
      if (verb !== 'approve' && verb !== 'reject') throw new BadRequest('verb must be approve or reject')
      const note = text(values, 'note', false)
      const result = await finance.user<{ status: string }>('POST', `/ledgers/${id(text(values, 'ledger'))}/changes/${id(text(values, 'id'))}/${verb}`, { body: { note: note === '' ? null : note } })
      return json({ status: result.status })
    }),

    route('/status', ['GET'], async () => {
      const credential = await deps.credential.status()
      try {
        const ledgers = await finance.user<LedgerInfo[]>('GET', '/agent/ledgers')
        const reference = await finance.user<FinancialPosition['valuation']>('GET', '/agent/reference-rates/status').catch(() => undefined)
        return json({ ok: true, ledgers: ledgers.map(item => item.id), credential, ...(reference === undefined ? {} : { reference }) })
      } catch (error) {
        return json({ ok: false, message: error instanceof Error ? error.message : String(error), status: error instanceof FinanceError ? error.status ?? null : null, credential })
      }
    }),

    route('/refresh-rates', ['POST'], async (request) => {
      const values = await body(request)
      return json(await finance.user<FinancialPosition['valuation']>('POST', `/ledgers/${id(text(values, 'ledger'))}/reference-rates/refresh`))
    }),

    route('/credential', ['GET', 'POST'], async (request) => {
      if (request.method === 'GET') return json(await deps.credential.status())
      const values = await body(request)
      const value = typeof values.value === 'string' ? values.value.trim() : ''
      if (value === '') await deps.credential.unset()
      else await deps.credential.set(value)
      return json(await deps.credential.status())
    }),
  ]
}
