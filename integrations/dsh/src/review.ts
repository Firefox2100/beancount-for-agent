/**
 * The card that asks the person to approve one proposal, in the conversation. The host half of DSH's user-question
 * service renders it, so the plugin ships no UI of its own here; this module only decides what the card says and what
 * the answer means. `finance_review` (tools.ts) drives it, and the person's own answer is the only thing that can
 * approve: the model cannot answer its own question.
 */
import { describeChange } from '@beancount-mcp/client'
import type { AskUserQuestionAnswer, AskUserQuestionItem } from '@deepseek-ai/dsh-user-questions'
import type { Amount, Change, Posting } from './format.ts'

/** The two choices, in the language the person writes in. */
export interface ApprovalLabels {
  approve: string
  reject: string
}

/** What the person decided, read from their answer. */
export type Decision = 'approve' | 'reject' | 'dismiss'

/** The shape of a proposed operation, as far as this card needs to read it. */
interface Operation {
  kind?: string
  transaction?: { date?: string; payee?: string | null; narration?: string; postings?: Posting[] }
  operations?: Operation[]
  id?: string
  account?: string
  type?: string | null
  amount?: Amount
  date?: string
  currencies?: string[]
}

const operationOf = (change: Change): Operation => (change as unknown as { operation?: Operation }).operation ?? {}

const money = (amount: Amount | null | undefined): string =>
  amount === null || amount === undefined ? 'the rest' : `${amount.number} ${amount.currency}`

const units = (posting: Posting): string => {
  if (posting.units === null || posting.units === undefined) return 'the rest'
  const price = posting.price === null || posting.price === undefined ? '' : ` @ ${posting.price.number} ${posting.price.currency}`
  return `${posting.units.number} ${posting.units.currency}${price}`
}

/** One transaction, as a table of exactly the postings the service will record. */
function transactionTable(operation: Operation, verb: string): string[] {
  const transaction = operation.transaction ?? {}
  const head = [transaction.date, transaction.payee, transaction.narration].filter(Boolean).join(' · ')
  const postings = transaction.postings ?? []
  return [
    `**${verb}${head === '' ? '' : ` ${head}`}**`,
    '',
    '| account | amount |',
    '| --- | --- |',
    ...postings.map(posting => `| \`${posting.account}\` | ${units(posting)} |`),
  ]
}

/** The markdown body of one operation; anything this card does not know is quoted verbatim instead. */
function bodyOf(operation: Operation, change: Change): string[] {
  switch (operation.kind) {
    case 'add_transaction':
      return transactionTable(operation, 'Add')
    case 'update_transaction':
      return transactionTable(operation, operation.id === undefined ? 'Update' : `Update \`${operation.id}\``)
    case 'open_account': {
      const head = [`**Open \`${operation.account ?? ''}\`**`]
      if (operation.type) head.push(` (${operation.type})`)
      if (operation.currencies !== undefined && operation.currencies.length > 0) head.push(` · ${operation.currencies.join('/')}`)
      if (operation.date !== undefined) head.push(` · ${operation.date}`)
      return [head.join('')]
    }
    case 'close_account':
      return [`**Close \`${operation.account ?? ''}\`**${operation.date === undefined ? '' : ` · ${operation.date}`}`]
    case 'reconcile':
      return [`**Reconcile \`${operation.account ?? ''}\` to ${money(operation.amount)} on ${operation.date ?? ''}**`]
    default:
      return ['```', describeChange(change), '```']
  }
}

/** The card's body: what will be recorded, in markdown, never a paraphrase of the amount. */
export function approvalDetail(change: Change): string {
  const operation = operationOf(change)
  const lines: string[] = [`Proposal \`${change.id}\` in ledger \`${change.ledger_id}\`.`]
  if (operation.kind === 'batch') {
    const members = operation.operations ?? []
    if (members.length === 0) lines.push('', ...bodyOf(operation, change))
    for (const [index, member] of members.entries()) {
      if (index > 0) lines.push('')
      lines.push(...bodyOf(member, change))
    }
  } else {
    lines.push('', ...bodyOf(operation, change))
  }
  if (change.note) lines.push('', `> ${change.note}`)
  lines.push('', 'Approving records exactly this; rejecting leaves the ledger untouched.')
  return lines.join('\n')
}

/** The question line: the model's own words when it gives any, otherwise the operation itself. */
export function approvalQuestion(change: Change, asked: string | undefined): string {
  if (asked !== undefined && asked.trim() !== '') return asked.trim()
  const narration = operationOf(change).transaction?.narration
  return narration === undefined || narration === '' ? 'Approve this change?' : `Approve "${narration}"?`
}

/** The question id, so the answer can be matched to this card alone. */
export const reviewId = (change: Change): string => `review-${change.id}`

/** The one question DSH renders as a card: the detail above, and the two choices. */
export function reviewRequest(change: Change, labels: ApprovalLabels, question: string | undefined): AskUserQuestionItem {
  return {
    id: reviewId(change),
    question: approvalQuestion(change, question),
    detail: approvalDetail(change),
    options: [{ label: labels.approve }, { label: labels.reject }],
  }
}

/** Read the person's answer: their chosen label, their own words, or a dismissal. */
export function decisionOf(answer: AskUserQuestionAnswer, id: string, labels: ApprovalLabels): Decision {
  const item = answer.answers.find(entry => entry.id === id)
  if (item === undefined) return 'dismiss'
  const chosen = item.custom !== undefined && item.custom.trim() !== '' ? item.custom.trim() : item.selected[0]
  if (chosen === labels.approve) return 'approve'
  if (chosen === labels.reject) return 'reject'
  return 'dismiss'
}
