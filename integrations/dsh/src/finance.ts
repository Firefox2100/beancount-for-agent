import { ApiError, createClient } from '@beancount-mcp/client'
import type { Settings } from './settings.ts'

/** A failure the model or the person can act on: the service's own reason, or why it could not be reached. */
export class FinanceError extends Error {
  readonly status: number | undefined
  constructor(message: string, status?: number) {
    super(message)
    this.name = 'FinanceError'
    this.status = status
  }
}

export interface CallOptions {
  query?: Record<string, string | number | undefined>
  body?: unknown
  signal?: AbortSignal
  /** Replaces the settings' timeout for this call, for the requests that are allowed to take longer. */
  timeoutMs?: number
}

/** Who is asking, as the service records it: the model's tools are an agent, the dock page is the user. */
export type Caller = { actor: 'agent'; session: string } | { actor: 'user' }

/**
 * The finance service as the plugin sees it. The token is resolved from the credential store for each call and
 * never held: a rotated token reaches the next request, and nothing here can leak it into a tool result.
 */
export class Finance {
  constructor(
    private readonly settings: () => Settings,
    private readonly token: () => Promise<string | undefined>,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  async call<T>(caller: Caller, method: string, path: string, options: CallOptions = {}): Promise<T> {
    const settings = this.settings()
    const token = await this.token()
    const client = createClient({
      baseUrl: settings.baseUrl,
      ...(token === undefined ? {} : { token }),
      actor: caller.actor,
      clientId: caller.actor === 'agent' ? 'dsh' : 'dsh-ui',
      ...(caller.actor === 'agent' ? { sessionId: caller.session } : {}),
      fetch: this.fetchImpl,
    })
    const timeout = options.timeoutMs ?? settings.timeoutMs
    const signal = options.signal === undefined ? AbortSignal.timeout(timeout) : AbortSignal.any([options.signal, AbortSignal.timeout(timeout)])
    try {
      return (await client.request(method, path, { ...options, signal })) as T
    } catch (error) {
      if (error instanceof ApiError) throw new FinanceError(describeDetail(error.detail), error.status)
      // A caller's own cancellation travels untouched; our own deadline becomes a sentence that names the wait,
      // because `AbortSignal.timeout()` rejects as TimeoutError and would otherwise read as an unreachable service.
      if (options.signal?.aborted === true) throw error
      if (error instanceof Error && (error.name === 'AbortError' || error.name === 'TimeoutError')) {
        throw new FinanceError(`the finance service did not answer within ${String(timeout)} ms`, 504)
      }
      throw new FinanceError(`cannot reach the finance service at ${settings.baseUrl}`)
    }
  }

  /** `GET /agent/...` and friends, as the model's session. */
  agent<T>(session: string, method: string, path: string, options?: CallOptions): Promise<T> {
    return this.call<T>({ actor: 'agent', session }, method, path, options)
  }

  /** Calls that are the person's own, such as approving. */
  user<T>(method: string, path: string, options?: CallOptions): Promise<T> {
    return this.call<T>({ actor: 'user' }, method, path, options)
  }
}

/** The service's `detail`: a sentence, a list of validation problems, or something else worth showing. */
export function describeDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item !== null && typeof item === 'object' && 'msg' in item) {
          const where = 'loc' in item && Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : ''
          return where === '' ? String(item.msg) : `${where}: ${String(item.msg)}`
        }
        return JSON.stringify(item)
      })
      .join('; ')
  }
  return JSON.stringify(detail)
}
