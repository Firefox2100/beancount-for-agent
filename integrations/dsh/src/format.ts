/** Plain-text renderings of what the service returns, short enough for a small model to read and quote. */
import { describeChange } from '@beancount-mcp/client'

export interface Amount { number: string; currency: string }
export interface AccountInfo {
  name: string
  type?: string | null
  currencies: string[]
  description?: string | null
  recipes: string[]
  details: Record<string, string>
  close_date?: string | null
}
export interface Balance { account: string; balances: Record<string, string> }
export interface Posting { account: string; units?: Amount | null; price?: Amount | null }
export interface Transaction { id: string; date: string; payee?: string | null; narration: string; postings: Posting[] }
export interface Recipe { id: string; title: string; description: string; params_schema: { properties?: Record<string, unknown>; required?: string[] } }
export interface OpenItems { account: string; items: { link: string; opened: string; payee?: string | null; narration: string; balances: Record<string, string> }[]; unlinked?: Record<string, string> }
export interface DueItem { account: string; due_date?: string | null; owed: Record<string, string>; unbilled?: Record<string, string>; autopay_from?: string | null; next_statement?: string | null }
export interface PoolStatus { name: string; limit: Amount; used: string; available: string; unconverted?: Record<string, string> }
export interface LedgerInfo { id: string; version: string }
export interface FinancialPosition {
  base_currency: string
  interval: 'week' | 'month'
  points: Array<{
    date: string
    assets: { original: Record<string, string>; reference_value?: Amount | null }
    liabilities: { original: Record<string, string>; reference_value?: Amount | null }
    net: { original: Record<string, string>; reference_value?: Amount | null }
  }>
  valuation: { state: string; observed_on?: string | null; missing_currencies?: string[] }
}
export type Change = Parameters<typeof describeChange>[0]

const money = (amounts: Record<string, string>): string =>
  Object.entries(amounts).map(([currency, number]) => `${number} ${currency}`).join(', ')

export function ledgers(items: LedgerInfo[], active: string | null): string {
  if (items.length === 0) return 'There are no ledgers yet.'
  return items.map(item => `${item.id}${item.id === active ? ' (active)' : ''}`).join('\n')
}

export function accounts(items: AccountInfo[]): string {
  if (items.length === 0) return 'No accounts yet.'
  return items.map((account) => {
    const head = [account.type, account.currencies.join('/')].filter(Boolean).join(', ')
    const bank = Object.entries(account.details).map(([key, value]) => `${key.replace(/_/g, ' ')} ${value}`).join(', ')
    const lines = [`${account.name}${head === '' ? '' : ` (${head})`}`]
    if (account.description) lines.push(`  ${account.description}`)
    if (bank !== '') lines.push(`  ${bank}`)
    if (account.recipes.length > 0) lines.push(`  recipes: ${account.recipes.join(', ')}`)
    return lines.join('\n')
  }).join('\n')
}

export function balances(items: Balance[]): string {
  if (items.length === 0) return 'Nothing is recorded yet.'
  return items.map(item => `${item.account}  ${money(item.balances)}`).join('\n')
}

export function financialPosition(item: FinancialPosition): string {
  const latest = item.points.at(-1)
  if (latest === undefined) return 'No financial position is available yet.'
  const value = (total: FinancialPosition['points'][number]['assets']): string => {
    const original = money(total.original)
    const reference = total.reference_value
    return reference === null || reference === undefined
      ? original
      : `${original} (approximately ${reference.number} ${reference.currency})`
  }
  const missing = item.valuation.missing_currencies ?? []
  const rate = item.valuation.state === 'disabled'
    ? 'Reference conversion is disabled.'
    : `Reference rates: ${item.valuation.state}${item.valuation.observed_on == null ? '' : `, observed ${item.valuation.observed_on}`}${missing.length === 0 ? '' : `; missing ${missing.join(', ')}`}.`
  return [
    `Financial position on ${latest.date}:`,
    `Assets: ${value(latest.assets)}`,
    `Liabilities: ${value(latest.liabilities)}`,
    `Net position: ${value(latest.net)}`,
    rate,
    'Reference values are approximate and are not ledger entries.',
  ].join('\n')
}

export function transactions(items: Transaction[]): string {
  if (items.length === 0) return 'No transactions match.'
  return items.map((item) => {
    const head = [item.date, item.payee, item.narration].filter(Boolean).join(' ')
    const postings = item.postings.map((posting) => {
      const units = posting.units === null || posting.units === undefined ? '' : `${posting.units.number} ${posting.units.currency}`
      const price = posting.price === null || posting.price === undefined ? '' : ` @ ${posting.price.number} ${posting.price.currency}`
      return `    ${posting.account}  ${units}${price}`.trimEnd()
    })
    return [`${head}  [${item.id}]`, ...postings].join('\n')
  }).join('\n')
}

export function recipes(items: Recipe[]): string {
  if (items.length === 0) return 'No actions are available for this account.'
  return items.map((recipe) => {
    const properties = recipe.params_schema.properties ?? {}
    const required = new Set(recipe.params_schema.required ?? [])
    const params = Object.entries(properties).map(([name, schema]) => {
      const description = schema !== null && typeof schema === 'object' && 'description' in schema ? ` - ${String(schema.description)}` : ''
      return `    ${name}${required.has(name) ? ' (required)' : ''}${description}`
    })
    return [`${recipe.id}: ${recipe.description}`, ...params].join('\n')
  }).join('\n')
}

export function openItems(groups: OpenItems[]): string {
  const lines = groups.flatMap((group) => {
    const items = group.items.map(item => `  ${item.link}: ${[item.opened, item.payee, item.narration].filter(Boolean).join(' ')} - ${money(item.balances)} still open`)
    const loose = group.unlinked !== undefined && Object.keys(group.unlinked).length > 0 ? [`  not linked to a claim: ${money(group.unlinked)}`] : []
    return items.length + loose.length === 0 ? [] : [group.account, ...items, ...loose]
  })
  return lines.length === 0 ? 'Nothing is open.' : lines.join('\n')
}

export function due(items: DueItem[]): string {
  if (items.length === 0) return 'Nothing is due in that time.'
  return items.map((item) => {
    const parts = [`${item.account}: owes ${money(item.owed)}`]
    if (item.due_date) parts.push(`due ${item.due_date}`)
    if (item.next_statement) parts.push(`next statement ${item.next_statement}`)
    if (item.autopay_from) parts.push(`autopay from ${item.autopay_from}`)
    return parts.join(', ')
  }).join('\n')
}

export function pools(items: PoolStatus[]): string {
  if (items.length === 0) return 'No credit pools are set up.'
  return items.map((pool) => {
    const currency = pool.limit.currency
    const parts = [pool.name, `limit ${pool.limit.number} ${currency}`, `used ${pool.used} ${currency}`, `available ${pool.available} ${currency}`]
    if (pool.unconverted && Object.keys(pool.unconverted).length > 0) parts.push(`not counted (no price): ${money(pool.unconverted)}`)
    return parts.join(', ')
  }).join('\n')
}

/** One proposal, as the person will review it. */
export function proposal(change: Change): string {
  return describeChange(change)
}

export function proposals(items: Change[]): string {
  return items.length === 0 ? 'No proposals.' : items.map(proposal).join('\n\n')
}
