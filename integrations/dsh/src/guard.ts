/**
 * Keeps the model's own file and shell tools away from the ledger and the credentials. The ledger is reached only
 * through the finance tools. A blunt text check: a false refusal costs a retry, a miss costs the boundary.
 */
export interface GuardOptions {
  /** Extra paths to protect, such as the folder the ledgers live in. */
  paths: readonly string[]
}

/** Tool names that belong to this plugin; their arguments are the plugin's own business. */
const OWN_PREFIX = 'finance_'

/**
 * The argument names that carry prose: a document being written, text being replaced, a message. Everything else is
 * searched, including argument names this guard has never heard of, so a tool with an unusual name for its command or
 * its target (`args`, `argv`, `source`, `destination`, `input`) is judged like any other. Only prose is exempt, so a
 * tool that writes a document can quote a ledger file name or a setting without being refused.
 */
const PROSE = new Set([
  'content', 'contents', 'text', 'old_string', 'new_string', 'old_str', 'new_str', 'replacement', 'message',
  'description', 'prompt', 'body', 'summary', 'title', 'note', 'comment', 'comments',
])

// The names are assembled from fragments so that this file does not contain the strings it refuses: an agent
// editing the guard would otherwise refuse its own edit.
const INSENSITIVE: readonly RegExp[] = [
  String.raw`\.bean` + String.raw`count(?!\w)`,
  String.raw`\.side` + `car`,
  String.raw`\.cred` + String.raw`entials\.yaml`,
].map(source => new RegExp(source, 'i'))

const SENSITIVE: readonly RegExp[] = [new RegExp(`BEAN` + `COUNT_MCP_[A-Z]`)]

const collected = (value: unknown, key: string | undefined, found: string[]): void => {
  if (typeof value === 'string') {
    if (key === undefined || !PROSE.has(key)) found.push(value)
    return
  }
  if (Array.isArray(value)) {
    for (const item of value) collected(item, key, found)
    return
  }
  if (value !== null && typeof value === 'object') {
    for (const [name, item] of Object.entries(value)) collected(item, name, found)
  }
}

/** The reason a call is refused, or undefined when it may go ahead. */
export function judge(tool: string, args: unknown, options: GuardOptions): string | undefined {
  if (tool.startsWith(OWN_PREFIX)) return undefined
  const fields: string[] = []
  collected(args ?? null, undefined, fields)
  const hit = fields.some(field =>
    INSENSITIVE.some(pattern => pattern.test(field))
    || SENSITIVE.some(pattern => pattern.test(field))
    || options.paths.some(path => path !== '' && field.includes(path)))
  return hit ? 'Ledger files and finance settings are not available to this tool. Use the finance tools instead.' : undefined
}
