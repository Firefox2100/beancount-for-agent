import { useCallback, useEffect, useState } from 'react'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type { Group } from '../types.ts'
import { getJson, postJson, type Interval, type OverviewData, type PendingItem } from './api.ts'
import { Approval } from './Approval.tsx'
import type { BeancountKey } from './locales.ts'
import { Overview } from './Overview.tsx'
import css from './Page.module.css'

/** What the page is handed besides the slot's own props: its session and the page-wide memory of unsent input. */
export interface PageInjected {
  sessionId: SessionId
  /** Unsent input and the chosen tab, kept outside the components so a refresh or a switch never loses them. */
  drafts: Map<string, string>
}

type Props = PropsRuntime<'sidebar.right.pane.tab'> & InjectFace<PageInjected> & PropsLocale<'beancount'>
type Tab = 'overview' | 'approval'

const message = (error: unknown): string => (error instanceof Error ? error.message : String(error))

/**
 * The right-dock page. It reads the session's state from the host, and looks again when the page opens, when a turn
 * ends and when the ledger or a tool group changes. Only the data is replaced, so what is being typed stays.
 */
export function Page({ useProjection, sessionId, drafts, t }: Props) {
  const view = useProjection('beancount')
  const session = String(sessionId)
  const tabKey = `${session}:tab`
  const [tab, setTabState] = useState<Tab>(drafts.get(tabKey) === 'approval' ? 'approval' : 'overview')
  const intervalKey = `${session}:interval`
  const [interval, setIntervalState] = useState<Interval>(drafts.get(intervalKey) === 'week' ? 'week' : 'month')
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [pending, setPending] = useState<PendingItem[] | null>(null)
  const [overviewError, setOverviewError] = useState<string | null>(null)
  const [pendingError, setPendingError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [nonce, setNonce] = useState(0)

  const setTab = (next: Tab) => { drafts.set(tabKey, next); setTabState(next) }
  const refresh = useCallback(() => { setNonce(value => value + 1) }, [])

  // The projection carries the turn counter; the ledger and the tool groups come back with the overview, which is
  // what the page already reads, so a mutation just asks for it again.
  const turns = view?.turns ?? 0
  useEffect(() => {
    const controller = new AbortController()
    void (async () => {
      const [overviewResult, pendingResult] = await Promise.allSettled([
        getJson<OverviewData>(`/overview?session=${encodeURIComponent(session)}&interval=${interval}`, controller.signal),
        getJson<PendingItem[]>('/pending', controller.signal),
      ])
      if (controller.signal.aborted) return
      if (overviewResult.status === 'fulfilled') { setOverview(overviewResult.value); setOverviewError(null) } else setOverviewError(message(overviewResult.reason))
      if (pendingResult.status === 'fulfilled') { setPending(pendingResult.value); setPendingError(null) } else setPendingError(message(pendingResult.reason))
    })()
    return () => { controller.abort() }
  }, [session, turns, nonce, interval])

  const change = async (run: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await run()
      setNonce(value => value + 1)
    } catch (error) { setOverviewError(message(error)) } finally { setBusy(false) }
  }

  const count = pending?.length ?? 0
  return (
    <div className={css.page} data-testid="beancount-page">
      <div className={css.bar}>
        <div className={css.tabs} role="tablist" aria-label={t('tabList')}>
          <button type="button" role="tab" aria-selected={tab === 'overview'} className={css.tab} onClick={() => { setTab('overview') }}>{t('tabOverview')}</button>
          <button type="button" role="tab" aria-selected={tab === 'approval'} className={css.tab} onClick={() => { setTab('approval') }}>
            {t('tabApproval')}{count > 0 && <span className={css.badge}>{count}</span>}
          </button>
        </div>
      </div>
      {tab === 'overview' && (
        <Overview
          t={t}
          data={overview}
          error={overviewError}
          busy={busy}
          onRefresh={refresh}
          interval={interval}
          onInterval={(next) => { drafts.set(intervalKey, next); setIntervalState(next) }}
          onLedger={(next) => { void change(() => postJson('/ledger', { session, ledger: next })) }}
          onGroup={(group: Group, enabled) => { void change(() => postJson('/groups', { session, group, enabled })) }}
          onRefreshRates={() => {
            const ledger = overview?.state.ledger ?? overview?.active ?? null
            if (ledger === null) return
            void change(() => postJson('/refresh-rates', { ledger }))
          }}
        />
      )}
      {tab === 'approval' && (
        <Approval
          t={t}
          items={pending}
          error={pendingError}
          drafts={drafts}
          sessionKey={session}
          onResolve={async (item, verb, note) => {
            await postJson('/resolve', { ledger: item.ledger, id: item.change.id, verb, note })
            refresh()
          }}
        />
      )}
    </div>
  )
}

export type { BeancountKey }
