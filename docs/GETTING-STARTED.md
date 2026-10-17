# Getting started

**English** · [Korean](GETTING-STARTED.ko.md)

Steps 1 and 2 give you the screen. The rest is optional.

## 1. Get the code

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus      # any folder works
```

Needs Python 3.9 or later, nothing else; the macOS `/usr/bin/python3` works.
Data (logs, caches, mailbox, config) goes to `$MAILBOX_DIR`, default `~/.mailbox-mcp`
(Windows: `%USERPROFILE%\.mailbox-mcp`).

**Windows** (not yet verified on a real machine): wherever this page says `python3` or `/usr/bin/python3`, write
`py`. For `python3 -m sidereus …` you can also run `C:\path\sidereus\sidereus.cmd …` from any folder
(it uses `py -3`, else `python`); `py -m sidereus` works only inside the clone.
`~/.claude/settings.json` is `%USERPROFILE%\.claude\settings.json`.

## 2. Start the viewer

```sh
cd ~/sidereus
python3 -m sidereus start --demo --open      # synthetic data on :18799, nothing real read; Ctrl-C stops it
python3 -m sidereus start --open             # your own sessions on :8799; --port N moves it (saved)
python3 -m sidereus status
python3 -m sidereus stop
```

The first `start` writes `config.local.json` (never overwrites); its default `self.ids`, `<user>-sidereus`,
is fine. Sessions appear within a few seconds. If Claude Code has never run here, the page is empty with
no warnings. Without the launcher: `/usr/bin/python3 chat_server.py [--no-open] [--port N]`.
A second clone or data dir needs its own `--port N`; on 8799 `start` stops with "another Sidereus (different data dir)".

By default Sidereus reads the Claude Code OAuth token from the macOS keychain for the quota lookup and holds
`caffeinate` while sessions work. Off: `"quota_lookup": false`, `"keep_awake": false` in
`config.local.json`. See [SECURITY.md](../SECURITY.md).

On Windows the viewer, transcripts and mailbox work. Off there: live process probes, terminal jump, the
quota lookup, idle-sleep prevention, and harness evidence rows (`hooks/ev_hook.py` needs `fcntl`).
The shell scripts (`watch.sh`, `backup.sh`, `backup-data.sh`) need Git Bash or WSL.

## 3. Keep it running

```sh
python3 -m sidereus stop                         # if a plain start is running
python3 -m sidereus start --install-service      # starts at login, restarts if it dies
```

macOS writes `~/Library/LaunchAgents/io.sidereus.viewer.plist`. `sidereus stop` leaves a service alone; use:

```sh
launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer     # restart
launchctl bootout gui/$(id -u)/io.sidereus.viewer          # stop
rm ~/Library/LaunchAgents/io.sidereus.viewer.plist         # uninstall; otherwise stop/status still see a service
```

Windows (unverified) creates the logon task `Sidereus` with `schtasks /Create /SC ONLOGON` and runs it once.
It starts at login but is not restarted if it dies. Creating it may need an Administrator prompt: if you
see `Access is denied`, run the same `start --install-service` from a terminal opened with «Run as administrator».
`sidereus stop` leaves the task alone here too. Stop: `schtasks /End /TN Sidereus`; start again:
`schtasks /Run /TN Sidereus`; uninstall: `/End`, then `schtasks /Delete /TN Sidereus /F`.

## 4. Session state over OpenTelemetry

Claude Code can send each session's state (thinking, which tool) straight to Sidereus. Add to the `env`
block of `~/.claude/settings.json`; the port must match the viewer's:

```json
"CLAUDE_CODE_ENABLE_TELEMETRY": "1",
"OTEL_LOGS_EXPORTER": "otlp",
"OTEL_METRICS_EXPORTER": "none",
"OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:8799",
"OTEL_LOGS_EXPORT_INTERVAL": "3000"
```

New sessions pick it up. No prompts, responses or tool details are sent. Without it Sidereus works from the
transcripts, a little later.

## 5. MCP and hooks

Pick one way. ⚠ Not both: you would get every hook twice and two MCP servers (`sidereus` and `plugin:sidereus:sidereus`).

**Plugin (recommended).** Registers the `sidereus` MCP server and the nine hooks in
[HOOKS.md](HOOKS.md#claude-code-hooks). Its hooks run `python3` on macOS/Linux; on Windows they look on PATH
for Python 3.9+ as `python3`, then `py -3`, then `python`, and run through Git Bash, so install Git for Windows.
Its MCP server runs bare `python3`: on Windows without it, also register the server with the line from **Manual** below.

```text
/plugin marketplace add <path to your clone>
/plugin install sidereus@sidereus
```

Uninstall: `claude plugin uninstall sidereus@sidereus`, then `claude plugin marketplace remove sidereus`.

**Manual.** Print the lines with this clone's paths and Python (writes nothing), then use what it prints:

```sh
python3 -m sidereus setup-claude [--mailbox-mcp DIR]
```

Run the `claude mcp add` line and merge the hooks JSON into `~/.claude/settings.json`. On macOS the MCP line
looks like `claude mcp add --scope user sidereus -- /usr/bin/python3 ~/sidereus/mcp/sidereus_mcp.py`; on Windows
use the paths `setup-claude` prints. The hooks JSON holds the same nine hooks as the plugin.

Neither way registers the `mailbox` MCP server (§6).

Agents rarely call the tools unprompted. Add to your `AGENTS.md` or `CLAUDE.md`:

```md
- Before spawning several subagents, call `sidereus_quota`; follow its advice line.
- Before editing a file other agents may touch, call `sidereus_file_peers(path)`; if another live agent
  edited it in the last 30 min, coordinate or wait.
