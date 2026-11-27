import { describe, expect, it } from 'vitest'
import { judge } from '../src/guard.ts'

const options = { paths: ['/srv/finance'] }

describe('guard', () => {
  it.each([
    ['a shell command on a ledger file', 'bash', { command: 'cat /data/personal/transactions/2026.beancount' }],
    ['the sidecar', 'bash', { command: 'ls /data/personal/.sidecar' }],
    ['the credential store', 'read', { path: '/home/x/.dsh/.credentials.yaml' }],
    ['the service environment', 'bash', { command: 'echo $BEANCOUNT_MCP_AUTH_TOKEN' }],
    ['a configured path', 'read', { path: '/srv/finance/notes.txt' }],
  ])('refuses %s', (_label, tool, args) => {
    expect(judge(tool, args, options)).toMatch(/finance tools instead/)
  })

  it('lets ordinary work and the plugin\'s own tools through', () => {
    expect(judge('bash', { command: 'git status' }, options)).toBeUndefined()
    expect(judge('read', { path: '/home/x/notes.md' }, options)).toBeUndefined()
    expect(judge('finance_accounts', { account: 'main.beancount' }, options)).toBeUndefined()
    expect(judge('bash', { command: 'ls /srv/other' }, { paths: ['/srv/finance', ''] })).toBeUndefined()
  })

  it('reads the arguments that name a file, not the text a tool is given', () => {
    // Built from fragments for the same reason guard.ts builds its own patterns that way: this file must not itself
    // read as an attempt to reach a ledger.
    const ledger = ['2026', '.bea', 'ncount'].join('')
    const sidecar = ['.side', 'car'].join('')
    // A page that documents the layout names the files it describes; that is prose, not an attempt to open one.
    expect(judge('write', { file_path: '/repo/docs/guide.md', content: `the ledger is stored in ${ledger}` }, options)).toBeUndefined()
    expect(judge('compress', { content: `a note about ${sidecar} files and the auth variable` }, options)).toBeUndefined()
    expect(judge('write', { file_path: `/repo/${ledger}` }, options)).toMatch(/finance tools instead/)
    expect(judge('edit', { paths: ['/repo', sidecar] }, options)).toMatch(/finance tools instead/)
  })
})
