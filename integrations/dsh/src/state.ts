import { pluginRecordOf } from '@deepseek-ai/dsh-session'
import type { SessionEvent } from '@deepseek-ai/dsh-session/types'
import { z } from 'zod'
import { GROUPS, type BeancountView, type Group, type StateRecord } from './types.ts'

export const STATE_RECORD = 'plugin:dsh-beancount/state'

export const viewSchema = z.object({
  ledger: z.string().nullable(),
  groups: z.object({ record: z.boolean(), analysis: z.boolean() }),
  turns: z.number().int().min(0),
})

const recordSchema = z.object({
  ledger: z.string().nullable().optional(),
  groups: z.object({ record: z.boolean().optional(), analysis: z.boolean().optional() }).optional(),
})

/** A fresh session: recording on, analysis off until the person asks for it. */
export const initialState = (): BeancountView => ({ ledger: null, groups: { record: true, analysis: false }, turns: 0 })

/**
 * One committed event folded into the state. Pure and synchronous, as a projection must be: the same log always
 * gives the same state, so a reload shows the ledger and tool groups the session had.
 */
export function fold(state: BeancountView, event: SessionEvent): BeancountView {
  if (event.type === 'turn/end') return { ...state, turns: state.turns + 1 }
  const record = pluginRecordOf(event)
  if (record === undefined || record.type !== STATE_RECORD) return state
  const parsed = recordSchema.safeParse(record.data)
  if (!parsed.success) return state
  const change = parsed.data
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

export type { StateRecord }
