import type { Context } from '@deepseek-ai/cordis'
// Type-only: these pull in the Context and SlotMap augmentations the pages rely on.
import type {} from '@deepseek-ai/dsh-api-remotes/client'
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-session/client'
import type {} from '@deepseek-ai/dsh-client-ui-settings/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import type {} from '../types.ts'
import { de, en, es, fr, ja, pt, ru, zh, type BeancountKey } from './locales.ts'
import { Page, type PageInjected } from './Page.tsx'
import { SettingsController, type BeancountSettings } from './settings/controller.ts'
import { Section } from './settings/Section.tsx'

declare module '@deepseek-ai/dsh-client-ui-slots' {
  interface LocaleNamespaceMap {
    beancount: BeancountKey
  }
}

const NAMESPACE = 'beancount'
const ID = 'dsh-beancount'
/** The Loader entry the host half runs under; its settings are what the settings tab edits. */
const ENTRY_ID = 'beancount'

export const inject = ['slots', 'locale', 'configForms', 'sidebarRightTabs']

/** A page in the right dock, reachable from its guide, and a tab in the settings menu. */
export function apply(ctx: Context): void {
  const t = ctx.locale.bind(NAMESPACE)
  // Every language the harness ships, so the dock page and the settings tab read the same way the rest of the UI does.
  ctx.effect(() => ctx.locale.register(NAMESPACE, { en, zh, ja, es, fr, de, ru, pt }), 'dsh-beancount: dictionaries')

  const drafts = new Map<string, string>()
  ctx.effect(() => ctx.sidebarRightTabs.register({
    id: ID,
    kind: 'beancount',
    title: () => t('title'),
    guide: [{ id: 'open', order: 41, title: () => t('title'), description: () => t('description') }],
  }), 'dsh-beancount: tab type')
  ctx.effect(() => ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({
    name: 'sidebar.right.pane.tab',
    key: ID,
    locale: NAMESPACE,
    inject: (sessionId: SessionId): PageInjected => ({ sessionId, drafts }),
  }, Page)), 'dsh-beancount: page')

  const settings = new SettingsController(ctx.configForms.get<BeancountSettings>(ENTRY_ID))
  ctx.effect(() => () => { settings.dispose() }, 'dsh-beancount: settings controller')
  settings.start()
  const face = settings.inject()
  ctx.effect(
    () => ctx.configForms.whileServed([ENTRY_ID], () => ctx.slots.inject('settings.section', () => ctx.slots.register({
      name: 'settings.section',
      id: 'beancount',
      order: 43,
      label: () => t('settingsSection'),
      locale: NAMESPACE,
      inject: () => face,
    }, Section))),
    'dsh-beancount: settings section',
  )
}
