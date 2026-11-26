import type { SnapshotStore } from '@deepseek-ai/dsh-client-store'
import {
  SettingsFormModel,
  settingsNumberField,
  settingsTextField,
  type SettingsFieldSpec,
  type SettingsFieldState,
  type SettingsFormActions,
  type SettingsFormScope,
  type SettingsFormShell,
} from '@deepseek-ai/dsh-client-ui-primitives'
import { getJson, postJson, type ConnectionStatus } from '../api.ts'

/** The plugin's settings as the form sees them. */
export interface BeancountSettings {
  baseUrl?: string
  tokenRef?: string
  timeoutMs?: number
  guard?: boolean
  guardPaths?: string[]
}

export type TestResult = { kind: 'ok'; ledgers: string[] } | { kind: 'failed'; message: string }

export interface SettingsState extends SettingsFormShell {
  baseUrl: SettingsFieldState
  tokenRef: SettingsFieldState
  timeoutMs: SettingsFieldState
  guard: boolean
  guardPaths: SettingsFieldState
  /** The staged token text; a stored token never leaves the host, so a draft starts blank. */
  token: SettingsFieldState
  /** What the credential store says, never the value; absent until read. */
  credential: ConnectionStatus['credential'] | undefined
  tokenError?: string
  testing: boolean
  test?: TestResult
}

export interface SettingsFace extends SettingsFormActions {
  hooks: { settings: SnapshotStore<SettingsState> }
  setGuard(on: boolean): void
  removeToken(): Promise<boolean>
  test(): Promise<void>
}

const guardField: SettingsFieldSpec = {
  field: 'guard',
  format: value => (value === false ? 'false' : 'true'),
  parse: text => (text === 'true' ? { kind: 'set', value: true } : text === 'false' ? { kind: 'set', value: false } : undefined),
}

/** One path a line; a blank line is nothing. */
const pathsField: SettingsFieldSpec = {
  field: 'guardPaths',
  format: value => (Array.isArray(value) ? value.join('\n') : ''),
  parse: text => ({ kind: 'set', value: text.split('\n').map(line => line.trim()).filter(line => line !== '') }),
}

/**
 * The Beancount settings tab: where the service is, the token (kept in the credential store and staged with the form,
 * so saving the page writes it and a discarded draft leaves the store alone), the guard, and a connection test.
 */
export class SettingsController {
  private readonly form: SettingsFormModel<BeancountSettings>
  private readonly store: SnapshotStore<SettingsState>
  private abort = new AbortController()
  private credential: SettingsState['credential']
  private tokenError: string | undefined
  private testing = false
  private tested: TestResult | undefined
  private running = false

  constructor(scope: SettingsFormScope<BeancountSettings>) {
    this.form = new SettingsFormModel(
      scope,
      [guardField, pathsField, settingsTextField('baseUrl'), settingsTextField('tokenRef'), settingsNumberField('timeoutMs')],
      [{ field: 'token', write: (text: string) => this.writeToken(text) }],
    )
    this.store = this.form.bind(() => this.projection())
  }

  start(): void {
    if (this.running) return
    this.running = true
    void this.read()
  }

  stop(): void {
    this.running = false
    this.abort.abort()
    this.abort = new AbortController()
  }

  private projection(): SettingsState {
    return {
      ...this.form.shell(),
      baseUrl: this.form.field('baseUrl'),
      tokenRef: this.form.field('tokenRef'),
      timeoutMs: this.form.field('timeoutMs'),
      guard: this.form.field('guard').text !== 'false',
      guardPaths: this.form.field('guardPaths'),
      token: this.form.field('token'),
      credential: this.credential,
      testing: this.testing,
      ...this.tokenError === undefined ? {} : { tokenError: this.tokenError },
      ...this.tested === undefined ? {} : { test: this.tested },
    }
  }

  private async read(): Promise<void> {
    try {
      const status = await getJson<ConnectionStatus>('/status', this.abort.signal)
      this.credential = status.credential
    } catch { /* the next read tries again */ }
    this.store.set(this.projection())
  }

  private async writeToken(value: string): Promise<boolean> {
    this.tokenError = undefined
    let stored = false
    try {
      await postJson('/credential', { value })
      stored = true
    } catch (error) {
      this.tokenError = error instanceof Error ? error.message : String(error)
    }
    await this.read()
    return stored
  }

  async test(): Promise<void> {
    this.testing = true
    this.store.set(this.projection())
    try {
      const status = await getJson<ConnectionStatus>('/status', this.abort.signal)
      this.credential = status.credential
      this.tested = status.ok ? { kind: 'ok', ledgers: status.ledgers ?? [] } : { kind: 'failed', message: status.message ?? 'unknown' }
    } catch (error) {
      this.tested = { kind: 'failed', message: error instanceof Error ? error.message : String(error) }
    }
    this.testing = false
    this.store.set(this.projection())
  }

  inject(): SettingsFace {
    return {
      hooks: { settings: this.store },
      ...this.form.actions(),
      setGuard: (on) => { this.form.actions().edit('guard', on ? 'true' : 'false') },
      removeToken: () => this.writeToken(''),
      test: () => this.test(),
    }
  }

  dispose(): void {
    this.stop()
    this.form.dispose()
  }
}