```

## 6. Mailbox between sessions

The mailbox ships here (`bus.jsonl`, `watch.sh`, `monitor_stream.py`, `mailbox_core.py`, the Stop hook).
The Chat tab and the work-popup DM already use it. A session receives mail, full body included, in one of
two ways:

- Instantly: the Stop async hook `hooks/mailbox_wake.py` (asyncRewake) wakes an idle session on new mail;
  read it with `mailbox_inbox`.
  - It is active once the plugin or the `setup-claude` hooks JSON (§5) is in place; nothing else needs to run.
  - `watch.sh` is optional, for a plain terminal.
  - Config `mailbox_watch` turns the session-start notice off globally or per project.
- At the end of its turn, through the Stop hook `hooks/mailbox_stop.py` (sender and count only).
  See [HOOKS.md](HOOKS.md).

For a session to post on its own it needs `mailbox-mcp`, a separate MCP package not included here:

```sh
claude mcp add --scope user mailbox -- uv --directory <path-to-mailbox-mcp> run mailbox-mcp
```

## 7. Check

- Your sessions show up in the sessions drawer (top right).
- The status bar shows the 5-hour figure with `≈`. It is an estimate and sharpens over a few cycles.
- A new session asked to call `sidereus_quota` answers in a few lines.

Everyday use, with screenshots: [GUIDE.md](GUIDE.md).

## Uninstall

1. `python3 -m sidereus stop`; remove the service as in §3 and the plugin as in §5.
2. Delete the clone and, if you want the data gone too, `~/.mailbox-mcp`.

## When something looks wrong

| Symptom | Fix |
|---|---|
| Page does not load | `python3 -m sidereus status`, then start it (service: `launchctl kickstart -k ...`; Windows: `schtasks /Run /TN Sidereus`) |
| A code change does not show | The page is built at start. Restart the viewer. |
| No sessions listed | Check that `~/.claude/projects/` has recent `.jsonl` files. With `CLAUDE_CONFIG_DIR` set, the viewer must see the same variable (launchd: `EnvironmentVariables`) |
| MCP tools say "not reachable" | The viewer is down or just restarted. Call again. |
| MCP tools missing | Only sessions started after `claude mcp add` have them |

Log: `~/.mailbox-mcp/viewer.err`. It is append-only, so old lines are history, not current errors.
