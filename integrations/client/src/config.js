/**
 * @typedef {object} ClientConfig
 * @property {string} baseUrl Service root, without a trailing slash.
 * @property {string} [token] Bearer token. Omit for a service with no authentication.
 */

/**
 * Connection settings from the environment, the same names the service reads.
 * The URL and token are never taken from command arguments or tool input.
 *
 * @param {Record<string, string | undefined>} [env]
 * @returns {ClientConfig}
 */
export function configFromEnv(env = process.env) {
  const configuredUrl = env.BEANCOUNT_MCP_URL || "http://127.0.0.1:8000";
  let baseUrl = configuredUrl;
  while (baseUrl.endsWith("/")) baseUrl = baseUrl.slice(0, -1);
  const token = (env.BEANCOUNT_MCP_AUTH_TOKEN || "").trim();
  return token ? { baseUrl, token } : { baseUrl };
}
