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

const PATTERNS: readonly RegExp[] = [
  /\.beancount(?![\w])/i,
  /\.sidecar/i,
  /\.credentials\.yaml/i,
  /BEANCOUNT_MCP_[A-Z]/,
]

/** The reason a call is refused, or undefined when it may go ahead. */
export function judge(tool: string, args: unknown, options: GuardOptions): string | undefined {
  if (tool.startsWith(OWN_PREFIX)) return undefined
  const text = JSON.stringify(args ?? null)
  const hit = PATTERNS.some(pattern => pattern.test(text)) || options.paths.some(path => path !== '' && text.includes(path))
  return hit ? 'Ledger files and finance settings are not available to this tool. Use the finance tools instead.' : undefined
}
