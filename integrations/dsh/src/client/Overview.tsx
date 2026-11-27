import { useId } from 'react'
import type { Group } from '../types.ts'
import type { FinancialPosition, Interval, OverviewData, PositionTotal, ReferenceRateStatus } from './api.ts'
import { AllocationChart, PositionChart } from './Charts.tsx'
import type { BeancountKey } from './locales.ts'
import css from './Page.module.css'

type T = (key: BeancountKey, values?: Record<string, string | number>) => string

/** The service reports its own vocabulary; the page shows the same word in the reader's language. */
const RATE_STATE: Record<ReferenceRateStatus['state'], BeancountKey> = {
  disabled: 'rateDisabled',
  empty: 'rateEmpty',
  fresh: 'rateFresh',
  stale: 'rateStale',
  refreshing: 'rateRefreshing',
  unavailable: 'rateUnavailable',
}

const ROOTS = ['Assets', 'Liabilities', 'Equity', 'Income', 'Expenses'] as const

export interface OverviewProps {
  t: T
  data: OverviewData | null
  error: string | null
  busy: boolean
  /** The valuation arrives on its own request, after the accounts, so it is passed separately. */
  position: FinancialPosition | null
  problem: string | null
  onLedger(ledger: string): void
  onGroup(group: Group, enabled: boolean): void
  onRefresh(): void
  onRefreshRates(): void
  interval: Interval
  onInterval(interval: Interval): void
}

const amounts = (values: Record<string, string>): string => Object.entries(values).map(([currency, value]) => `${value} ${currency}`).join(' · ')
const total = (item: PositionTotal | undefined): string => item?.reference_value == null ? '—' : `${item.reference_value.number} ${item.reference_value.currency}`

/** A total is only convertible when every currency in it has a price today. */
const convertible = (held: Record<string, number>, position: FinancialPosition | null): boolean =>
  position !== null && Object.keys(held).every(currency => currency === position.base_currency || position.rates?.[currency] !== undefined)

/** One line for a whole root account: the base-currency total when every currency has a rate, else each currency. */
function summaryOf(held: Record<string, number>, position: FinancialPosition | null): string {
  if (convertible(held, position) && position !== null) {
    const base = position.base_currency
    const value = Object.entries(held).reduce((sum, [currency, number]) => {
      const rate = currency === base ? 1 : Number(position.rates?.[currency] ?? 0)
      return sum + number * rate
    }, 0)
    return `≈ ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${base}`
  }
  return Object.entries(held).map(([currency, number]) => `${number.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${currency}`).join(' · ') || '—'
}

