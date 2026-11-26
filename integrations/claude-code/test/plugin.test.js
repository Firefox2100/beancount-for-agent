import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { root, run, stubService } from "./helpers.js";

const json = (path) => JSON.parse(readFileSync(join(root, path), "utf8"));
const tools = json("../contract/mcp-tools.json");

const guard = (tool_input, env = {}, tool_name = "Bash") =>
  run(`${root}/hooks/guard.mjs`, [], { env, input: JSON.stringify({ hook_event_name: "PreToolUse", tool_name, tool_input }) });

test("manifest, MCP and hook files are valid and agree", () => {
  assert.equal(json(".claude-plugin/plugin.json").name, "beancount");
  const server = json(".mcp.json").mcpServers.beancount;
  assert.equal(server.type, "http");
  assert.match(server.url, /\/mcp$/);
  assert.match(server.headers.Authorization, /user_config\.api_token/);
  assert.ok(json(".claude-plugin/plugin.json").userConfig.api_token.sensitive);
  assert.ok(json("hooks/hooks.json").hooks.PreToolUse[0].matcher.includes("Bash"));
});

test("the skill only names tools that exist, and covers the write tools", () => {
  const skill = readFileSync(join(root, "skills/beancount/SKILL.md"), "utf8");
  const names = new Set(tools.map((tool) => tool.name));
  const mentioned = [...skill.matchAll(/`([a-z]+_[a-z_]+)`/g)].map((match) => match[1]);
  for (const name of mentioned) assert.ok(names.has(name), `${name} is not a tool`);
  for (const tool of tools.filter((t) => t.tags.includes("propose") || t.tags.includes("recipe"))) {
    assert.ok(skill.includes(`\`${tool.name}\``), `skill does not mention ${tool.name}`);
  }
});

test("the agent-facing text never mentions the API or approval commands", () => {
  const skill = readFileSync(join(root, "skills/beancount/SKILL.md"), "utf8");
  assert.doesNotMatch(skill, /\bcurl\b|\/ledgers|\/approve|\bREST\b|BEANCOUNT_MCP/);
});

test("review commands are user-only and the script is not on the agent's PATH", () => {
  for (const name of ["pending", "approve", "reject", "due"]) {
    assert.match(readFileSync(join(root, `skills/${name}/SKILL.md`), "utf8"), /disable-model-invocation: true/);
  }
  assert.throws(() => statSync(join(root, "bin")), "a bin/ folder would put the review script on the agent's PATH");
  assert.ok(readdirSync(join(root, "scripts")).includes("review.mjs"));
});

test("integrations never import the Python package", () => {
  const skill = readFileSync(join(root, "skills/beancount/SKILL.md"), "utf8");
  assert.doesNotMatch(skill, /beancount_mcp\./);
});

