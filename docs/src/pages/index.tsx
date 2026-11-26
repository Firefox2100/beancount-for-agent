import type { ReactNode } from 'react'
import clsx from 'clsx'
import Link from '@docusaurus/Link'
import Layout from '@theme/Layout'
import useBaseUrl from '@docusaurus/useBaseUrl'

import styles from './index.module.css'

function RouteNode({ children }: { children: ReactNode }) {
  return <span className={styles.routeNode}>{children}</span>
}

export default function Home(): ReactNode {
  const logo = useBaseUrl('/img/brand-mark.svg')

  return (
    <Layout
      title="Beancount for agents"
      description="Let agents help with bookkeeping through validated operations and human-approved changes.">
      <main className={styles.home}>
        <section className={styles.hero}>
          <div className={styles.heroCopy}>
            <div className={styles.heroIdentity}>
              <img src={logo} alt="" width="42" height="42" />
              <span>Beancount for agents</span>
            </div>
            <h1>Useful agents.<br />Untouched ledger.</h1>
            <p>
              Turn everyday financial intent into validated Beancount operations without giving an agent raw file access or the ability to approve its own work.
            </p>
            <div className={styles.heroActions}>
              <Link id="get-started" className={styles.primaryAction} to="/getting-started/quickstart">Start the quickstart</Link>
              <Link className={styles.secondaryAction} to="/concepts/proposals">Understand proposals</Link>
            </div>
          </div>

          <aside className={styles.heroAside} aria-label="Project principles">
            <p>Your ledger stays plain text.</p>
            <p>Invalid changes stop before the write.</p>
            <p>Agents propose. You decide.</p>
          </aside>
        </section>

        <section className={styles.receipt} aria-labelledby="receipt-title">
          <header className={styles.receiptHeader}>
            <h2 id="receipt-title">One change, shown end to end</h2>
            <span>Illustrative proposal · validated</span>
          </header>
          <div className={styles.routeLine} aria-hidden="true" />
          <div className={styles.receiptStages}>
            <article className={styles.stage}>
              <div className={styles.stageLabel}><RouteNode>1</RouteNode>Intent</div>
              <h3>Sample request: "I paid the pharmacy £18.65 on my card."</h3>
              <p>The agent asks for a purpose-built expense operation, not permission to edit ledger text.</p>
            </article>
            <article className={styles.stage}>
              <div className={styles.stageLabel}><RouteNode>2</RouteNode>Exact postings</div>
              <h3>What would change</h3>
              <dl className={styles.postings}>
                <div><dt>Expenses:Health:Pharmacy</dt><dd><span style={{color: '#285d85', fontSize: '.6rem', textTransform: 'uppercase'}}>Sample&nbsp;</span>18.65 GBP</dd></div>
                <div><dt>Liabilities:Card</dt><dd><span style={{color: '#285d85', fontSize: '.6rem', textTransform: 'uppercase'}}>Sample&nbsp;</span>−18.65 GBP</dd></div>
              </dl>
              <span className={styles.validated}>Parsed, booked and balanced</span>
            </article>
            <article className={clsx(styles.stage, styles.decisionStage)}>
              <div className={styles.stageLabel}><RouteNode>3</RouteNode>Human decision</div>
              <h3>Nothing writes itself.</h3>
              <p>Review the exact consequence. Approval is a separate door the agent cannot reach.</p>
              <div className={styles.decisionExample} aria-label="Illustrative decision controls">
                <span>Reject</span><strong>Approve</strong>
              </div>
            </article>
          </div>
          <footer className={styles.receiptFooter}>
            Intent <span>/</span> staged ledger <span>/</span> validation <span>/</span> human approval <span>/</span> atomic write
          </footer>
        </section>

        <section className={styles.boundary}>
          <div className={styles.sectionHeading}>
            <h2>The boundary is the product.</h2>
            <p>Agents get useful financial tools. They do not get a text editor, a credential, or an approval button.</p>
          </div>
          <div className={styles.boundaryFlow}>
            <div><strong>Agent surfaces</strong><span>MCP and native tools express business intent.</span></div>
            <div><strong>Service layer</strong><span>Recipes compile, stage and validate operations.</span></div>
            <div><strong>Your side</strong><span>Exact postings are approved before an atomic write.</span></div>
          </div>
          <Link className={styles.textLink} to="/concepts/security">Read the security model</Link>
        </section>

        <section className={styles.ownership}>
          <div>
            <h2>Still your books.</h2>
            <p>The durable source of truth remains an ordinary Beancount ledger. Open it with Fava, edit it by hand, back it up, or move it elsewhere.</p>
          </div>
          <pre aria-label="Example service layout"><code>{`one ASGI service
|-- REST API
|-- optional MCP endpoint
|-- human review interface
\-- Beancount engine -> ledger files`}</code></pre>
        </section>

        <section className={styles.paths}>
          <div className={styles.sectionHeading}>
            <h2>Choose the way in.</h2>
            <p>Run the service, connect an agent, or inspect the contracts before committing to either.</p>
          </div>
          <nav className={styles.pathLinks} aria-label="Getting started paths">
            <Link to="/getting-started/quickstart"><strong>Run the service</strong><span>Docker and source quickstart</span></Link>
            <Link to="/guides/claude-code"><strong>Claude Code</strong><span>MCP, guard hook and review commands</span></Link>
            <Link to="/guides/deepseek-harness"><strong>DeepSeek Harness</strong><span>Native tools and approval dock</span></Link>
            <Link to="/reference/rest-api"><strong>Read the API</strong><span>REST and agent-facing contracts</span></Link>
          </nav>
        </section>

        <section className={styles.status}>
          <div><h2>Young project, explicit expectations.</h2><p>The service and integrations work and are tested, but APIs and tool names can still change. Keep a backup of your ledger, as you would for any hand-edited file.</p></div>
          <Link className={styles.primaryAction} to="/getting-started/quickstart">Start with a throwaway ledger</Link>
        </section>
      </main>
    </Layout>
  )
}
