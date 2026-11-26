/**
 * The model's tools: native, calling the service's `/agent/*` surface. None of them takes a ledger, because the
 * session holds it, and none approves anything: the person does that in the dock page.
 */
import type { Agent } from '@deepseek-ai/dsh-agent'
import { defineTool, type ParameterSchemaSpec, type ToolDefinition } from '@deepseek-ai/dsh-tools'
import { FinanceError, type Finance } from './finance.ts'
import * as format from './format.ts'
import type { BeancountView, Group, StateRecord } from './types.ts'

export interface ToolDeps {
  finance: Finance
  stateOf(agent: Agent): BeancountView
  update(agent: Agent, change: StateRecord): Promise<void>
}

/** A tool and the switchable group it belongs to; `core` tools are always on. */
export interface GroupedTool {
  group: 'core' | Group
  definition: ToolDefinition
}

const WAITING = 'It is waiting for the user to approve it; nothing is recorded until then. Tell the user what you proposed.'

/** Drop what was not given, so the service applies its own defaults. */
function clean(values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== ''))
}

/** The service's complaints about a missing ledger, restated for the tools that can fix them. */
export function explain(error: unknown): never {
  if (error instanceof FinanceError) {
    const several = /name the ledger: (.+)$/.exec(error.message)
    if (several !== null) throw new FinanceError(`Several ledgers exist (${several[1]}). Call finance_use_ledger to choose the one to work on.`, error.status)
    if (/no ledgers exist yet/.test(error.message)) throw new FinanceError('There are no ledgers yet. Create one with finance_create_ledger.', error.status)
  }
  throw error
}

type Text = { type: 'string' }
const string = (description: string, required = false) => ({ type: 'string', description, ...(required ? { required: true as const } : {}) }) as const satisfies Text & { description: string }

