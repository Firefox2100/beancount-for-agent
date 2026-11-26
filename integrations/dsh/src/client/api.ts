import type { BeancountView } from '../types.ts'

export interface AccountRow {
  name: string
  type?: string | null
  currencies: string[]
  description?: string | null
  details: Record<string, string>
}

export interface OverviewData {
  state: BeancountView
  service: string
  ledgers: { id: string }[]
  active: string | null
  accounts: AccountRow[]
  balances: { account: string; balances: Record<string, string> }[]
}

export interface PendingItem {
  ledger: string
  text: string
  change: { id: string; created_at: string; note: string | null; caller: { actor: string; client_id: string | null } }
}

export interface ConnectionStatus {
  ok: boolean
  message?: string
  status?: number | null
  ledgers?: string[]
  credential: { configured: boolean; writable: boolean; source?: string }
}

const PREFIX = '/api/beancount'

/** An answer the page can show: the host's own message when it gave one, else the status. */
async function failure(response: Response): Promise<Error> {
  try {
    const body = await response.json() as { message?: string }
    if (typeof body.message === 'string') return new Error(body.message)
  } catch { /* a body that is not JSON says nothing more */ }
  return new Error(`${response.status}`)
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${PREFIX}${path}`, { credentials: 'same-origin', ...(signal === undefined ? {} : { signal }) })
  if (!response.ok) throw await failure(response)
  return await response.json() as T
}

export async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${PREFIX}${path}`, { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!response.ok) throw await failure(response)
  return await response.json() as T
}