export function Overview({ t, data, error, busy, position, problem, onLedger, onGroup, onRefresh, onRefreshRates, interval, onInterval }: OverviewProps) {
  const page = useId()
  const balances = new Map((data?.balances ?? []).map(item => [item.account, item.balances]))
  const chosen = data?.state.ledger ?? data?.active ?? ''
  const groups = data?.state.groups
  return (
    <div className={css.group} data-testid="beancount-overview">
      <div className={css.bar}>
        <label className={css.inline}>
          {t('ledger')}
          <select className={css.select} value={chosen} disabled={busy || (data?.ledgers.length ?? 0) === 0} onChange={(event) => { onLedger(event.target.value) }}>
            {chosen === '' && <option value="">{t('noLedger')}</option>}
            {data?.ledgers.map(ledger => <option key={ledger.id} value={ledger.id}>{ledger.id}</option>)}
          </select>
        </label>
        <button type="button" className={css.button} disabled={busy} onClick={onRefresh}>{t('refresh')}</button>
      </div>

      {error !== null && <div className={`${css.notice} ${css.error}`} role="alert">{t('unreachable', { message: error })}<div className={css.muted}>{t('openSettings')}</div></div>}
      {data !== null && data.ledgers.length === 0 && error === null && <p className={css.muted}>{t('noLedgers')}</p>}

      {problem !== null && <p className={css.notice} role="status">{t('positionUnavailable', { message: problem })}</p>}

      {position !== null && (() => {
        const latest = position.points.at(-1)
        return <>
          <section className={css.sectionBlock} aria-labelledby={`${page}-position`}>
            <div className={css.sectionHead}>
              <div><h2 id={`${page}-position`} className={css.sectionTitle}>{t('financialPosition')}</h2><p className={css.muted}>{t('referenceIn', { currency: position.base_currency })}</p></div>
              <div className={css.segmented} aria-label={t('period')}>
                <button type="button" aria-pressed={interval === 'week'} onClick={() => { onInterval('week') }}>{t('weekly')}</button>
                <button type="button" aria-pressed={interval === 'month'} onClick={() => { onInterval('month') }}>{t('monthly')}</button>
              </div>
            </div>
            <div className={css.summary}>
              <div><span>{t('assets')}</span><strong>{total(latest?.assets)}</strong></div>
              <div><span>{t('liabilities')}</span><strong>{total(latest?.liabilities)}</strong></div>
              <div><span>{t('netPosition')}</span><strong>{total(latest?.net)}</strong></div>
            </div>
            <PositionChart points={position.points} t={t} />
            <p className={css.rateNote}>
              <span>{t('approximateValues')} · {t(RATE_STATE[position.valuation.state])}{position.valuation.observed_on == null ? '' : ` · ${position.valuation.observed_on}`}{position.valuation.message == null ? '' : ` · ${position.valuation.message}`}</span>
              <button type="button" className={css.linkButton} disabled={busy} onClick={onRefreshRates}>{t('refreshRates')}</button>
            </p>
          </section>
          {position.allocation.length > 0 && <section className={css.sectionBlock} aria-labelledby={`${page}-allocation`}><h2 id={`${page}-allocation`} className={css.sectionTitle}>{t('assetAllocation')}</h2><AllocationChart items={position.allocation} t={t} /></section>}
        </>
      })()}

      {data !== null && data.due.length > 0 && <section className={css.sectionBlock}><h2 className={css.sectionTitle}>{t('needsAttention')}</h2>{data.due.map(item => <div className={css.attentionRow} key={item.account}><span><strong>{item.account.replace(/^Liabilities:/, '')}</strong><small>{item.due_date == null ? t('amountDue') : t('dueOn', { date: item.due_date })}</small></span><span className={css.amount}>{amounts(item.owed)}</span></div>)}</section>}

      {data !== null && data.active !== null && (
        <div className={css.group}>
          <h2 className={css.sectionTitle}>{t('accounts')}</h2>
          {data.accounts.length === 0 && <p className={css.muted}>{t('noAccounts')}</p>}
          {ROOTS.map((root) => {
            const rows = data.accounts.filter(account => account.name === root || account.name.startsWith(`${root}:`))
            if (rows.length === 0) return null
            const held: Record<string, number> = {}
            for (const account of rows) {
              for (const [currency, value] of Object.entries(balances.get(account.name) ?? {})) {
                held[currency] = (held[currency] ?? 0) + Number(value)
              }
            }
            return (
              <details key={root} className={css.accountGroup}>
                <summary className={css.accountSummary}>
                  <span>{root}<span className={css.muted}> · {rows.length}</span></span>
                  <span className={css.amount} title={convertible(held, position) ? t('approximateValues') : undefined}>{summaryOf(held, position)}</span>
                </summary>
                {rows.map((account) => {
                  const amounts = Object.entries(balances.get(account.name) ?? {}).map(([currency, number]) => `${number} ${currency}`).join('\n')
                  const bank = account.details.bank_name
                  return (
                    <div key={account.name} className={css.row}>
                      <span className={css.name}>
                        {account.name.slice(root.length + 1)}
                        {(account.type !== undefined && account.type !== null) || bank !== undefined ? <span className={css.muted}> {[account.type, bank].filter(Boolean).join(' · ')}</span> : null}
                      </span>
                      <span className={css.amount}>{amounts}</span>
                    </div>
                  )
                })}
              </details>
            )
          })}
        </div>
      )}

      {groups !== undefined && (
        <details className={css.disclosure}>
          <summary>{t('tools')}</summary>
          <div className={css.group}>
            <div className={css.muted}>{t('alwaysAvailable')}</div>
            <p className={css.toolNames}>{(data?.tools?.core ?? []).join(' · ')}</p>
            <label className={css.inline}><input type="checkbox" checked={groups.record} disabled={busy} onChange={(event) => { onGroup('record', event.target.checked) }} />{t('toolRecord')}</label>
            <p className={css.toolNames}>{(data?.tools?.record ?? []).join(' · ')}</p>
            <label className={css.inline}><input type="checkbox" checked={groups.analysis} disabled={busy} onChange={(event) => { onGroup('analysis', event.target.checked) }} />{t('toolAnalysis')}</label>
            <p className={css.toolNames}>{(data?.tools?.analysis ?? []).join(' · ')}</p>
          </div>
        </details>
      )}
    </div>
  )
}
