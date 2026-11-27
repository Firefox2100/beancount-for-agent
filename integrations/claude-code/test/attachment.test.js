import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { root, run, stubService } from "./helpers.js";

const HOOK = `${root}/hooks/attachment.mjs`;
const PNG = Buffer.from("89504e470d0a1a0a0000000d49484452", "hex");

/** A transcript with the user's messages: each is a list of parts, an image part being `{ image: bytes, type }`. */
function transcript(...messages) {
  const lines = messages.map((parts) => ({
    type: "user",
    message: {
      role: "user",
      content: parts.map((part) =>
        typeof part === "string"
          ? { type: "text", text: part }
          : { type: "image", source: { type: "base64", media_type: part.type ?? "image/png", data: part.image.toString("base64") } },
      ),
    },
  }));
  const file = join(mkdtempSync(join(tmpdir(), "attach-")), "session.jsonl");
  writeFileSync(file, lines.map((line) => JSON.stringify(line)).join("\n") + "\n");
  return file;
}

const call = (service, file, toolInput, env = {}) =>
  run(HOOK, [], {
    env: { CLAUDE_PLUGIN_OPTION_URL: service.url, CLAUDE_PLUGIN_OPTION_API_TOKEN: "t0k", ...env },
    input: JSON.stringify({ hook_event_name: "PreToolUse", tool_name: "mcp__x__record_expense", tool_input: toolInput, transcript_path: file }),
  });

test("the attached image is stored as the user and its path replaces the sentinel, with no permission decision", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "main" }] },
    "POST /ledgers/main/receipts": { status: 201, body: { path: "documents/receipts/2026/ab12-attached.png" } },
  });
  const result = await call(service, transcript(["Here is the receipt", { image: PNG }]), { amount: "5.30 USD", receipt: "attached" });
  await service.close();
  const output = JSON.parse(result.stdout).hookSpecificOutput;
  assert.equal(output.hookEventName, "PreToolUse");
  assert.deepEqual(output.updatedInput, { amount: "5.30 USD", receipt: "documents/receipts/2026/ab12-attached.png" });
  assert.equal(output.permissionDecision, undefined);
  const upload = service.requests.find((r) => r.method === "POST");
  assert.equal(upload.headers.authorization, "Bearer t0k");
  assert.equal(upload.headers["x-client-id"], "claude-code-hook");
  assert.equal(upload.headers["x-actor"], undefined);
  assert.match(upload.headers["content-type"], /^multipart\/form-data/);
  assert.match(upload.body, /name="file"; filename="attached\.png"/);
});

test("the most recent image of the conversation is the one stored", async () => {
  const service = await stubService({ "GET /ledgers": { body: [{ id: "main" }] }, "POST /ledgers/main/receipts": { status: 201, body: { path: "documents/x.png" } } });
  const older = Buffer.from("OLDER-IMAGE-BYTES");
  const newer = Buffer.from("NEWER-IMAGE-BYTES");
  await call(service, transcript(["first", { image: older, type: "image/png" }], ["second", { image: newer, type: "image/png" }], ["no image here"]), { receipt: "attached" });
  await service.close();
  const upload = service.requests.find((r) => r.method === "POST");
  assert.match(upload.body, /NEWER-IMAGE-BYTES/);
  assert.doesNotMatch(upload.body, /OLDER-IMAGE-BYTES/);
});

test("any other call is left alone and the service is not contacted", async () => {
  const service = await stubService({});
  const file = transcript(["receipt", { image: PNG }]);
  for (const input of [{ amount: "1 USD" }, { receipt: "documents/receipts/2026/ab12-lunch.jpg" }, { receipt: "ab12-lunch.jpg" }]) {
    const result = await call(service, file, input);
    assert.equal(result.code, 0);
    assert.equal(result.stdout, "");
  }
  await service.close();
  assert.equal(service.requests.length, 0);
});

test("with no image in the conversation the call is refused and says what to do", async () => {
  const service = await stubService({});
  const result = await call(service, transcript(["just words"]), { receipt: "attached" });
  await service.close();
  const output = JSON.parse(result.stdout).hookSpecificOutput;
  assert.equal(output.permissionDecision, "deny");
  assert.match(output.permissionDecisionReason, /No image is attached.*Receipts/);
  assert.equal(service.requests.length, 0);
});

test("a type the service cannot keep, and a refusal from the service, are explained", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "main" }] },
    "POST /ledgers/main/receipts": { status: 422, body: { detail: "the file is 20,000,000 bytes; at most 15,000,000 are accepted" } },
  });
  const gif = JSON.parse((await call(service, transcript([{ image: PNG, type: "image/gif" }]), { receipt: "attached" })).stdout).hookSpecificOutput;
  assert.match(gif.permissionDecisionReason, /image\/gif.*cannot be stored/);
  const big = JSON.parse((await call(service, transcript([{ image: PNG }]), { receipt: "attached" })).stdout).hookSpecificOutput;
  assert.equal(big.permissionDecision, "deny");
  assert.match(big.permissionDecisionReason, /could not be stored: the file is 20,000,000 bytes/);
  await service.close();
});

test("with several ledgers the call must name one, and the named one is used", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "a" }, { id: "b" }] },
    "POST /ledgers/b/receipts": { status: 201, body: { path: "documents/y.png" } },
  });
  const file = transcript([{ image: PNG }]);
  const vague = JSON.parse((await call(service, file, { receipt: "attached" })).stdout).hookSpecificOutput;
  assert.match(vague.permissionDecisionReason, /name the ledger/);
  const named = JSON.parse((await call(service, file, { receipt: "attached", ledger: "b" })).stdout).hookSpecificOutput;
  assert.equal(named.updatedInput.receipt, "documents/y.png");
  await service.close();
});

test("a service that cannot be reached refuses this one call and nothing else", async () => {
  const file = transcript([{ image: PNG }]);
  const result = await run(HOOK, [], {
    env: { BEANCOUNT_MCP_URL: "http://127.0.0.1:1" },
    input: JSON.stringify({ tool_name: "mcp__x__get_receipt", tool_input: { receipt: "attached", ledger: "main" }, transcript_path: file }),
  });
  assert.equal(result.code, 0);
  assert.match(JSON.parse(result.stdout).hookSpecificOutput.permissionDecisionReason, /could not be stored/);
});

test("the hook is registered for every tool that takes a receipt, and for no other", () => {
  const hooks = JSON.parse(readFileSync(`${root}/hooks/hooks.json`, "utf8")).hooks.PreToolUse;
  const entry = hooks.find((item) => item.hooks.some((hook) => hook.command.includes("attachment.mjs")));
  assert.ok(entry, "attachment hook registered");
  const matcher = new RegExp(`^(?:${entry.matcher})$`);
  for (const tool of ["get_receipt", "record_expense", "record_income", "record_transfer", "perform_recipe"]) {
    assert.ok(matcher.test(`mcp__plugin_beancount_beancount__${tool}`), tool);
  }
  for (const tool of ["Bash", "mcp__plugin_beancount_beancount__get_balances", "mcp__plugin_beancount_beancount__record_recurring"]) {
    assert.ok(!matcher.test(tool), tool);
  }
});
