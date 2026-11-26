import type {} from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-session-projection/types'

/** Tool groups a person can switch per session. The core read tools are always there. */
export const GROUPS = ['record', 'analysis'] as const
export type Group = (typeof GROUPS)[number]

/** The part of a session this plugin owns: the ledger its tools work on, and which optional groups are on. */
export interface LedgerState {
  /** The ledger every tool of this session works on; null until one is chosen. */
  ledger: string | null
  /** Which optional tool groups are on. */
  groups: Record<Group, boolean>
}

/** What the dock page reads: the owned state plus the turn counter derived from the session log. */
export interface BeancountView extends LedgerState {
  /** How many turns have ended, so the page knows when to look again. */
  turns: number
}

/** One change to the owned state, applied and stored as a whole. */
export interface StateRecord {
  ledger?: string | null
  groups?: Partial<Record<Group, boolean>>
}

/** What the session projection keeps: only what is derived from existing session events. */
export interface BeancountProjection {
  /** How many turns have ended in this session. */
  turns: number
}

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    beancount: BeancountProjection
  }
}
