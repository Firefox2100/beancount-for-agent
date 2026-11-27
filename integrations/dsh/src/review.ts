/**
 * The card that asks the person to approve one proposal, in the conversation. The host half of DSH's user-question
 * service renders it, so the plugin ships no UI of its own here; this module only decides what the card says and what
 * the answer means. `finance_review` (tools.ts) drives it, and the person's own answer is the only thing that can
 * approve: the model cannot answer its own question.
 */
import { describeChange } from '@beancount-mcp/client'
import type { AskUserQuestionAnswer, AskUserQuestionItem } from '@deepseek-ai/dsh-user-questions'
import type { Amount, Change, Posting } from './format.ts'

/** The languages the harness ships. */
export const LANGUAGES = ['en', 'zh', 'ja', 'es', 'fr', 'de', 'ru', 'pt'] as const
export type Language = (typeof LANGUAGES)[number]

/**
 * What the card says. It is fixed by this plugin and never by the model: the question and the two labels are the
 * boundary between a proposal and the ledger, so the agent that wrote the proposal cannot word them. The model may
 * only choose among these languages, and add a remark that is shown as its own.
 */
export interface CardText {
  approve: string
  reject: string
  question: string
  says: string
}

export const CARD_TEXT: Record<Language, CardText> = {
  en: { approve: 'Approve', reject: 'Reject', question: 'Approve this change?', says: 'The assistant says' },
  zh: { approve: '批准', reject: '拒绝', question: '批准这项更改？', says: '助手的说明' },
  ja: { approve: '承認', reject: '却下', question: 'この変更を承認しますか？', says: 'アシスタントのコメント' },
  es: { approve: 'Aprobar', reject: 'Rechazar', question: '¿Aprobar este cambio?', says: 'El asistente dice' },
  fr: { approve: 'Approuver', reject: 'Refuser', question: 'Approuver cette modification ?', says: 'L\'assistant dit' },
  de: { approve: 'Genehmigen', reject: 'Ablehnen', question: 'Diese Änderung genehmigen?', says: 'Der Assistent sagt' },
  ru: { approve: 'Одобрить', reject: 'Отклонить', question: 'Одобрить это изменение?', says: 'Ассистент сообщает' },
  pt: { approve: 'Aprovar', reject: 'Rejeitar', question: 'Aprovar esta alteração?', says: 'O assistente diz' },
}

/** The card's text in a language, or English for one this plugin does not have. */
export const cardText = (language: string | undefined): CardText =>
  CARD_TEXT[(LANGUAGES as readonly string[]).includes(language ?? '') ? (language as Language) : 'en']

/** The longest remark of the assistant a card quotes. */
const SAYS_LIMIT = 300

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

/** The assistant's remark as one quoted, plainly attributed line, so it cannot pass for the card's own words. */
function remark(says: string | undefined, text: CardText): string[] {
  const clean = (says ?? '').replace(/[`>*_]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, SAYS_LIMIT)
  return clean === '' ? [] : ['', `${text.says}: \u201c${clean}\u201d`]
}

/** The card's body: what will be recorded, in markdown, never a paraphrase of the amount. */
export function approvalDetail(change: Change, says?: string, text: CardText = CARD_TEXT.en): string {
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
  lines.push(...remark(says, text))
  lines.push('', 'Approving records exactly this; rejecting leaves the ledger untouched.')
  return lines.join('\n')
}

/** The question id, so the answer can be matched to this card alone. */
export const reviewId = (change: Change): string => `review-${change.id}`

/** The one question DSH renders as a card: the detail above, and the two choices. Every word of it is fixed here. */
export function reviewRequest(change: Change, language: string | undefined, says?: string): AskUserQuestionItem {
  const text = cardText(language)
  return {
    id: reviewId(change),
    question: text.question,
    detail: approvalDetail(change, says, text),
    options: [{ label: text.approve }, { label: text.reject }],
  }
}

/** Read the person's answer: their chosen label, their own words, or a dismissal. */
export function decisionOf(answer: AskUserQuestionAnswer, id: string, language: string | undefined): Decision {
  const labels = cardText(language)
  const item = answer.answers.find(entry => entry.id === id)
  if (item === undefined) return 'dismiss'
  const chosen = item.custom !== undefined && item.custom.trim() !== '' ? item.custom.trim() : item.selected[0]
  if (chosen === labels.approve) return 'approve'
  if (chosen === labels.reject) return 'reject'
  return 'dismiss'
}
