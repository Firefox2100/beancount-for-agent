import { getJson, postJson, type ConnectionStatus } from '../api.ts'
import {
  FormModel,
  Store,
  numberField,
  textField,
  type Field,
  type FieldSpec,
  type FieldState,
  type FormShell,
  type Scope,
  type SnapshotSource,
} from './form.ts'

/** The plugin's settings as the form sees them. */
export interface BeancountSettings {
  baseUrl?: string
  tokenRef?: string
  timeoutMs?: number
  guard?: boolean
  guardPaths?: string[]
}

export type TestResult = { kind: 'ok'; ledgers: string[] } | { kind: 'failed'; message: string }

export interface SettingsState extends FormShell {
  baseUrl: FieldState
  tokenRef: FieldState
  timeoutMs: FieldState
  guard: boolean
  guardPaths: FieldState
  /** The staged token text; a stored token never leaves the host, so a draft starts blank. */
  token: FieldState
  /** What the credential store says, never the value; absent until read. */
  credential: ConnectionStatus['credential'] | undefined
  reference: ConnectionStatus['reference'] | undefined
  tokenError?: string
  testing: boolean
  test?: TestResult
}

/** What the settings page may do. */
export interface SettingsActions {
  edit(field: Field, text: string): void
  resetField(field: Field): void
  save(): Promise<void>
  discard(): void
}

export interface SettingsFace extends SettingsActions {
  hooks: { settings: SnapshotSource<SettingsState> }
  setGuard(on: boolean): void
  removeToken(): Promise<boolean>
  test(): Promise<void>
}

const guardField: FieldSpec = {
  field: 'guard',
  format: value => (value === false ? 'false' : 'true'),
  parse: text => (text === 'true' ? { kind: 'set', value: true } : text === 'false' ? { kind: 'set', value: false } : undefined),
}

/** One path a line; a blank line is nothing. */
const pathsField: FieldSpec = {
  field: 'guardPaths',
  format: value => (Array.isArray(value) ? value.join('\n') : ''),
  parse: text => ({ kind: 'set', value: text.split('\n').map(line => line.trim()).filter(line => line !== '') }),
}

/**
 * The Beancount settings tab: where the service is, the token (kept in the credential store and staged with the form,
 * so saving the page writes it and a discarded draft leaves the store alone), the guard, and a connection test.
 */
export class SettingsController {
  private readonly form: FormModel<BeancountSettings>
  private readonly store: Store<SettingsState>
  private readonly leave: () => void
  private abort = new AbortController()
  private credential: SettingsState['credential']
  private reference: SettingsState['reference']
  private tokenError: string | undefined
  private testing = false
  private tested: TestResult | undefined
  private running = false

  constructor(scope: Scope<BeancountSettings>) {
    this.form = new FormModel(
      scope,
      [guardField, pathsField, textField('baseUrl'), textField('tokenRef'), numberField('timeoutMs')],
      [{ field: 'token', write: (text: string) => this.writeToken(text) }],
    )
    this.store = new Store(this.projection())
    this.leave = scope.subscribe(() => { this.store.set(this.projection()) })
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
      reference: this.reference,
      testing: this.testing,
      ...this.tokenError === undefined ? {} : { tokenError: this.tokenError },
      ...this.tested === undefined ? {} : { test: this.tested },
    }
  }

  private async read(): Promise<void> {
    try {
      const status = await getJson<ConnectionStatus>('/status', this.abort.signal)
      this.credential = status.credential
      this.reference = status.reference
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
      this.reference = status.reference
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
      edit: (field, text) => { this.form.edit(field, text); this.store.set(this.projection()) },
      resetField: (field) => { this.form.resetField(field); this.store.set(this.projection()) },
      discard: () => { this.form.discard(); this.store.set(this.projection()) },
      save: async () => {
        await this.form.save()
        this.store.set(this.projection())
      },
      setGuard: (on) => { this.form.edit('guard', on ? 'true' : 'false'); this.store.set(this.projection()) },
      removeToken: () => this.writeToken(''),
      test: () => this.test(),
    }
  }

  dispose(): void {
    this.stop()
    this.leave()
  }
}
