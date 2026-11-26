/**
 * The controls the settings tab draws itself. The harness's form components are internal: importing them means a patch
 * release can blank the page, so the few controls this plugin needs live here, styled with theme tokens only.
 */
import type { ReactNode } from 'react'
import css from '../Page.module.css'
import type { FormShell } from './form.ts'

export interface FrameLabels {
  unavailable: string
  readOnly: string
  saveFailed: string
  save: string
  saving: string
  discard: string
}

export function Button({ children, onClick, disabled, primary }: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  primary?: boolean
}) {
  return (
    <button type="button" className={primary === true ? `${css.button} ${css.primary}` : css.button} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  )
}

/** The frame around a settings form: the fields, then save and discard. */
export function Frame({ labels, state, onSave, onDiscard, children }: {
  labels: FrameLabels
  state: FormShell
  onSave(): void
  onDiscard(): void
  children: ReactNode
}) {
  if (!state.available) return <p className={css.muted}>{labels.unavailable}</p>
  return (
    <div className={css.group}>
      {children}
      <div className={css.actions}>
        <Button primary disabled={!state.writable || state.saving || !state.dirty || state.invalid} onClick={onSave}>
          {state.saving ? labels.saving : labels.save}
        </Button>
        <Button disabled={!state.dirty || state.saving} onClick={onDiscard}>{labels.discard}</Button>
        {!state.writable && <span className={css.muted} role="status">{labels.readOnly}</span>}
        {state.failed && <span className={css.error} role="alert">{labels.saveFailed}</span>}
      </div>
    </div>
  )
}

/** A staged secret: the page never shows the stored value, only whether there is one. */
export function SecretField({ id, label, hint, stateLabel, text, configured, disabled, onEdit }: {
  id: string
  label: string
  hint: string
  stateLabel: string
  text: string
  configured: boolean
  disabled: boolean
  onEdit(text: string): void
}) {
  return (
    <div className={css.field}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        className={css.input}
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={text}
        disabled={disabled}
        placeholder={configured ? '••••••••' : ''}
        onChange={(event) => { onEdit(event.target.value) }}
      />
      <span className={css.muted} role="status">{stateLabel}</span>
      <span className={css.muted}>{hint}</span>
    </div>
  )
}
