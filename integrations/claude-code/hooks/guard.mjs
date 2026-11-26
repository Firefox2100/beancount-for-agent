#!/usr/bin/env node
// PreToolUse: keep generic file and shell tools away from the ledger and the service credentials.
// The ledger is reached only through the beancount tools. This is a path and text check, so it needs
// no running service and no dependencies beyond Node itself: Node runs the same way from cmd.exe,
// PowerShell, Git Bash and a POSIX shell, which a shell script does not.
// Ledger files, the sidecar, the token and the service settings are refused.
//
// What is checked depends on the tool, so working on the service's own source stays possible:
//   Bash                      the whole command
//   Glob                      the pattern and the folder
//   Read, Write, Edit, Grep   the target path only, never the text being written or searched for
// Deliberately blunt: a false refusal costs a retry, a miss costs the boundary.
// Without readable input the hook lets the call through.
// Extra paths to protect come from the environment variable named in guardVariable, separated by the
// platform's path separator, for example the data folder.
import { delimiter } from "node:path";

async function readInput() {
  let text = "";
  for await (const chunk of process.stdin) text += chunk;
  return text;
}

/** The text a tool is judged by: the command, the pattern and folder, or the target paths. */
function judged(tool, input) {
  if (tool === "Bash") return typeof input.command === "string" ? input.command : "";
  const keys = tool === "Glob" ? ["pattern", "path"] : ["file_path", "path", "notebook_path"];
  return keys
    .map((key) => input[key])
    .filter((value) => typeof value === "string" && value !== "")
    .join("\n");
}

const pieces = await readInput();
let payload;
try {
  payload = JSON.parse(pieces);
} catch {
  process.exit(0);
}
if (payload === null || typeof payload !== "object") process.exit(0);

const tool = typeof payload.tool_name === "string" ? payload.tool_name : "";
const input = payload.tool_input !== null && typeof payload.tool_input === "object" ? payload.tool_input : {};
const text = judged(tool, input);
if (text === "") process.exit(0);

// Pieces are joined from adjacent fragments so this file never contains what it looks for: the
// service's own checkout mentions ledger files all over, and must read as ordinary source.
const insensitive = new RegExp(
  ["\\." + "beancount([^A-Za-z0-9_]|$)", "\\." + "sidecar", "beancount-mcp/tok" + "en", "plugins/data/beanc" + "ount"].join("|"),
  "im",
);
const sensitive = new RegExp(["BEANCOUNT" + "_MCP_[A-Z]", "CLAUDE_PLUGIN_" + "OPTION", "CLAUDE_PLUGIN_" + "DATA"].join("|"));

const guardVariable = "BEANCOUNT" + "_MCP_GUARD_PATHS";
const extra = (process.env[guardVariable] ?? "").split(delimiter).filter((path) => path !== "");
// Windows paths are case-insensitive, so a guarded folder there is matched the way the file system does.
const fold = (value) => (process.platform === "win32" ? value.toLowerCase() : value);

let hit = insensitive.test(text) || sensitive.test(text);
if (!hit) {
  const haystack = fold(text);
  hit = extra.some((path) => haystack.includes(fold(path)));
}
if (!hit) process.exit(0);

process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason:
        "Ledger files and finance service settings are not available to file or shell tools. Use the beancount tools instead.",
    },
  }) + "\n",
);
