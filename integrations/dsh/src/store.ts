/**
 * The session state this plugin owns, kept in DSH's storage domain. The session log is the only source of truth for
 * the conversation, and its plugin records are reserved for DSH's own experimental packages, so plugin-owned data
 * belongs in a domain record instead.
 */
import { defineDomain, domainTable } from '@deepseek-ai/dsh-storage-domain'
import { z } from 'zod'
import type { LedgerState } from './types.ts'

export const stateSchema = z.object({
  ledger: z.string().nullable(),
  groups: z.object({ record: z.boolean(), analysis: z.boolean() }),
})

/** One record per session, keyed by the session id. */
export const ledgerDomain = defineDomain({
  name: 'beancount',
  version: 1,
  layout: 'per-record',
  invalidRecords: 'backup-and-skip',
  tables: { sessions: domainTable<string, LedgerState>(stateSchema) },
})
