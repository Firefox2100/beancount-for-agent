import { useState } from 'react'
import type { InjectFace, PropsLocale, PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { Button, Frame, SecretField, type FrameLabels } from './controls.tsx'
import type { SettingsFace } from './controller.ts'
import css from '../Page.module.css'

export type SectionProps = PropsRuntime<'settings.section'> & PropsLocale<'beancount'> & InjectFace<SettingsFace>

/** The Beancount tab of the settings menu. */
export function Section(props: SectionProps) {
  const { t } = props
  const state = props.useSettings(snapshot => snapshot)
  const [busy, setBusy] = useState(false)
  const credential = state.credential
  const readOnly = !state.writable || (credential !== undefined && !credential.writable)
  const locked = readOnly || busy
  const labels: FrameLabels = {
    unavailable: t('unavailable'),
    readOnly: t('readOnly'),
    saveFailed: t('saveFailed'),
    save: t('save'),
    saving: t('saving'),
    discard: t('discard'),
  }
  const tokenState = credential === undefined
    ? t('tokenChecking')
    : credential.configured
      ? `${t('tokenSet')}${credential.source === undefined ? '' : ` (${t('tokenSource', { source: credential.source })})`}`
      : t('tokenUnset')
  return (
    <div className={css.section} data-testid="beancount-settings">
      <h2 className={css.title}>{t('settingsTitle')}</h2>
      <p className={css.muted}>{t('settingsDescription')}</p>
      <Frame labels={labels} state={state} onSave={() => { void props.save() }} onDiscard={() => { props.discard() }}>
        <label className={css.field}>{t('baseUrl')}
          <input className={css.input} value={state.baseUrl.text} disabled={!state.writable} onChange={(event) => { props.edit('baseUrl', event.target.value) }} />
        </label>
        <label className={css.field}>{t('tokenName')}
          <input className={css.input} value={state.tokenRef.text} disabled={!state.writable} onChange={(event) => { props.edit('tokenRef', event.target.value) }} />
        </label>
        <SecretField
          id="beancount-token-value"
          label={t('token')}
          hint={t('tokenHelp')}
          stateLabel={tokenState}
          text={state.token.text}
          configured={credential?.configured === true}
          disabled={locked}
          onEdit={(text) => { props.edit('token', text) }}
        />
        <div className={css.inline}>
          <Button disabled={locked || credential?.configured !== true} onClick={() => { setBusy(true); void props.removeToken().finally(() => { setBusy(false) }) }}>{t('tokenRemove')}</Button>
          {readOnly && <span className={css.muted} role="status">{t('tokenReadOnly')}</span>}
        </div>
        {state.tokenError !== undefined && <p className={css.error} role="alert">{state.tokenError}</p>}
        <label className={css.field}>{t('timeout')}
          <input className={css.input} type="number" min={1} step={500} value={state.timeoutMs.text} disabled={!state.writable} onChange={(event) => { props.edit('timeoutMs', event.target.value) }} />
        </label>
        <label className={css.inline}>
          <input type="checkbox" checked={state.guard} disabled={!state.writable} onChange={(event) => { props.setGuard(event.target.checked) }} />
          {t('guard')}
        </label>
        <label className={css.field}>{t('guardPaths')}
          <textarea className={css.area} rows={3} value={state.guardPaths.text} disabled={!state.writable} onChange={(event) => { props.edit('guardPaths', event.target.value) }} />
        </label>
        <p className={css.muted}>{t('guardPathsHelp')}</p>
      </Frame>
      <div className={css.inline}>
        <Button disabled={state.testing} onClick={() => { void props.test() }}>{state.testing ? t('testing') : t('test')}</Button>
        {state.test?.kind === 'ok' && <span role="status">{t('testOk', { ledgers: state.test.ledgers.join(', ') || t('testNone') })}</span>}
        {state.test?.kind === 'failed' && <span className={css.error} role="alert">{t('testFailed', { message: state.test.message })}</span>}
      </div>
    </div>
  )
}
