---
name: Bug report
about: Something in Sidereus does not work as expected
labels: bug
---

<!--
Do not paste conversation text from any session, and do not paste private paths,
hostnames or session ids. Sidereus shows metadata only; keep reports the same way.
For screenshots, run the viewer with `--demo` so no real data is on screen.
-->

**What happened**

**What you expected**

**Steps to reproduce**
1.
2.

**Environment**
- OS:
- Python (`python3 --version`):
- Node (`node --version`):
- Sidereus commit:

**Other plugins / hooks** (optional — see docs/HOOKS.md «Coexisting with other hooks»)
- `/plugin` installed list:
- `hooks` block of `~/.claude/settings.json` and project `.claude/settings.json` (event, matcher, command only — no `env` values or secrets; redact tokens and paths inside hook commands):
- Claude Code version (`claude --version`):

**Relevant `viewer.err` lines** (redact paths)
