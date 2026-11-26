#!/usr/bin/env bash
# SessionStart: tell the model what needs attention (bills due soon, proposals waiting for the user).
# Fails open: with the service down, or curl or jq missing, the session just starts without it.
# Settings arrive as plugin options in the hook's environment.
command -v curl >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 || exit 0
cat >/dev/null
url="${BEANCOUNT_MCP_URL:-${CLAUDE_PLUGIN_OPTION_URL:-http://127.0.0.1:8000}}"
token="${BEANCOUNT_MCP_AUTH_TOKEN:-${CLAUDE_PLUGIN_OPTION_API_TOKEN:-}}"
auth=()
[ -n "$token" ] && auth=(-H "authorization: Bearer $token")
get() { curl -sS --fail --max-time 5 "${auth[@]}" "${url%/}$1" 2>/dev/null; }

ledgers=$(get /ledgers | jq -r '.[].id') || exit 0
[ -n "$ledgers" ] || exit 0
lines=()
for ledger in $ledgers; do
  pending=$(get "/ledgers/$ledger/changes?status=pending" | jq 'length') || continue
  [ "$pending" -gt 0 ] && lines+=("Ledger $ledger: $pending proposal(s) waiting for the user's approval.")
  while IFS= read -r due; do
    [ -n "$due" ] && lines+=("Ledger $ledger: $due")
  done < <(get "/ledgers/$ledger/due?within_days=7" | jq -r '.[] | "\(.account) is due \(.due_date // "soon"), owing \(.owed | to_entries | map("\(.value) \(.key)") | join(", "))."' 2>/dev/null)
done
[ ${#lines[@]} -gt 0 ] || exit 0
printf '%s\n' "${lines[@]}" | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: ("Finance status:\n" + .)}}'
