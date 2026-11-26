import type { SidebarsConfig } from '@docusaurus/plugin-content-docs'

const sidebars: SidebarsConfig = {
  main: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      items: ['getting-started/quickstart', 'getting-started/configuration', 'getting-started/first-ledger'],
    },
    {
      type: 'category',
      label: 'Concepts',
      items: [
        'concepts/ledgers',
        'concepts/proposals',
        'concepts/accounts',
        'concepts/recipes',
        'concepts/views',
        'concepts/security',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      items: [
        'guides/web-interface',
        'guides/claude-code',
        'guides/deepseek-harness',
        'guides/other-agents',
        'guides/fava',
        'guides/worked-examples',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      items: ['reference/mcp-tools', 'reference/agent-api', 'reference/rest-api', 'reference/recipes'],
    },
    {
      type: 'category',
      label: 'Development',
      items: ['development/architecture', 'development/testing', 'development/integrations'],
    },
  ],
}

export default sidebars
