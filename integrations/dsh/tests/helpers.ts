import { createServer } from 'node:http'
import type { SessionEvent } from '@deepseek-ai/dsh-session/types'

export const turnEnd = (): SessionEvent => ({ type: 'turn/end' }) as unknown as SessionEvent

export interface Seen { method: string; path: string; query: string; headers: Record<string, string | string[] | undefined>; body: string }

/** A stub finance service. `routes` maps "METHOD /path" to `{ status?, body }`. */
export async function stubService(routes: Record<string, { status?: number; body: unknown }>) {
  const requests: Seen[] = []
  const server = createServer((req, res) => {
    let raw = ''
    req.on('data', (chunk) => { raw += chunk })
    req.on('end', () => {
      const url = new URL(req.url ?? '/', 'http://x')
      requests.push({ method: req.method ?? '', path: url.pathname, query: url.search, headers: req.headers, body: raw })
      const answer = routes[`${req.method} ${url.pathname}`] ?? { status: 404, body: { detail: 'no route' } }
      res.writeHead(answer.status ?? 200, { 'content-type': 'application/json' })
      res.end(JSON.stringify(answer.body))
    })
  })
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve))
  const address = server.address()
  const port = typeof address === 'object' && address !== null ? address.port : 0
  return {
    url: `http://127.0.0.1:${port}`,
    requests,
    close: () => new Promise<void>(resolve => server.close(() => resolve())),
  }
}
