import { useState } from 'react'
import type { PendingItem } from './api.ts'
import css from './Page.module.css'

type T = (key: any, values?: Record<string, string | number>) => string

export interface ApprovalProps {
  t: T
  items: PendingItem[] | null
  error: string | null
  /** Unsent notes, kept outside the component so a refresh never loses them. */
  drafts: Map<string, string>
  sessionKey: string
  onResolve(item: PendingItem, verb: 'approve' | 'reject', note: string): Promise<void>
}

function Card({ t, item, drafts, sessionKey, onResolve }: Omit<ApprovalProps, 'items' | 'error'> & { item: PendingItem }) {
  const key = `${sessionKey}:note:${item.change.id}`
  const [note, setNote] = useState(drafts.get(key) ?? '')
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const who = [item.change.caller.actor, item.change.caller.client_id].filter(Boolean).join('/')
  const act = async (verb: 'approve' | 'reject') => {
    setBusy(verb)
    setProblem(null)
    try {
      await onResolve(item, verb, note)
      drafts.delete(key)
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error))
    } finally {
      setBusy(null)
    }
  }
  return (
    <div className={css.card} data-testid={`pending-${item.change.id}`}>
      <div className={css.muted}>{item.ledger} · {item.change.id.slice(0, 8)} · {t('from', { who })} · {item.change.created_at.slice(0, 16).replace('T', ' ')}</div>
      {item.change.note !== null && <div>“{item.change.note}”</div>}
      <pre className={css.postings}>{item.text.split('\n').slice(2).join('\n')}</pre>
      <div className={css.actions}>
        <input
          className={`${css.input} ${css.grow}`}
          placeholder={t('note')}
          value={note}
          disabled={busy !== null}
          onChange={(event) => { drafts.set(key, event.target.value); setNote(event.target.value) }}
        />
        <button type="button" className={`${css.button} ${css.primary}`} disabled={busy !== null} onClick={() => { void act('approve') }}>{busy === 'approve' ? t('working') : t('approve')}</button>
        <button type="button" className={css.button} disabled={busy !== null} onClick={() => { void act('reject') }}>{busy === 'reject' ? t('working') : t('reject')}</button>
      </div>
      {problem !== null && <div className={css.error} role="alert">{t('failed', { message: problem })}</div>}
    </div>
  )
}

export function Approval({ t, items, error, drafts, sessionKey, onResolve }: ApprovalProps) {
  return (
    <div className={css.group} data-testid="beancount-approval">
      <div className={css.heading}>{t('pending')}</div>
      {error !== null && <div className={`${css.notice} ${css.error}`} role="alert">{t('unreachable', { message: error })}</div>}
      {items !== null && items.length === 0 && error === null && <p className={css.muted}>{t('nothingPending')}</p>}
      {items?.map(item => <Card key={`${item.ledger}/${item.change.id}`} t={t} item={item} drafts={drafts} sessionKey={sessionKey} onResolve={onResolve} />)}
    </div>
  )
}
