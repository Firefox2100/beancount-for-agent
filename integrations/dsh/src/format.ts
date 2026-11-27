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

export function statements(items: any[]): string {
  if (items.length === 0) return 'The user has not uploaded any statements.'
  return items.map(item => `${item.id}  ${item.filename}  ${item.account}  ${item.start} to ${item.end}  ${item.lines} lines, ${item.new} new${item.warnings.length > 0 ? `\n  warning: ${item.warnings.join('; ')}` : ''}`).join('\n')
}

export function statement(review: any): string {
  const head = `${review.filename} for ${review.account}, ${review.start} to ${review.end}, ${review.currency}${review.closing_balance == null ? '' : `, closes at ${review.closing_balance}`}`
  const warnings = review.warnings.map((warning: string) => `warning: ${warning}`)
  const lines = review.items.map((line: any) => `${line.number}  ${line.date}  ${line.amount}  ${[line.payee, line.description].filter(Boolean).join(' - ')}${line.status === 'new' ? '' : `  [${line.status.replace('_', ' ')}]`}`)
  const more = review.omitted > 0 ? [`${review.omitted} more lines are not shown`] : []
  return [head, ...warnings, ...(lines.length > 0 ? lines : ['No new lines: everything is already in the ledger.']), ...more].join('\n')
}

export function recurring(items: any[]): string {
  if (items.length === 0) return 'No recurring items are set up. The user can add them in the web interface.'
  return items.map((item) => {
    const head = `${item.id}: ${item.title}, ${item.schedule}, ${item.amount.number} ${item.amount.currency}${item.variable ? ' (varies)' : ''}, ${item.from_account} to ${item.to_account}`
    const open = item.occurrences.map((o: any) => `  ${o.status} ${o.date}`)
    return [head + (item.last_paid == null ? '' : `, last paid ${item.last_paid}`), ...(open.length > 0 ? open : ['  nothing outstanding'])].join('\n')
  }).join('\n')
}

export function recurringSuggestions(items: any[]): string {
  if (items.length === 0) return 'No repeating payments found that are not already covered.'
  return items.map(item => `${item.recurring.title}: about ${item.recurring.amount.number} ${item.recurring.amount.currency} every ${item.recurring.interval === 1 ? '' : `${item.recurring.interval} `}${item.recurring.every}${item.recurring.interval === 1 ? '' : 's'}, ${item.recurring.from_account} to ${item.recurring.to_account}, seen ${item.seen} times, last ${item.last_seen}${item.recurring.variable ? ' (varies)' : ''}`).join('\n')
}

export function incomeStatement(report: any): string {
  const line = (row: any) => `  ${row.account}: ${money(row.totals)}${row.previous == null ? '' : ` (before: ${Object.keys(row.previous).length === 0 ? 'nothing' : money(row.previous)})`}`
  const section = (title: string, rows: any[], total: Record<string, string>) => rows.length === 0 ? [] : [`${title}: ${money(total)}`, ...rows.map(line)]
  const lines = [
    `${report.start} to ${report.end}${report.previous_start == null ? '' : `, compared with ${report.previous_start} to ${report.previous_end}`}`,
    ...section('Income', report.income, report.income_total),
    ...section('Expenses', report.expenses, report.expense_total),
    `Net: ${Object.keys(report.net).length === 0 ? 'nothing recorded' : money(report.net)}${report.savings_rate == null ? '' : `, saved ${report.savings_rate}% of income`}`,
  ]
  if (report.periods.length > 0) {
    lines.push(`By ${report.interval}:`, ...report.periods.map((p: any) => `  ${p.start} to ${p.end}: income ${money(p.income)}, expenses ${money(p.expenses)}, net ${money(p.net)}`))
  }
  return lines.join('\n')
}

export function budgets(items: any[]): string {
  if (items.length === 0) return 'No budgets are set. The user can add them in the web interface.'
  return items.map((item) => {
    const other = Object.entries(item.other_currencies as Record<string, string>).map(([currency, number]) => `${number} ${currency}`)
    const converted = (item.converted ?? []).map((c: any) => `${c.amount} ${c.currency} counted as ${c.value} at about ${c.rate}`)
    return [
      `${item.title} (${item.account}): ${item.state}. ${item.approximate === true ? 'About ' : ''}${item.spent} of ${item.limit.number} ${item.limit.currency} per ${item.every}, ${item.remaining} left, ${item.days_left} days left (${item.start} to ${item.end}).`,
      `  At this pace the period ends at ${item.projected}${item.daily_allowance == null ? '' : `; ${item.daily_allowance} a day is available`}${converted.length > 0 ? `; includes ${converted.join(', ')} (approximate, today's rate)` : ''}${other.length > 0 ? `; also spent ${other.join(', ')} with no rate available, not counted` : ''}.`,
    ].join('\n')
  }).join('\n')
}

export function budgetSuggestions(items: any[]): string {
  if (items.length === 0) return 'No budgets to suggest: every group with regular spending already has one.'
  return items.map(item => `${item.budget.account}: averaged ${item.average} a month over ${item.months} of the last 3 months, so ${item.budget.amount.number} ${item.budget.amount.currency} per month`).join('\n')
}

export function goals(items: any[]): string {
  if (items.length === 0) return 'No savings goals are set. The user can add them in the web interface.'
  return items.map((item) => {
    const other = Object.entries(item.other_currencies as Record<string, string>).map(([currency, number]) => `${number} ${currency}`)
    const parts = [`${item.title}: ${item.state.replace('_', ' ')}. ${item.approximate === true ? 'About ' : ''}${item.saved} saved of ${item.target.number} ${item.target.currency}${item.reached === true ? '' : `, ${item.remaining} to go`}`]
    if (item.by != null) parts.push(`by ${item.by}${item.months_left == null ? '' : ` (${item.months_left} months left)`}`)
    if (item.needed_monthly != null) parts.push(`needs ${item.needed_monthly} a month to arrive on time`)
    if (item.projected != null) parts.push(`reached about ${item.projected} at the planned ${item.planned_monthly.number} a month`)
    if (other.length > 0) parts.push(`${other.join(', ')} held with no rate available, not counted`)
    return `${parts.join('; ')}.`
  }).join('\n')
}

export function checks(items: any[]): string {
  if (items.length === 0) return 'Nothing stands out: no errors, overdrawn accounts, stale balances or likely duplicates.'
  return items.map(item => `[${item.severity}] ${item.title}. ${item.detail}${item.transactions.length > 0 ? ` (transactions: ${item.transactions.join(', ')})` : ''}`).join('\n')
}

export function receipt(reading: any): string {
  const pages = reading.pages.map((page: any) => {
    const source = page.source === 'text' ? 'the PDF\'s own text' : page.source === 'ocr' ? 'OCR' : 'nothing could be read'
    const body = page.text === '' ? (page.note ?? '') : page.text
    const unsure = page.uncertain.length > 0 ? `\nUncertain, check these: ${page.uncertain.join(' | ')}` : ''
    return `Page ${String(page.number)} (${source}):\n${body}${unsure}${page.text !== '' && page.note != null ? `\n${page.note}` : ''}`
  })
  return [`Receipt ${reading.path}. ${reading.notice}`, ...pages].join('\n\n')
}
