import z from '@deepseek-ai/schemastery'

/**
 * The plugin's settings. Every field is volatile: the settings card edits the live entry, and each is read at the
 * moment of use, so a change applies to the next call without a reload.
 */
export const Config = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8421').volatile(),
  tokenRef: z.string().role('credential-ref').default('BEANCOUNT_MCP_AUTH_TOKEN').volatile(),
  timeoutMs: z.natural().default(15000).volatile(),
  guard: z.boolean().default(true).volatile(),
  guardPaths: z.array(z.string()).default([]).volatile(),
})

export interface Settings {
  baseUrl: string
  tokenRef: string
  timeoutMs: number
  guard: boolean
  guardPaths: string[]
}

/** What `apply` receives: each setting as an accessor. */
export interface Accessors {
  baseUrl: { get(): string }
  tokenRef: { get(): string }
  timeoutMs: { get(): number }
  guard: { get(): boolean }
  guardPaths: { get(): string[] }
}

export function settingsOf(config: Accessors): Settings {
  let baseUrl = config.baseUrl.get()
  while (baseUrl.endsWith('/')) baseUrl = baseUrl.slice(0, -1)
  return {
    baseUrl,
    tokenRef: config.tokenRef.get(),
    timeoutMs: config.timeoutMs.get(),
    guard: config.guard.get(),
    guardPaths: config.guardPaths.get(),
  }
}
