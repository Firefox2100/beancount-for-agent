import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-connection'
import type {} from '@deepseek-ai/dsh-commands'
import { credentialRef } from '@deepseek-ai/dsh-credentials'
import type {} from '@deepseek-ai/dsh-credentials'
import type {} from '@deepseek-ai/dsh-host-webserver'
import type { Session } from '@deepseek-ai/dsh-session'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type {} from '@deepseek-ai/dsh-session-projection'
import type {} from '@deepseek-ai/dsh-skill'
import type {} from '@deepseek-ai/dsh-storage-domain'
import type {} from '@deepseek-ai/dsh-user-questions'
import { Finance } from './finance.ts'
import { judge } from './guard.ts'
import { createRoutes, type CredentialStatus, type SessionHandle } from './routes.ts'
import { Config, settingsOf, type Accessors } from './settings.ts'
import { applyChange, defaultLedgerState, fold, initialState, isGroup, viewSchema } from './state.ts'
import { ledgerDomain } from './store.ts'
import { financeTools, reviewTool } from './tools.ts'
import type { BeancountView, LedgerState, StateRecord } from './types.ts'

export { Config }

/** The Loader entry id, and the settings namespace. */
export const name = 'beancount'

export const inject = ['tools', 'sessionProjections', 'sessions', 'commands', 'storageDomain']

const SKILL_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'skills', 'finance', 'SKILL.md')
const USAGE = '/finance ledger <id> | tools <record|analysis> <on|off> | status'

/** The skill file's frontmatter and body; ours declares exactly `name` and `description`. */
function parseSkill(source: string): { name: string; description: string; body: string } {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$/.exec(source)
  if (match === null) return { name: 'finance', description: '', body: source.trim() }
  const fields: Record<string, string> = {}
  for (const line of (match[1] ?? '').split(/\r?\n/)) {
    const at = line.indexOf(':')
    if (at > 0) fields[line.slice(0, at).trim()] = line.slice(at + 1).trim()
  }
  return { name: fields.name ?? 'finance', description: fields.description ?? '', body: (match[2] ?? '').trim() }
}

export async function apply(ctx: Context, config: Accessors): Promise<void> {
  const settings = () => settingsOf(config)
  const ref = () => credentialRef(settings().tokenRef)
  const token = async () => (await ctx.get('credentials')?.resolve(ref()))?.value
  const finance = new Finance(settings, token)

  // The ledger and the tool groups are this plugin's own data, so they live in its storage domain. Only the turn
  // counter is projected from the session log, because that is derived from events the session already has.
  const storage = ctx.get('storageDomain')
  if (storage === undefined) throw new Error('this profile has no storage domain: dsh-base provides it')
  const domain = await storage.open(ledgerDomain)
  ctx.effect(() => async () => {
    await domain.close()
  }, 'dsh-beancount: ledger domain')
  const records = domain.table('sessions')

  const projection = await ctx.sessionProjections.register({
    key: 'beancount',
    stateVersion: 1,
    stateSchema: viewSchema,
    init: initialState,
    apply: fold,
    wire: { viewSchema, view: state => state },
  })

  /** A session's state: its stored record, plus what the projection derives from the log. */
  const stateOf = (session: Session): BeancountView => ({
    ...(records.get(String(session.id)) ?? defaultLedgerState()),
    turns: projection.stateOf(session).turns,
  })

  const write = async (session: Session, change: StateRecord): Promise<void> => {
    const key = String(session.id)
    const current: LedgerState = records.get(key) ?? defaultLedgerState()
    await records.put(key, applyChange(current, change))
  }

  for (const { group, definition } of financeTools({
    finance,
    stateOf: agent => stateOf(agent.session),
    update: (agent, change) => write(agent.session, change),
  })) {
    ctx.tools.register(
      definition,
      group === 'core' ? undefined : { when: ({ agent }) => stateOf(agent.session).groups[group] },
    )
  }

  // The card rides DSH's own user-question service, which every dsh-base profile mounts. Without it the tool is not
  // registered at all, and the dock page stays the only way to approve.
  ctx.inject(['userQuestions'], (scoped) => {
    const definition = reviewTool({
      finance,
      stateOf: agent => stateOf(agent.session),
      ask: request => scoped.userQuestions.ask(request),
    })
    scoped.effect(() => scoped.tools.register(definition), 'dsh-beancount: review card')
  })

  ctx.on('tools/pre-execute', async (exec, next) => {
    const current = settings()
    if (!current.guard) return next()
    const reason = judge(exec.name, exec.arguments, { paths: current.guardPaths })
    return reason === undefined ? next() : { kind: 'deny', reason }
  })

  ctx.commands.register({
    name: 'finance',
    description: 'Choose the ledger or switch tool groups for this conversation.',
    input: { hint: 'ledger <id> | tools <record|analysis> <on|off> | status' },
    recordInput: false,
    async handler({ agent, rawInput }) {
      const [verb, first, second] = rawInput.trim().split(/\s+/)
      const state = stateOf(agent.session)
      if (verb === 'status') {
        return { kind: 'success', text: `ledger: ${state.ledger ?? 'none'}; record tools ${state.groups.record ? 'on' : 'off'}; analysis tools ${state.groups.analysis ? 'on' : 'off'}` }
      }
      if (verb === 'ledger' && first !== undefined) {
        await write(agent.session, { ledger: first })
        return { kind: 'success', text: `Working on ledger ${first}.` }
      }
      if (verb === 'tools' && first !== undefined && isGroup(first) && (second === 'on' || second === 'off')) {
        await write(agent.session, { groups: { [first]: second === 'on' } })
        return { kind: 'success', text: `${first} tools ${second}.` }
      }
      return { kind: 'error', text: `usage: ${USAGE}` }
    },
  })

  ctx.inject(['skills'], (skillCtx) => {
    let skill: ReturnType<typeof parseSkill>
    try {
      skill = parseSkill(readFileSync(SKILL_PATH, 'utf8'))
    } catch {
      return
    }
    skillCtx.effect(() => skillCtx.skills.register({ name: skill.name, description: skill.description, content: skill.body, source: 'runtime' }), 'dsh-beancount: skill')
  })

  const credential = {
    async status(): Promise<CredentialStatus> {
      const credentials = ctx.get('credentials')
      if (credentials === undefined) return { configured: false, writable: false }
      const info = await credentials.describe(ref())
      return { configured: info.configured, writable: info.writable, ...(info.source === undefined ? {} : { source: info.source }) }
    },
    async set(value: string): Promise<void> {
      const credentials = ctx.get('credentials')
      if (credentials === undefined) throw new Error('this profile has no credential store')
      await credentials.set(ref(), value)
    },
    async unset(): Promise<void> {
      await ctx.get('credentials')?.unset(ref())
    },
  }

  const routes = createRoutes({
    finance,
    credential,
    session(id): SessionHandle | undefined {
      let session: Session | undefined
      try {
        session = ctx.sessions.get(id as SessionId)
      } catch {
        return undefined
      }
      if (session === undefined) return undefined
      const found = session
      return { state: () => stateOf(found), update: change => write(found, change) }
    },
  })

  ctx.inject(['connection'], (web) => {
    for (const route of routes) {
      web.effect(() => {
        const remove = web.connection.fetch.register({
          path: `/api/beancount${route.path}`,
          methods: [...route.methods],
          requestBody: 'buffered',
          fetch: request => route.handle(request),
        })
        return () => { void remove() }
      }, `dsh-beancount: route ${route.path}`)
    }
  })
}