test("hooks and commands run Node, never a shell script", () => {
  // Windows runs a hook's command through cmd.exe, which cannot execute a .sh file; `node "…"` works everywhere.
  for (const [event, entries] of Object.entries(json("hooks/hooks.json").hooks)) {
    for (const { command } of entries.flatMap((entry) => entry.hooks)) {
      assert.match(command, /^node "\$\{CLAUDE_PLUGIN_ROOT\}\/[^"]+\.mjs"$/, `${event}: ${command}`);
    }
  }
  assert.deepEqual(readdirSync(join(root, "hooks")).filter((name) => name.endsWith(".sh")), []);
  assert.deepEqual(
    readdirSync(join(root, "scripts")).filter((name) => !name.endsWith(".mjs")),
    [],
    "a shell script here would not run on Windows",
  );
  for (const name of readdirSync(join(root, "skills"))) {
    const skill = readFileSync(join(root, `skills/${name}/SKILL.md`), "utf8");
    for (const command of skill.matchAll(/^(node .*)$/gm).map((match) => match[1])) {
      assert.match(command, /^node "\$\{CLAUDE_PLUGIN_ROOT\}\/scripts\/[^"]+\.mjs" /, `${name}: ${command}`);
    }
    assert.doesNotMatch(skill, /^"\$\{CLAUDE_PLUGIN_ROOT\}\/scripts\/review /m);
  }
});

for (const [label, input] of [
  ["a ledger file", { command: "cat /srv/data/main/transactions/2026.beancount" }],
  ["the sidecar", { command: "ls /srv/data/main/.sidecar/changes" }],
  ["the token file", { command: "cat ~/.config/beancount-mcp/token" }],
  ["the environment", { command: "echo $BEANCOUNT_MCP_AUTH_TOKEN" }],
  ["a plugin option", { command: "env | grep CLAUDE_PLUGIN_OPTION" }],
  ["a grep inside a ledger", { command: "grep Expenses /home/x/ledger/main.beancount" }],
]) {
  test(`guard refuses ${label}`, async () => {
    const result = await guard(input);
    assert.equal(result.code, 0);
    const output = JSON.parse(result.stdout);
    assert.equal(output.hookSpecificOutput.permissionDecision, "deny");
    assert.doesNotMatch(output.hookSpecificOutput.permissionDecisionReason, /api|curl|approve/i);
  });
}

test("file tools are judged by their path, not by the text they carry", async () => {
  const ledgerFile = "/srv/data/main/transactions/2026.beancount";
  assert.match((await guard({ file_path: ledgerFile }, {}, "Read")).stdout, /deny/);
  assert.match((await guard({ file_path: ledgerFile, content: "x" }, {}, "Write")).stdout, /deny/);
  assert.match((await guard({ pattern: "x", path: "/srv/data/main/.sidecar" }, {}, "Grep")).stdout, /deny/);
  assert.match((await guard({ pattern: "**/*.beancount" }, {}, "Glob")).stdout, /deny/);
  // Source code that merely mentions ledger files, or lives in the service's package folder, is fine.
  const mention = { file_path: "/work/src/beancount_mcp/ledger/edit.py", new_string: "main.beancount .sidecar" };
  assert.equal((await guard(mention, {}, "Edit")).stdout, "");
  assert.equal((await guard({ pattern: "main.beancount", path: "/work/src" }, {}, "Grep")).stdout, "");
  assert.equal((await guard({ command: "ls /work/src/beancount_mcp" })).stdout, "");
});

test("guard refuses configured extra paths and lets ordinary work through", async () => {
  assert.match((await guard({ command: "ls /srv/finance/data" }, { BEANCOUNT_MCP_GUARD_PATHS: "/srv/finance" })).stdout, /deny/);
  assert.equal((await guard({ command: "ls /srv/other" }, { BEANCOUNT_MCP_GUARD_PATHS: "/srv/finance" })).stdout, "");
  assert.equal((await guard({ command: "git status" })).stdout, "");
  assert.equal((await guard({ file_path: "/home/x/notes.md" })).stdout, "");
});

test("briefing reports pending proposals and bills due, with the plugin's token", async () => {
  const service = await stubService({
    "GET /ledgers": { body: [{ id: "main" }] },
    "GET /ledgers/main/changes": { body: [{ id: "c1" }, { id: "c2" }] },
    "GET /ledgers/main/due": { body: [{ account: "Liabilities:Visa", due_date: "2026-03-20", owed: { USD: "120.00" } }] },
  });
  const result = await run(`${root}/hooks/briefing.mjs`, [], {
    env: { CLAUDE_PLUGIN_OPTION_URL: service.url, CLAUDE_PLUGIN_OPTION_API_TOKEN: "t0k" },
    input: "{}",
  });
  await service.close();
  const context = JSON.parse(result.stdout).hookSpecificOutput;
  assert.equal(context.hookEventName, "SessionStart");
  assert.match(context.additionalContext, /2 proposal\(s\) waiting/);
  assert.match(context.additionalContext, /Liabilities:Visa is due 2026-03-20, owing 120.00 USD/);
  assert.equal(service.requests[0].headers.authorization, "Bearer t0k");
});

test("briefing fails open when the service is down", async () => {
  const result = await run(`${root}/hooks/briefing.mjs`, [], { env: { BEANCOUNT_MCP_URL: "http://127.0.0.1:1" }, input: "{}" });
  assert.equal(result.code, 0);
  assert.equal(result.stdout, "");
});
