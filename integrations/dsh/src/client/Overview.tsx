import type { Group } from '../types.ts'
import type { Interval, OverviewData, PositionTotal } from './api.ts'
import { AllocationChart, PositionChart } from './Charts.tsx'
import css from './Page.module.css'

type T = (key: any, values?: Record<string, string | number>) => string

const ROOTS = ['Assets', 'Liabilities', 'Equity', 'Income', 'Expenses'] as const

export interface OverviewProps {
  t: T
  data: OverviewData | null
  error: string | null
  busy: boolean
  onLedger(ledger: string): void
  onGroup(group: Group, enabled: boolean): void
  onRefresh(): void
  interval: Interval
  onInterval(interval: Interval): void
}

const amounts = (values: Record<string, string>): string => Object.entries(values).map(([currency, value]) => `${value} ${currency}`).join(' · ')
const total = (item: PositionTotal | undefined): string => item?.reference_value == null ? '—' : `${item.reference_value.number} ${item.reference_value.currency}`

export function Overview({ t, data, error, busy, onLedger, onGroup, onRefresh, interval, onInterval }: OverviewProps) {
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

      {data?.position !== null && data?.position !== undefined && (() => {
        const latest = data.position.points.at(-1)
        return <>
          <section className={css.sectionBlock} aria-labelledby="financial-position-title">
            <div className={css.sectionHead}>
              <div><h2 id="financial-position-title" className={css.sectionTitle}>{t('financialPosition')}</h2><p className={css.muted}>{t('referenceIn', { currency: data.position.base_currency })}</p></div>
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
            <PositionChart points={data.position.points} t={t} />
            <p className={css.rateNote}>{t('approximateValues')} · {t('rateState', { state: data.position.valuation.state })}{data.position.valuation.observed_on == null ? '' : ` · ${data.position.valuation.observed_on}`}</p>
          </section>
          {data.position.allocation.length > 0 && <section className={css.sectionBlock} aria-labelledby="allocation-title"><h2 id="allocation-title" className={css.sectionTitle}>{t('assetAllocation')}</h2><AllocationChart items={data.position.allocation} t={t} /></section>}
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
            return (
              <div key={root} className={css.group}>
                <div className={css.muted}>{root}</div>
                {rows.map((account) => {
                  const held = balances.get(account.name) ?? {}
                  const amounts = Object.entries(held).map(([currency, number]) => `${number} ${currency}`).join('\n')
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
              </div>
            )
          })}
        </div>
      )}

      {groups !== undefined && <details className={css.disclosure}><summary>{t('tools')}</summary><div className={css.group}><label className={css.inline}><input type="checkbox" checked={groups.record} disabled={busy} onChange={(event) => { onGroup('record', event.target.checked) }} />{t('toolRecord')}</label><label className={css.inline}><input type="checkbox" checked={groups.analysis} disabled={busy} onChange={(event) => { onGroup('analysis', event.target.checked) }} />{t('toolAnalysis')}</label></div></details>}
    </div>
  )
}
