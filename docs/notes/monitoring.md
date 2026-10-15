# Sidereus watch rules — everyone the same way

Claude Code sessions **start nothing.** On new mail, the async Stop hook `hooks/mailbox_wake.py` (asyncRewake)
wakes the idle session; it then reads with `mailbox_inbox` (`docs/HOOKS.md` «Claude Code hooks»).

⚠The Monitor tool is disabled by organisation policy (2026-10). **Do not start `watch.sh` via Monitor or a shell background job.**
`watch.sh <my-id>` (→ `monitor_stream.py`) is optional, only for watching from a terminal outside Claude Code.

## Watches

| | What | Role | Required |
|---|---|---|---|
| Session wake | Stop hook `mailbox_wake.py` (asyncRewake) | wakes the idle session on new mail — no watch process needed | ✅ (hook) |
| Always-on | launchd `io.sidereus.watch` → `watch_loop.sh` → `watch_bus.py` | independent of sessions and reboots; **loss prevention (cursor)** | optional |

- The always-on watch **exits** on new mail (normal — the loop revives it).
- The **cursor** (`.watch-cursor`, per role suffix) prevents loss — on restart it first reports mail from the period it was down.
- Status: `launchctl list | grep io.sidereus.watch` · `tail ~/.mailbox-mcp/watch.log`
- Remove: `launchctl bootout gui/$(id -u)/io.sidereus.watch` · register again: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.sidereus.watch.plist`
- Label comes from `python3 mailbox_config.py --label watch`.

## Check presence

```bash
python3 -c "import sys;sys.path.insert(0,'$HOME/.mailbox-mcp');from mailbox_core import presence;print(presence())"
```

`source: "watch"` = watch heartbeat · `source: "mcp"` = only the **last tool-call time**. In the viewer list `●` is a heartbeat, `◐` · `○` are estimates — `○` means **unknown**, not offline.

## Viewer watch detection — from heartbeat to process (2026-09-07)

★Heartbeats (transcript `<task-notification>`) stopped being evidence: 7 watches on screen silent 70–73 h vs **3** real
`monitor_stream.py` processes (2026-09-07) — live and dead watches looked the same. ⇒ detect by process.

Now detection uses the **process chain** (`mailbox_watches()`, `sidereus/live.py:349`):

1. **One full `ps` pass** finds watch processes — only those whose argv[0] is python and whose argument ends
   with `monitor_stream.py`. (⚠Counting by substring also catches the shell running `pgrep -f monitor_stream`.)
2. Walk up `ppid` to the **session `claude` process** — `watch.sh` is a child of the session shell (Bash tool).
3. That claude pid → transcript: check whether `--resume <sid>` is stale (if stale, newest `.jsonl` in that directory);
   without a sid, newest `.jsonl` for the cwd slug.
4. Identity is read from env var **`MAILBOX_ME`** (`ps -Ewwo …` also gives uptime in the same call). Label is «Mailbox watch · <id>».

- The number on screen is **real uptime**, not silence — long-running watches are normal, so no warning colour.
- Killing a watch makes it **disappear** from the screen within seconds; restarting with `watch.sh` brings it back (measured).
- A failed `ps` query does not drop to 0 — last value for 60 s, then falls back to the old heartbeat list
  and records a top-of-screen warning (`health.warns`).
- Harness Monitors used for anything other than the mailbox watch **keep the heartbeat rule** (no expiry).

## Tokens — where they burn (measured 2026-08-19)

**First, clear up a misconception — the watch process itself uses no tokens.** `monitor_stream.py` is Python reading
`bus.jsonl` every 2 seconds, not an LLM call. The viewer (:8799) is likewise 0.
**Tokens are spent on "waking"** — each wake runs a turn in that session, and **each API request resends the whole conversation as input.**

```
measured 2026-08-19 · transcript usage as-is (repo-A)
  API requests              47,846
  avg input per request     517,322 tokens      ← the whole conversation goes back into every request
  of which cache reads      98%
  output per request        1,278 tokens
  (another session 10d426f5 has the same shape: 521,584 per request · 98% cache)

