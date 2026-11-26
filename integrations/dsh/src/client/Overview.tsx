import type { Group } from '../types.ts'
import type { OverviewData } from './api.ts'
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
}

export function Overview({ t, data, error, busy, onLedger, onGroup, onRefresh }: OverviewProps) {
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

      {groups !== undefined && (
        <div className={css.group}>
          <div className={css.heading}>{t('tools')}</div>
          <label className={css.inline}><input type="checkbox" checked={groups.record} disabled={busy} onChange={(event) => { onGroup('record', event.target.checked) }} />{t('toolRecord')}</label>
          <label className={css.inline}><input type="checkbox" checked={groups.analysis} disabled={busy} onChange={(event) => { onGroup('analysis', event.target.checked) }} />{t('toolAnalysis')}</label>
        </div>
      )}

      {data !== null && data.active !== null && (
        <div className={css.group}>
          <div className={css.heading}>{t('accounts')}</div>
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
    </div>
  )
}
