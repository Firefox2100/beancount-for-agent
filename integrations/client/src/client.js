/**
 * @typedef {import("./config.js").ClientConfig} ClientConfig
 * @typedef {"pending" | "approved" | "rejected" | "withdrawn"} ChangeStatus
 * @typedef {{ id: string, ledger_id: string, status: ChangeStatus, note: string | null,
 *   caller: { actor: string, client_id: string | null, session_id: string | null },
 *   operation: { kind: string, [key: string]: unknown }, [key: string]: unknown }} PendingChange
 */

/** An error response from the service. `status` is the HTTP code, `detail` the reason it gave. */
export class ApiError extends Error {
  /**
   * @param {number} status
   * @param {unknown} detail
   */
  constructor(status, detail) {
    super(`${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * @param {ClientConfig & { actor?: string, clientId?: string, sessionId?: string, fetch?: typeof fetch }} config
 */
export function createClient(config) {
  const doFetch = config.fetch ?? fetch;
  let base = config.baseUrl;
  while (base.endsWith("/")) base = base.slice(0, -1);
  const headers = {
    accept: "application/json",
    "x-actor": config.actor ?? "user",
    ...(config.clientId ? { "x-client-id": config.clientId } : {}),
    ...(config.sessionId ? { "x-session-id": config.sessionId } : {}),
    ...(config.token ? { authorization: `Bearer ${config.token}` } : {}),
  };

  /**
   * @param {string} method
   * @param {string} path
   * @param {{ query?: Record<string, string | number | undefined>, body?: unknown, ifMatch?: string, signal?: AbortSignal }} [options]
   */
  async function request(method, path, options = {}) {
    const url = new URL(base + path);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
    }
    const response = await doFetch(url, {
      method,
      headers: {
        ...headers,
        ...(options.body !== undefined ? { "content-type": "application/json" } : {}),
        ...(options.ifMatch ? { "if-match": options.ifMatch } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) throw new ApiError(response.status, payload?.detail ?? payload ?? response.statusText);
    return payload;
  }

  const ledger = (id) => `/ledgers/${encodeURIComponent(id)}`;

  return {
    request,
    /** @returns {Promise<{ id: string }[]>} */
    ledgers: () => request("GET", "/ledgers"),
    /**
     * Proposed changes of one ledger.
     * @param {string} ledgerId
     * @param {ChangeStatus} [status] Defaults to `pending`.
     * @returns {Promise<PendingChange[]>}
     */
    changes: (ledgerId, status = "pending") => request("GET", `${ledger(ledgerId)}/changes`, { query: { status } }),
    /** @returns {Promise<PendingChange>} */
    change: (ledgerId, changeId) => request("GET", `${ledger(ledgerId)}/changes/${encodeURIComponent(changeId)}`),
    /** @returns {Promise<PendingChange>} */
    approve: (ledgerId, changeId, note) =>
      request("POST", `${ledger(ledgerId)}/changes/${encodeURIComponent(changeId)}/approve`, { body: { note: note ?? null } }),
    /** @returns {Promise<PendingChange>} */
    reject: (ledgerId, changeId, note) =>
      request("POST", `${ledger(ledgerId)}/changes/${encodeURIComponent(changeId)}/reject`, { body: { note: note ?? null } }),
    /**
     * Set or clear an account's bank details. Acts as the user: the service refuses agents.
     * @param {string} ledgerId
     * @param {string} account
     * @param {{ set?: Record<string, string>, clear?: string[] }} update
     */
    setAccountDetails: (ledgerId, account, update) =>
      request("PUT", `${ledger(ledgerId)}/accounts/${encodeURIComponent(account)}/details`, {
        body: { set: update.set ?? {}, clear: update.clear ?? [] },
      }),
    due: (ledgerId, withinDays) => request("GET", `${ledger(ledgerId)}/due`, { query: { within_days: withinDays } }),
    openItems: (ledgerId, account) => request("GET", `${ledger(ledgerId)}/open-items`, { query: { account } }),
    pools: (ledgerId) => request("GET", `${ledger(ledgerId)}/pools`),

    /**
     * Pending changes across every ledger, oldest first.
     * @returns {Promise<PendingChange[]>}
     */
    async allPending() {
      const found = [];
      for (const { id } of await this.ledgers()) found.push(...(await this.changes(id)));
      return found.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    },
  };
}
