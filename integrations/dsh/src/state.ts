import type { SessionEvent } from '@deepseek-ai/dsh-session/types'
import { z } from 'zod'
import { GROUPS, type BeancountProjection, type Group, type LedgerState, type StateRecord } from './types.ts'

export const viewSchema = z.object({
  turns: z.number().int().min(0),
})

/** A fresh session: nothing chosen yet, recording tools on, analysis tools off. */
export const defaultLedgerState = (): LedgerState => ({ ledger: null, groups: { record: true, analysis: false } })

export const initialState = (): BeancountProjection => ({ turns: 0 })

/**
 * One committed event folded into the projection. Pure and synchronous, as a projection must be: only the turn
 * counter is derived here, because the ledger and the tool groups live in the storage domain.
 */
export function fold(state: BeancountProjection, event: SessionEvent): BeancountProjection {
  return event.type === 'turn/end' ? { turns: state.turns + 1 } : state
}

/** The stored state with one change applied; the caller writes the result back as a whole record. */
export function applyChange(state: LedgerState, change: StateRecord): LedgerState {
  const groups = { ...state.groups }
  for (const group of GROUPS) {
    const value = change.groups?.[group]
    if (value !== undefined) groups[group] = value
  }
  return { ...state, ...(change.ledger === undefined ? {} : { ledger: change.ledger }), groups }
}

export function isGroup(value: string): value is Group {
  return (GROUPS as readonly string[]).includes(value)
}
