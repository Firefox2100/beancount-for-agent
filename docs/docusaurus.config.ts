import { themes as prismThemes } from 'prism-react-renderer'
import type { Config } from '@docusaurus/types'
import type * as Preset from '@docusaurus/preset-classic'

const config: Config = {
  title: 'Beancount for agents',
  tagline: 'Let agents manage your finances in Beancount, without ever editing the ledger',
  favicon: 'img/favicon.svg',
  future: { v4: true },
  url: 'https://firefox2100.github.io',
  baseUrl: '/beancount-for-agent/',
  organizationName: 'Firefox2100',
  projectName: 'beancount-for-agent',
  onBrokenLinks: 'throw',
  markdown: { hooks: { onBrokenMarkdownLinks: 'throw' } },
  i18n: { defaultLocale: 'en', locales: ['en'] },
  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/Firefox2100/beancount-for-agent/tree/main/docs/',
        },
        blog: false,
        theme: { customCss: './src/css/custom.css' },
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    navbar: {
      title: 'Beancount for agents',
      items: [
        { type: 'docSidebar', sidebarId: 'main', position: 'left', label: 'Documentation' },
        { href: 'https://github.com/Firefox2100/beancount-for-agent', label: 'GitHub', position: 'right' },
      ],
    },
    footer: { style: 'dark', copyright: 'Beancount for agents' },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'json', 'toml', 'python'],
    },
    colorMode: { respectPrefersColorScheme: true },
  } satisfies Preset.ThemeConfig,
}

export default config