export function financeTools(deps: ToolDeps): GroupedTool[] {
  const { finance } = deps

  /** Define a tool whose result is text, with the agent, its session and its ledger resolved. */
  const textTool = (
    group: GroupedTool['group'],
    name: string,
    description: string,
    parameters: ParameterSchemaSpec,
    run: (call: { args: Record<string, any>; agent: Agent; session: string; ledger: string | undefined; state: BeancountView; signal: AbortSignal }) => Promise<string>,
  ): GroupedTool => ({
    group,
    definition: defineTool({
      name,
      description,
      parameters,
      output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
      async execute(args, exec) {
        const agent = exec.agent
        if (agent === undefined) throw new Error('finance tools work inside a conversation')
        const state = deps.stateOf(agent)
        try {
          return await run({ args: args as Record<string, any>, agent, session: String(agent.session.id), ledger: state.ledger ?? undefined, state, signal: exec.signal })
        } catch (error) {
          return explain(error)
        }
      },
    }),
  })

  const read = (session: string, path: string, query: Record<string, string | number | undefined>, signal: AbortSignal) =>
    finance.agent<any>(session, 'GET', path, { query, signal })
  const write = (session: string, path: string, body: Record<string, unknown>, signal: AbortSignal) =>
    finance.agent<any>(session, 'POST', path, { body: clean(body), signal })
  const proposed = (change: Parameters<typeof format.proposal>[0]) => `${format.proposal(change)}\n\n${WAITING}`

  return [
    textTool('core', 'finance_ledgers', 'List the ledgers and say which one this conversation works on.', {}, async ({ session, state, signal }) =>
      format.ledgers(await read(session, '/agent/ledgers', {}, signal), state.ledger)),

    textTool('core', 'finance_use_ledger', 'Choose the ledger this conversation works on. Every other finance tool then uses it. Call it when the user names a ledger, or when another tool says several exist.', {
      ledger: string('The ledger id, from finance_ledgers.', true),
    }, async ({ args, agent, session, signal }) => {
      const known: { id: string }[] = await read(session, '/agent/ledgers', {}, signal)
      if (!known.some(item => item.id === args.ledger)) throw new FinanceError(`There is no ledger "${String(args.ledger)}". The ledgers are: ${known.map(item => item.id).join(', ') || 'none yet'}.`)
      await deps.update(agent, { ledger: String(args.ledger) })
      return `Now working on ledger ${String(args.ledger)}.`
    }),

    textTool('core', 'finance_create_ledger', 'Create a new ledger. The id becomes its folder name: lowercase letters, digits, - and _. It then becomes the one this conversation works on.', {
      id: string('The ledger id.', true),
      title: string('A readable name.'),
      currencies: { type: 'array', items: { type: 'string' }, description: 'The currencies the ledger is mainly kept in, such as ["GBP"].' },
    }, async ({ args, agent, session, signal }) => {
      const created: { id: string } = await write(session, '/agent/ledgers', { id: args.id, title: args.title, operating_currencies: args.currencies }, signal)
      await deps.update(agent, { ledger: created.id })
      return `Created ledger ${created.id}, now the one this conversation works on.`
    }),

    textTool('core', 'finance_accounts', 'List the accounts with their type, currencies, what they are for and the actions each supports. Call this before recording anything, to get the exact names.', {
      include_closed: { type: 'boolean', description: 'Also list closed accounts.' },
    }, async ({ args, session, ledger, signal }) =>
      format.accounts(await read(session, '/agent/accounts', { ledger, include_closed: args.include_closed === true ? 'true' : undefined }, signal))),

    textTool('core', 'finance_balances', 'Balances per account and currency. Give an account to see it and its sub-accounts, such as "Assets" or "Expenses:Food".', {
      account: string('An account name or a prefix of one.'),
      as_of: string('A date, YYYY-MM-DD. Defaults to today.'),
    }, async ({ args, session, ledger, signal }) =>
      format.balances(await read(session, '/agent/balances', { ledger, account: args.account, as_of: args.as_of }, signal))),

    textTool('core', 'finance_transactions', 'Find recorded transactions by text (payee or narration), account, dates or tag. Each shows its id, for finance_amend and finance_delete.', {
      text: string('Words in the payee or narration.'),
      account: string('An account name or a prefix of one.'),
      start: string('First date, YYYY-MM-DD.'),
      end: string('Last date, YYYY-MM-DD.'),
      tag: string('A tag.'),
      limit: { type: 'integer', description: 'How many to return, at most 100. Defaults to 20.' },
    }, async ({ args, session, ledger, signal }) =>
      format.transactions(await read(session, '/agent/transactions', { ledger, text: args.text, account: args.account, start: args.start, end: args.end, tag: args.tag, limit: args.limit }, signal))),

    textTool('core', 'finance_proposals', 'The changes you proposed in this conversation and whether the user has approved them yet.', {
      status: { type: 'string', enum: ['pending', 'approved', 'rejected', 'withdrawn'], description: 'Defaults to pending.' },
    }, async ({ args, session, ledger, signal }) =>
      format.proposals(await read(session, '/agent/proposals', { ledger, status: args.status }, signal))),

    textTool('record', 'finance_expense', 'Propose an expense paid from a bank, cash, wallet or card account. Account names can be short ("Current", "Food"). Give the amount in the currency it was paid in, as text such as "12.50 GBP".', {
      from_account: string('Where the money came from.', true),
      expense_account: string('What it was spent on.', true),
      amount: string('Such as "12.50 GBP", or just "12.50" when the account holds one currency.', true),
      date: string('YYYY-MM-DD. Defaults to today.'),
      payee: string('Who was paid.'),
      narration: string('A few words about it.'),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/expenses', { ledger, ...args }, signal))),

    textTool('record', 'finance_income', 'Propose money received into an account from an income account, such as interest or a gift. For pay with deductions use finance_recipe with the salary action.', {
      to_account: string('Where the money arrived.', true),
      income_account: string('Where it came from.', true),
      amount: string('Such as "100 GBP".', true),
      date: string('YYYY-MM-DD. Defaults to today.'),
      payee: string('Who paid.'),
      narration: string('A few words about it.'),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/income', { ledger, ...args }, signal))),

    textTool('record', 'finance_transfer', 'Propose moving money between two accounts. Across currencies give `received` (what arrived) or `rate`, using what the bank charged, never a guess.', {
      from_account: string('Where it left.', true),
      to_account: string('Where it arrived.', true),
      amount: string('What left, such as "500 GBP".', true),
      received: string('What arrived, when the currency differs, such as "4800 CNY".'),
      rate: string('Units of the received currency per one unit sent, instead of `received`.'),
      date: string('YYYY-MM-DD. Defaults to today.'),
      narration: string('A few words about it.'),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/transfers', { ledger, ...args }, signal))),

    textTool('record', 'finance_reconcile', 'Propose a balance check: this account held exactly this amount on this date, as a statement shows. It is refused if the books disagree.', {
      account: string('The account.', true),
      amount: string('The balance, such as "1200.50 GBP".', true),
      date: string('YYYY-MM-DD. Defaults to today.'),
      pad_account: string('Where a difference is booked instead of being refused, such as an adjustments expense.'),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/reconciliations', { ledger, ...args }, signal))),

    textTool('record', 'finance_recipes', 'The actions an account supports beyond plain income and expenses (card statements and payments, loans, claims, bills, trades, salary) and the parameters each takes.', {
      account: string('The account.', true),
    }, async ({ args, session, ledger, signal }) =>
      format.recipes(await read(session, '/agent/recipes', { ledger, account: args.account }, signal))),

    textTool('record', 'finance_recipe', 'Propose an account-specific action. `params` follows the parameters shown by finance_recipes for that action.', {
      account: string('The account the action is on.', true),
      recipe: string('The action id from finance_recipes.', true),
      params: { type: 'object', additionalProperties: true, description: 'The action\'s parameters.', required: true },
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/actions', { ledger, account: args.account, recipe: args.recipe, params: args.params ?? {}, note: args.note }, signal))),

    textTool('record', 'finance_open_account', 'Propose opening an account such as Assets:Bank:Current. The type (checking, savings, cash, ewallet, credit_card, loan, receivable, payable, brokerage) decides which actions it gets. It can be used only after the user approves.', {
      account: string('The full name, such as Assets:Bank:Current or Expenses:Food.', true),
      type: string('The account type, for accounts that hold money or debt.'),
      currencies: { type: 'array', items: { type: 'string' }, description: 'The currencies it may hold, such as ["GBP"].' },
      date: string('YYYY-MM-DD it opens. Defaults to today; it must not be later than the first entry on it.'),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/accounts/open', { ledger, ...args }, signal))),

    textTool('record', 'finance_close_account', 'Propose closing an account.', {
      account: string('The account.', true),
      date: string('YYYY-MM-DD. Defaults to today.'),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, '/agent/accounts/close', { ledger, ...args }, signal))),

    textTool('record', 'finance_amend', 'Propose correcting the date, payee, narration or tags of a recorded transaction (find its id with finance_transactions). Send only what changes, and "" for payee to remove it. Amounts and accounts cannot be amended: delete it and record it again.', {
      id: string('The transaction id.', true),
      date: string('The new date, YYYY-MM-DD.'),
      payee: string('The new payee.'),
      narration: string('The new narration.'),
      tags: { type: 'array', items: { type: 'string' }, description: 'The new tags, replacing the old ones.' },
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, `/agent/transactions/${encodeURIComponent(String(args.id))}/amend`, { ledger, date: args.date, payee: args.payee, narration: args.narration, tags: args.tags, note: args.note }, signal))),

    textTool('record', 'finance_delete', 'Propose removing a recorded transaction that was wrong or recorded twice (find its id with finance_transactions).', {
      id: string('The transaction id.', true),
      note: string('Why, for the user who approves it.'),
    }, async ({ args, session, ledger, signal }) =>
      proposed(await write(session, `/agent/transactions/${encodeURIComponent(String(args.id))}/deletion`, { ledger, note: args.note }, signal))),

    textTool('record', 'finance_withdraw', 'Withdraw one of your pending proposals that is no longer wanted.', {
      id: string('The proposal id.', true),
      note: string('Why.'),
    }, async ({ args, session, ledger, signal }) => {
      const change = await write(session, `/agent/proposals/${encodeURIComponent(String(args.id))}/withdraw`, { ledger, note: args.note }, signal)
      return format.proposal(change)
    }),

    textTool('analysis', 'finance_open_items', 'Unsettled reimbursement claims, loans, invoices and bills, with what is still open on each.', {
      account: string('Only this receivable or payable account.'),
    }, async ({ args, session, ledger, signal }) =>
      format.openItems(await read(session, '/agent/open-items', { ledger, account: args.account }, signal))),

    textTool('analysis', 'finance_due', 'Card statements and bills falling due soon: what is owed, the due date and the autopay source. Call this for the current picture rather than relying on earlier results.', {
      within_days: { type: 'integer', description: 'How far ahead to look. Defaults to 14.' },
    }, async ({ args, session, ledger, signal }) =>
      format.due(await read(session, '/agent/due', { ledger, within_days: args.within_days }, signal))),

    textTool('analysis', 'finance_credit_pools', 'Shared credit limits with what is used and what is left.', {}, async ({ session, ledger, signal }) =>
      format.pools(await read(session, '/agent/credit-pools', { ledger }, signal))),
  ]
}
