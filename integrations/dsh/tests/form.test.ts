import { describe, expect, it } from 'vitest'
import {
  FormModel,
  numberField,
  textField,
  type Scope,
  type ScopeSnapshot,
} from '../src/client/settings/form.ts'

interface Settings {
  baseUrl?: string
  timeoutMs?: number
  guard?: boolean
}

/** The host's side of a settings form: one stored value, one field at a time. */
class FakeScope implements Scope<Settings> {
  value: Settings = {}
  writable = true
  accept = true
  readonly calls: string[] = []

  getSnapshot(): ScopeSnapshot<Settings> {
    return { status: 'ready', value: this.value, writable: this.writable, revision: 1 }
  }

  subscribe(): () => void {
    return () => {}
  }

  async set(field: string, value: unknown): Promise<boolean> {
    this.calls.push(`${field}=${String(value)}`)
    if (!this.accept) return false
    this.value = { ...this.value, [field]: value }
    return true
  }

  async unset(field: string): Promise<boolean> {
    this.calls.push(`clear ${field}`)
    if (!this.accept) return false
    this.value = Object.fromEntries(Object.entries(this.value).filter(([key]) => key !== field))
    return true
  }
}

const specs = [textField('baseUrl'), numberField('timeoutMs')]

describe('the settings form', () => {
  it('shows what is stored until something is typed', () => {
    const scope = new FakeScope()
    scope.value = { baseUrl: 'http://127.0.0.1:8421', timeoutMs: 15000 }
    const form = new FormModel(scope, specs)
    expect(form.field('baseUrl')).toEqual({ text: 'http://127.0.0.1:8421', overridden: false, invalid: false })
    expect(form.shell().dirty).toBe(false)
    expect(form.shell().available).toBe(true)
  })

  it('follows a draft and knows when it differs', () => {
    const scope = new FakeScope()
    scope.value = { baseUrl: 'http://a' }
    const form = new FormModel(scope, specs)
    form.edit('baseUrl', 'http://b')
    expect(form.field('baseUrl')).toMatchObject({ text: 'http://b', overridden: true })
    expect(form.shell().dirty).toBe(true)
    form.edit('baseUrl', 'http://a')
    expect(form.shell().dirty).toBe(false)
  })

  it('holds a save while a draft is not a value yet', () => {
    const form = new FormModel(new FakeScope(), specs)
    form.edit('timeoutMs', 'soon')
    expect(form.shell().invalid).toBe(true)
    expect(form.field('timeoutMs').invalid).toBe(true)
  })

  it('writes only the fields that changed, then forgets the drafts', async () => {
    const scope = new FakeScope()
    scope.value = { baseUrl: 'http://a', timeoutMs: 15000 }
    const form = new FormModel(scope, specs)
    form.edit('baseUrl', 'http://b')
    await form.save()
    expect(scope.calls).toEqual(['baseUrl=http://b'])
    expect(scope.value).toEqual({ baseUrl: 'http://b', timeoutMs: 15000 })
    expect(form.shell().dirty).toBe(false)
  })

  it('clears a setting from a blank draft', async () => {
    const scope = new FakeScope()
    scope.value = { baseUrl: 'http://a' }
    const form = new FormModel(scope, specs)
    form.edit('baseUrl', '')
    await form.save()
    expect(scope.calls).toEqual(['clear baseUrl'])
    expect(scope.value).toEqual({})
  })

  it('keeps everything typed when a write is refused', async () => {
    const scope = new FakeScope()
    scope.accept = false
    const form = new FormModel(scope, specs)
    form.edit('baseUrl', 'http://b')
    await form.save()
    expect(form.shell().failed).toBe(true)
    expect(form.field('baseUrl').text).toBe('http://b')
  })

  it('discards drafts without writing', () => {
    const scope = new FakeScope()
    const form = new FormModel(scope, specs)
    form.edit('baseUrl', 'http://b')
    form.discard()
    expect(form.field('baseUrl').text).toBe('')
    expect(scope.calls).toEqual([])
  })

  it('writes a secret first, and never for a blank draft', async () => {
    const scope = new FakeScope()
    const written: string[] = []
    const form = new FormModel(scope, specs, [{
      field: 'token',
      write: async (text) => {
        written.push(text)
        scope.calls.push('token')
        return true
      },
    }])
    form.edit('baseUrl', 'http://b')
    await form.save()
    expect(written).toEqual([])

    form.edit('token', 'secret')
    await form.save()
    expect(written).toEqual(['secret'])
    expect(scope.calls).toEqual(['baseUrl=http://b', 'token'])
    expect(form.field('token').text).toBe('')
    expect(form.shell().dirty).toBe(false)
  })
})
