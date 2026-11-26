#!/usr/bin/env bash
# PreToolUse: keep generic file and shell tools away from the ledger and the service credentials.
# The ledger is reached only through the beancount tools. This is a path and text check, so it needs
# no running service. Ledger files, the sidecar, the token and the service settings are refused.
#
# What is checked depends on the tool, so working on the service's own source stays possible:
#   Bash                      the whole command
#   Glob                      the pattern and the folder
#   Read, Write, Edit, Grep   the target path only, never the text being written or searched for
# Deliberately blunt: a false refusal costs a retry, a miss costs the boundary.
# Needs jq. Without it the hook cannot read its input and lets the call through.
# Extra paths to protect come from the environment variable named in guard_var, colon separated,
# for example the data folder.
input=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
tool=$(jq -r '.tool_name // ""' <<<"$input" 2>/dev/null) || exit 0
case "$tool" in
  Bash) text=$(jq -r '.tool_input.command // ""' <<<"$input") ;;
  Glob) text=$(jq -r '[.tool_input.pattern, .tool_input.path] | map(strings) | join("\n")' <<<"$input") ;;
  *) text=$(jq -r '[.tool_input.file_path, .tool_input.path, .tool_input.notebook_path] | map(strings) | join("\n")' <<<"$input") ;;
esac
[ -n "$text" ] || exit 0

# Pieces are joined from adjacent quotes so this file never contains what it looks for.
insensitive='\.''beancount([^[:alnum:]_]|$)|\.''sidecar|beancount-mcp/tok''en|plugins/data/beanc''ount'
sensitive='BEANCOUNT''_MCP_[A-Z]|CLAUDE_PLUGIN_''OPTION|CLAUDE_PLUGIN_''DATA'
hit=0
grep -Eiq "$insensitive" <<<"$text" && hit=1
grep -Eq "$sensitive" <<<"$text" && hit=1
guard_var='BEANCOUNT''_MCP_GUARD_PATHS'
IFS=: read -ra extra <<<"${!guard_var:-}"
for path in "${extra[@]}"; do
  [ -n "$path" ] && grep -Fq -- "$path" <<<"$text" && hit=1
done
[ "$hit" = 0 ] && exit 0

jq -n '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny",
  permissionDecisionReason: "Ledger files and finance service settings are not available to file or shell tools. Use the beancount tools instead."}}'
