#!/usr/bin/env node
// PreToolUse for the tools that take a receipt. When the model passes receipt "attached", it means the image the user
// attached to the chat: the model has seen it, but cannot hand its bytes to a tool. This hook finds that image in the
// session transcript, stores it with the service as the user (the same call the web interface makes), and replaces
// "attached" with the stored path. The model never supplies a file, only points at one the user sent.
// Fails closed for this one call (it says why) and never touches any other tool input.
import { readFileSync } from "node:fs";

const url = (process.env.BEANCOUNT_MCP_URL || process.env.CLAUDE_PLUGIN_OPTION_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const token = process.env.BEANCOUNT_MCP_AUTH_TOKEN || process.env.CLAUDE_PLUGIN_OPTION_API_TOKEN || "";
const EXTENSIONS = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf" };

const reply = (decision) => process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", ...decision } }));
const refuse = (reason) => reply({ permissionDecision: "deny", permissionDecisionReason: reason });

/** The most recent image the user attached, from the transcript the hook is pointed at. */
export function latestAttachedImage(transcript) {
  const entries = transcript.split("\n").filter(Boolean).map((line) => {
    try { return JSON.parse(line); } catch { return null; }
  });
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (entry?.type !== "user" || !Array.isArray(entry.message?.content)) continue;
    const images = entry.message.content.filter((part) => part?.type === "image" && part.source?.type === "base64");
    if (images.length > 0) {
      const { media_type: mediaType, data } = images[images.length - 1].source;
      return { mediaType, bytes: Buffer.from(data, "base64") };
    }
  }
  return undefined;
}

async function call(path, init = {}) {
  const response = await fetch(url + path, {
    ...init,
    headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), "x-client-id": "claude-code-hook", ...init.headers },
    signal: AbortSignal.timeout(20000),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `the service answered ${response.status}`);
  return body;
}

async function main() {
  const input = JSON.parse(readFileSync(0, "utf8"));
  const args = input.tool_input ?? {};
  if (args.receipt !== "attached") return;

  let transcript = "";
  try { transcript = readFileSync(input.transcript_path, "utf8"); } catch { /* handled below as no image */ }
  const image = latestAttachedImage(transcript);
  if (image === undefined) {
    return refuse("No image is attached to this conversation. Ask the user to attach the receipt, or to upload it in the web interface under Receipts, then use its path.");
  }
  const extension = EXTENSIONS[image.mediaType];
  if (extension === undefined) return refuse(`The attached image is ${image.mediaType}, which cannot be stored. Receipts are JPEG, PNG, WebP or PDF.`);

  try {
    let ledger = args.ledger;
    if (!ledger) {
      const ledgers = await call("/ledgers");
      if (!Array.isArray(ledgers) || ledgers.length !== 1) return refuse("Several ledgers exist: name the ledger when attaching a receipt.");
      ledger = ledgers[0].id;
    }
    const form = new FormData();
    form.set("file", new Blob([image.bytes], { type: image.mediaType }), `attached.${extension}`);
    const stored = await call(`/ledgers/${encodeURIComponent(ledger)}/receipts`, { method: "POST", body: form });
    // No permission decision: the user's own approval for the tool call still applies to the rewritten call.
    reply({ updatedInput: { ...args, receipt: stored.path } });
  } catch (error) {
    refuse(`The attached image could not be stored: ${error instanceof Error ? error.message : String(error)}`);
  }
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop())) await main();
