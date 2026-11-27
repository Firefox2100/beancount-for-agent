/**
 * One reviewable text block for a proposed change: who proposed it and the exact postings.
 *
 * @param {import("./client.js").PendingChange} change
 * @returns {string}
 */
export function describeChange(change) {
  const lines = [`${change.id}  [${change.ledger_id}]  ${change.status}`];
  const who = [change.caller?.actor, change.caller?.client_id].filter(Boolean).join("/");
  if (who) lines.push(`from ${who}`);
  if (change.note) lines.push(`note: ${change.note}`);
  lines.push(...describeOperation(change.operation, ""));
  return lines.join("\n");
}

/** @returns {string[]} */
function describeOperation(operation, indent) {
  const kind = operation.kind;
  if (kind === "add_transaction" || kind === "update_transaction") {
    const t = /** @type {any} */ (operation).transaction;
    const head = [t.date, t.payee, t.narration].filter(Boolean).join(" ");
    const verb = kind === "add_transaction" ? "add" : `update ${/** @type {any} */ (operation).id}`;
    return [`${indent}${verb}: ${head}`, ...t.postings.map((p) => `${indent}    ${posting(p)}`)];
  }
  if (kind === "batch") {
    return /** @type {any} */ (operation).operations.flatMap((member) => describeOperation(member, indent + "  "));
  }
  if (kind === "open_account") {
    const o = /** @type {any} */ (operation);
    return [`${indent}open ${o.account}${o.type ? ` (${o.type})` : ""}`];
  }
  if (kind === "close_account") return [`${indent}close ${/** @type {any} */ (operation).account}`];
  if (kind === "reconcile") {
    const o = /** @type {any} */ (operation);
    return [`${indent}reconcile ${o.account} to ${grouped(o.amount.number)} ${o.amount.currency} on ${o.date}`];
  }
  return [`${indent}${kind}`];
}

/**
 * A decimal written with commas between thousands (`-1,234,567.80`). Works on the text, so nothing passes through a float.
 *
 * @param {string | number} value
 * @returns {string}
 */
export function grouped(value) {
  const match = /^([+-]?)(\d+)(\.\d+)?$/.exec(String(value));
  return match ? `${match[1]}${match[2].replace(/\B(?=(\d{3})+$)/g, ",")}${match[3] ?? ""}` : String(value);
}

function posting(p) {
  const units = p.units ? `${grouped(p.units.number)} ${p.units.currency}` : "";
  const price = p.price ? ` @ ${grouped(p.price.number)} ${p.price.currency}` : "";
  return `${p.account}  ${units}${price}`.trimEnd();
}
