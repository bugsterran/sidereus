---
name: sidereus-ship
description: Orchestrator's end-of-change procedure for the Sidereus viewer (~/.mailbox-mcp) — gates, restart, wait for 200, live screen check at 900/1100/1440, backup, commit. Use when finishing / shipping a Sidereus change, or when asked to restart + check + commit it.
---

# Ship a Sidereus change (orchestrator only)

Agents never restart, back up or commit — the orchestrator does it once, at the end, in this order.
Tag each Bash description with `[pl:<pipeline>/<stage>]` when running inside a pipeline (`[pl:-]` clears it).

1. **Gates** — all must pass before a restart.
   ```
   bash scripts/check.sh --fast
   for f in chat_server.py sidereus/*.py; do /usr/bin/python3 -m py_compile "$f"; done
   for f in web/*.js web/js/*.js; do node --check "$f"; done
   ```
   ⚠Always `/usr/bin/python3` (3.9.6) — 3.9 is the supported floor (the viewer may run newer); another python lets 3.9-incompatible syntax slip in.
   ⚠The Python compile cannot catch JS errors.
2. **Restart** — `launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer` (`web/` is read once at import; changes show only after this).
3. **Wait for 200** — `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8799/api/state` until `200`. On failure read the tail of `viewer.err` (append-only — old lines are fossils).
4. **Live screen check** — the rendered page at 900 / 1100 / 1440 widths, console errors 0.
   Headless playwright on `http://127.0.0.1:8799/?nosave=1` is fine (⚠always `?nosave=1`: MCP browsers report `navigator.webdriver=false`, so without it a click writes the owner's prefs). ⚠Never open a new browser for the user (their tab is open; just ask them to refresh).
   ⚠API responses are not proof — the API has been right while the screen was wrong more than once.
5. **Backup** — `bash backup.sh` (keeps the last 10).
6. **CHANGELOG** — for a user-visible change, add one line under `CHANGELOG.md` `[Unreleased]` (Added / Changed / Fixed), in the same commit.
7. **Commit** — the pre-commit hook runs `scripts/check.sh --fast` (install: `bash scripts/install-hooks.sh`).
   Message ends with the attribution lines given by the session. Local git only — no remote, no push.
   The body (before the attribution lines) ends with the criteria block from the `requirements` skill:
   ```
   Done when:
   R1: <line> — PASS
   R2: <line> — FAIL (<why>)
   Not doing: <Non-goal>
   ```

- ⚠Updating the screen baseline (`node scripts/screen_check.mjs --update`) is the orchestrator's decision, never an agent's.
- Commit only what was verified live; keep refactor commits separate from feature commits.
