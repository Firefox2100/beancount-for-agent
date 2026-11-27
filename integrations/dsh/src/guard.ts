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
 * The argument names that can carry a file, a pattern or a command. Only these are searched: a tool that writes a
 * document must be able to quote a ledger file name or a setting in its text without being refused.
 */
const GUARDED = new Set([
  'command', 'cmd', 'script', 'pattern', 'glob', 'path', 'paths', 'file', 'files',
  'file_path', 'filepath', 'notebook_path', 'directory', 'cwd', 'url', 'target',
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
    if (key !== undefined && GUARDED.has(key)) found.push(value)
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
