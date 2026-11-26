/** The DSH releases the package is tested against, oldest first: the one list every constraint is derived from. */
export const DSH_RELEASES = ['0.2.2-rc.1']
/** The release the package is developed against: dev dependencies pin it exactly. */
export const DSH_DEVELOPMENT = '0.2.2-rc.1'
/**
 * DSH is in public beta and a patch bump has carried breaking changes, so every range stops before the next patch
 * line. Opening a new line is a deliberate release after the plugin has run against it. A range says what the package
 * installs on; "tested on" is claimed only for the releases in DSH_RELEASES after the full pass.
 *
 * `<0.2.3-0` is the lowest pre-release of 0.2.3, so the range stops before that line's first alpha too: a plain
 * `<0.2.3` would admit 0.2.3-alpha.1, which is not a 0.2.2 release and has not been tested.
 */
const DSH_COMPATIBILITY = [
  { packages: '>=0.2.2-rc.1 <0.2.3-0', engines: '>=0.2.2-rc.1 <0.2.3-0' },
]
/** Peer range of the `@deepseek-ai/dsh-*` packages, which share the runtime's version. */
export const DSH_PACKAGE_PEERS = DSH_COMPATIBILITY.map(({ packages }) => packages).join(' || ')
/** `engines.dsh`: each supported patch tuple, stopping before the next patch. */
export const DSH_ENGINES = DSH_COMPATIBILITY.map(({ engines }) => engines).join(' || ')
