/**
 * The settings form, written here rather than borrowed from another plugin's package: the harness's own form model is
 * an internal that changes between releases, and a plugin that imports it breaks on a patch bump. A draft is what the
 * page shows before anything is saved; only `save()` writes, one field at a time, and the host checks the revision.
 */

/** One settings field the page edits. */
export type Field = 'baseUrl' | 'tokenRef' | 'timeoutMs' | 'guard' | 'guardPaths' | 'token'

/** A field's draft as a write, or nothing when the text cannot be saved yet. */
export type FieldWrite = { kind: 'set'; value: unknown } | { kind: 'clear' }

export interface FieldSpec {
  field: Field
  /** The stored value, as the text the draft starts from. */
  format(value: unknown): string
  /** The draft text, as the write to make; undefined while the text is not a value yet. */
  parse(text: string): FieldWrite | undefined
}

/** A field the page stages and writes through its own call, never through the settings form. */
export interface SecretSpec {
  field: Field
  write(text: string): Promise<boolean>
}

export interface FieldState {
  /** The text the page shows: the draft when there is one, the stored value otherwise. */
  text: string
  /** Whether the page shows a draft that differs from what is stored. */
  overridden: boolean
  /** Whether the draft cannot be saved as it stands. */
  invalid: boolean
}

export interface FormShell {
  /** Whether the settings are readable yet. */
  available: boolean
  /** Whether the host lets this page change them. */
  writable: boolean
  /** Whether any draft differs from what is stored. */
  dirty: boolean
  /** Whether any draft is not a value yet. */
  invalid: boolean
  saving: boolean
  failed: boolean
}

/** What the host serves for this plugin's row: the stored settings, and a way to change one field. */
export interface ScopeSnapshot<T> {
  status: 'loading' | 'ready' | 'unavailable'
  value: T | undefined
  writable: boolean
  revision: number | undefined
}

export interface Scope<T> {
  getSnapshot(): ScopeSnapshot<T>
  subscribe(listener: () => void): () => void
  set(field: string, value: unknown): Promise<boolean>
  unset(field: string): Promise<boolean>
}

/** What a hook provider needs: a snapshot and a subscription. */
export interface SnapshotSource<T> {
  getSnapshot(): T
  subscribe(listener: () => void): () => void
}

/** The page's state, subscribed by the slot that renders it. */
export class Store<T> implements SnapshotSource<T> {
  private value: T
  private readonly listeners = new Set<() => void>()

  constructor(initial: T) {
    this.value = initial
  }

  readonly getSnapshot = (): T => this.value

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  set(value: T): void {
    this.value = value
    for (const listener of [...this.listeners]) listener()
  }
}

/** A text field: a blank draft clears the setting. */
export const textField = (field: Field): FieldSpec => ({
  field,
  format: value => (typeof value === 'string' ? value : ''),
  parse: text => (text.trim() === '' ? { kind: 'clear' } : { kind: 'set', value: text }),
})

/** A number field: a blank draft clears it, anything that is not a number keeps the save waiting. */
export const numberField = (field: Field): FieldSpec => ({
  field,
  format: value => (typeof value === 'number' ? String(value) : ''),
  parse: (text) => {
    if (text.trim() === '') return { kind: 'clear' }
    const parsed = Number(text)
    return Number.isSafeInteger(parsed) && parsed >= 0 ? { kind: 'set', value: parsed } : undefined
  },
})

/** The drafts over one settings form. */
export class FormModel<T> {
  private readonly scope: Scope<T>
  private readonly specs: FieldSpec[]
  private readonly secrets: SecretSpec[]
  private readonly drafts = new Map<Field, string>()
  private saving = false
  private failed = false

  constructor(scope: Scope<T>, specs: FieldSpec[], secrets: SecretSpec[] = []) {
    this.scope = scope
    this.specs = specs
    this.secrets = secrets
  }

  shell(): FormShell {
    const snapshot = this.scope.getSnapshot()
    return {
      available: snapshot.status === 'ready',
      writable: snapshot.writable,
      dirty: this.dirty(),
      invalid: this.specs.some(spec => this.field(spec.field).invalid),
      saving: this.saving,
      failed: this.failed,
    }
  }

  field(name: Field): FieldState {
    const stored = this.stored(name)
    const draft = this.drafts.get(name)
    if (draft === undefined) return { text: stored, overridden: false, invalid: false }
    const spec = this.specs.find(item => item.field === name)
    return { text: draft, overridden: draft !== stored, invalid: spec !== undefined && spec.parse(draft) === undefined }
  }

  edit(name: Field, text: string): void {
    if (text === this.stored(name)) this.drafts.delete(name)
    else this.drafts.set(name, text)
  }

  resetField(name: Field): void {
    this.drafts.delete(name)
  }

  discard(): void {
    this.drafts.clear()
    this.failed = false
  }

  /**
   * Write every draft. Secrets go first, because they live outside the settings form; then the form itself, one field
   * at a time, stopping at the first rejection and keeping the remaining drafts so nothing the page shows is lost.
   */
  async save(): Promise<void> {
    if (this.saving) return
    this.saving = true
    this.failed = false
    try {
      for (const secret of this.secrets) {
        const draft = this.drafts.get(secret.field)
        if (draft === undefined || draft === '') continue
        if (!(await secret.write(draft))) {
          this.failed = true
          return
        }
        this.drafts.delete(secret.field)
      }
      for (const spec of this.specs) {
        const draft = this.drafts.get(spec.field)
        if (draft === undefined) continue
        const write = spec.parse(draft)
        if (write === undefined) continue
        const accepted = write.kind === 'clear' ? await this.scope.unset(spec.field) : await this.scope.set(spec.field, write.value)
        if (!accepted) {
          this.failed = true
          return
        }
        this.drafts.delete(spec.field)
      }
    } finally {
      this.saving = false
    }
  }

  private dirty(): boolean {
    return this.specs.some(spec => this.field(spec.field).overridden)
      || this.secrets.some(secret => (this.drafts.get(secret.field) ?? '') !== '')
  }

  private stored(name: Field): string {
    // A stored secret is never read back, so its draft always starts blank.
    if (this.secrets.some(secret => secret.field === name)) return ''
    const spec = this.specs.find(item => item.field === name)
    if (spec === undefined) return ''
    const value = this.scope.getSnapshot().value
    return spec.format(value === undefined ? undefined : (value as Record<string, unknown>)[name])
  }
}
