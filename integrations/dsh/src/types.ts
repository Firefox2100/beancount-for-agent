import type {} from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-session-projection/types'

/** Tool groups a person can switch per session. The core read tools are always there. */
export const GROUPS = ['record', 'analysis'] as const
export type Group = (typeof GROUPS)[number]

/** What the host keeps per session, and what the dock page may read. */
export interface BeancountView {
  /** The ledger every tool of this session works on; null until one is chosen. */
  ledger: string | null
  /** Which optional tool groups are on. */
  groups: Record<Group, boolean>
  /** How many turns have ended, so the page knows when to look again. */
  turns: number
}

/** One change to that state, as it is written to the session log. */
export interface StateRecord {
  ledger?: string | null
  groups?: Partial<Record<Group, boolean>>
}

declare module '@deepseek-ai/dsh-session/types' {
  interface PluginRecordMap {
    'plugin:dsh-beancount/state': StateRecord
  }
}

declare module '@deepseek-ai/dsh-session-projection/types' {
  interface SessionProjectionMap {
    beancount: BeancountView
  }
}
