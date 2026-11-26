#!/usr/bin/env node
// SessionStart: tell the model what needs attention (bills due soon, proposals waiting for the user).
// Fails open: with the service down, or a request failing, the session just starts without it.
// Settings arrive as plugin options in the hook's environment.
const url = (process.env.BEANCOUNT_MCP_URL || process.env.CLAUDE_PLUGIN_OPTION_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const token = process.env.BEANCOUNT_MCP_AUTH_TOKEN || process.env.CLAUDE_PLUGIN_OPTION_API_TOKEN || "";

async function get(path) {
  const response = await fetch(url + path, {
    headers: token ? { authorization: `Bearer ${token}` } : {},
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return await response.json();
}

/** What is owed, per currency: `120.00 USD, 50.00 CNY`. */
const owed = (amounts) =>
  Object.entries(amounts ?? {})
    .map(([currency, value]) => `${value} ${currency}`)
    .join(", ");

try {
  // The hook's input is not needed: the briefing only reports what the service already knows.
  for await (const _ of process.stdin) void _;

  const ledgers = await get("/ledgers");
  const lines = [];
  for (const { id } of Array.isArray(ledgers) ? ledgers : []) {
    if (typeof id !== "string" || id === "") continue;
    const pending = await get(`/ledgers/${encodeURIComponent(id)}/changes?status=pending`).catch(() => []);
    const waiting = Array.isArray(pending) ? pending.length : 0;
    if (waiting > 0) lines.push(`Ledger ${id}: ${waiting} proposal(s) waiting for the user's approval.`);
    const due = await get(`/ledgers/${encodeURIComponent(id)}/due?within_days=7`).catch(() => []);
    for (const bill of Array.isArray(due) ? due : []) {
      lines.push(`Ledger ${id}: ${bill.account} is due ${bill.due_date ?? "soon"}, owing ${owed(bill.owed)}.`);
    }
  }
  if (lines.length > 0) {
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: { hookEventName: "SessionStart", additionalContext: `Finance status:\n${lines.join("\n")}\n` },
      }),
    );
  }
} catch {
  // Fails open: a session start is not the place to report a missing service.
}
