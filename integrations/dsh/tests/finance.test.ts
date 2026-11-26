import { afterEach, describe, expect, it } from 'vitest'
import { Finance, FinanceError, describeDetail } from '../src/finance.ts'
import { stubService } from './helpers.ts'

let service: Awaited<ReturnType<typeof stubService>> | undefined
afterEach(async () => { await service?.close(); service = undefined })

const settings = (baseUrl: string) => () => ({ baseUrl, tokenRef: 'T', timeoutMs: 2000, guard: true, guardPaths: [] })

describe('Finance', () => {
  it('sends the token, identifies the model as an agent in its session, and the dock as the user', async () => {
    service = await stubService({ 'GET /agent/ledgers': { body: [] }, 'GET /ledgers': { body: [] } })
    const finance = new Finance(settings(service.url), async () => 's3cret')
    await finance.agent('session-1', 'GET', '/agent/ledgers')
    await finance.user('GET', '/ledgers')
    const [agent, user] = service.requests
    expect(agent?.headers.authorization).toBe('Bearer s3cret')
    expect(agent?.headers['x-actor']).toBe('agent')
    expect(agent?.headers['x-session-id']).toBe('session-1')
    expect(agent?.headers['x-client-id']).toBe('dsh')
    expect(user?.headers['x-actor']).toBe('user')
    expect(user?.headers['x-client-id']).toBe('dsh-ui')
  })

  it('resolves the token on every call, so a rotated one reaches the next request', async () => {
    service = await stubService({ 'GET /agent/ledgers': { body: [] } })
    let current = 'one'
    const finance = new Finance(settings(service.url), async () => current)
    await finance.agent('s', 'GET', '/agent/ledgers')
    current = 'two'
    await finance.agent('s', 'GET', '/agent/ledgers')
    expect(service.requests.map(request => request.headers.authorization)).toEqual(['Bearer one', 'Bearer two'])
  })

  it('reports the service\'s own reason, and an unreachable service plainly', async () => {
    service = await stubService({ 'GET /agent/accounts': { status: 422, body: { detail: 'no open account matches "Nope"' } } })
    const finance = new Finance(settings(service.url), async () => undefined)
    await expect(finance.agent('s', 'GET', '/agent/accounts')).rejects.toMatchObject({ message: 'no open account matches "Nope"', status: 422 })
    const down = new Finance(settings('http://127.0.0.1:1'), async () => undefined)
    await expect(down.agent('s', 'GET', '/agent/ledgers')).rejects.toThrow(/cannot reach the finance service/)
    await expect(down.agent('s', 'GET', '/agent/ledgers')).rejects.toBeInstanceOf(FinanceError)
  })

  it('writes validation problems as readable text', () => {
    expect(describeDetail([{ loc: ['body', 'amount'], msg: 'Field required' }])).toBe('amount: Field required')
    expect(describeDetail('plain')).toBe('plain')
  })
})