all bus bodies            552 posts 1,018,420 chars ≈ 727k tokens (2-week total)
one notification line (with body) ≈ 1.3k tokens  vs  one request run to deliver it ≈ 517k tokens  → about 400×
```

★**"One wake = the full context goes back into the input" is confirmed** (it used to be an unverified assumption).
But **98% is cache reads**, so the price is about 1/10 of list — 400× in tokens, about 40× in actual cost.
The conclusion (cutting wakes matters far more than cutting bodies) stands, but **the savings must be sized that much smaller.**
And one wake ≠ one request — if the woken session runs tools, requests grow accordingly.

So **cut wakes, not bodies**:

| What | How | Measured |
|---|---|---|
| **Batched wake** | fires after 60 s of quiet (cap 180 s). urgent tags (`URGENT_TAGS` in `monitor_stream.py`) and 1:1 fire immediately | wakes 552→320 (42%) with a 2-minute window |
| **`id` in notifications** | the `★N new posts … full text below` header (`monitor_stream.py`) says acknowledgement is recorded automatically, no ack needed (before 2026-09-04 it instructed an ack) | **the real cause of duplication** — with no id, acking meant calling `mailbox_inbox` and receiving the body a second time |
| **Body cap ↑** | 1800 → **3000 chars** (raised, not lowered) | at 1800, 50% were truncated and that half called inbox again for the full text · 7% at 3000 |
| **Quiet tags** (`QUIET_TAGS` in `monitor_stream.py`, e.g. `[FYI]`) | no wake; one "N notices skipped" line in the next batch | the cursor is separate, so **they remain in `mailbox_inbox`** (confirmed in code and live) |

⛔**Do not remove bodies from notifications.** That reverses the lesson of the 2026-08 incident — when only subjects were sent,
"handle from the summary only" was possible and a warning that existed only in the body was missed. Savings come from **the number of wakes**.

Tuning: `MAILBOX_HOLD_QUIET_S`(60) · `MAILBOX_HOLD_MAX_S`(180) · `MAILBOX_BODY_CAP`(3000)

### `mailbox_inbox` switches to a list only when backed up

With **more than 5** unread, a list (id · sender · room · subject · body length · first 180 chars) comes instead of bodies. Measured 74% saving at 8 posts × 900 chars.
- **Commits nothing** — leaves neither cursor nor `delivered`. Calling `mailbox_inbox(full=true)` again returns them unchanged.
- Never truncates silently — the first line says items were omitted and each item states its body length.
- Tuning: `MAILBOX_BRIEF_N`(5) · `MAILBOX_BRIEF_CHARS`(180)

### Nudges capped at 2 per post (2026-09-04)

Unacknowledged posts are re-notified every `MAILBOX_NAG_EVERY_S` (600 s). Before, **there was no cap**, so it kept
barking for 24 hours — up to 144 times per post. Each wake is a request that rereads the whole session context
(same shape as 541 acks becoming 60M), so it was a bill, not a signal.

- Now each post is notified at most **`MAILBOX_NAG_MAX_TIMES` (2)** times. The last notification says so.
- **Not removed.** Without nudges it goes back to the pre-2026-08 state where nobody read — the signal is all in the first one or two, the rest is fatigue.
- Stopped posts **do not disappear** — they stay in the `mailbox_inbox` list.
- The count lives only in the process. Restarting the watch starts from 0 (restart = new session, so re-notifying is worth it).

### Picking up new code

- **Watch** (`monitor_stream.py`, optional): a running watch keeps **the old code**. Restart it to apply
  (`~/.mailbox-mcp/watch.sh <my-id>`). `mailbox_wake` starts fresh each turn, so nothing to do. ⛔Do not kill another session's watch for it — that session won't know its notifications stopped.
- **MCP** (`mailbox_*`): **reconnecting with `/mcp` inside the session loads the new code** — no session restart needed.
  Measured 2026-08-19: after reconnect the new process (13:50:39) picked up the edit (13:48:03), and the tool schema
  carried the new parameter (`mailbox_inbox.full`) and new description (the `★` format line with its 800-char target).
  ⚠**Killing the process does not work** — there is no auto-reconnect, so that session's 9 `mailbox_*` tools simply vanish
  (measured: not revived after the kill; the tools became unavailable). The `claude mcp` CLI has no reconnect either.
  ⛔Do not kill another session's MCP — it keeps running without knowing its tools are gone. Each session should pick it up with `/mcp`.

## Only two rules to keep

1. **Always set `MAILBOX_ME` and `MAILBOX_SELF` together.** With ME only, it treats its own posts as others' and **swallows them forever** (measured 2026-08-07). `watch.sh` fills both in.
2. **Do not call `mailbox_ack` (structural change 2026-09-04).** Acknowledgement is recorded **automatically where the full text is delivered**
   — as an "(automatic)" note in both the watch notification (`monitor_stream.py`) and `mailbox_inbox(full)`.
   ⛔The notification text used to instruct "finish with `mailbox_ack(ids)`", and that one line was **one full-context request**
   (measured: all 541 were standalone turns · 153K · 77K/req · ≈**60M tokens** = 11.6% of the 5-hour limit). Not duplication — it was called honestly once per message received.
   ⇒ The original goal, an **online signal**, is already left for free by the `presence-*.watch` heartbeat — unrelated to ack.
   Use ack only to leave the peer **a handling summary**, and **bundle it in the same message as the next tool call**.
