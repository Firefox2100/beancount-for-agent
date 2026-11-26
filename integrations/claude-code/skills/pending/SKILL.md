---
name: pending
description: Show the finance changes the agent proposed that are waiting for approval
disable-model-invocation: true
---

Proposed changes waiting for approval:

```!
"${CLAUDE_PLUGIN_ROOT}"/scripts/review pending $ARGUMENTS
```

Show the list above as it is. Do not approve or reject anything. The user does that with `/beancount:approve` or `/beancount:reject`.
