# Getting started

**English** · [Korean](GETTING-STARTED.ko.md)

Steps 1 and 2 give you the screen. The rest is optional.

## 0. Prerequisites

- **Python 3.9 or later.** macOS: the system `/usr/bin/python3` works. Windows: the installer from
  [python.org](https://www.python.org/downloads/windows/), which provides `py`.
- **Git.** Windows: Git for Windows (`winget install --id Git.Git -e --source winget`, or
  [git-scm.com](https://git-scm.com/install/windows)); the plugin hooks run through its Git Bash.
- **Claude Code** ([setup](https://code.claude.com/docs/en/setup)). macOS/Linux: `curl -fsSL https://claude.ai/install.sh | bash`;
  Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`.

After installing any of these, open a new terminal: an open one keeps the old PATH, so `claude` is "not recognized".

## 1. Get the code

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus      # any folder works
```

Needs Python 3.9 or later, nothing else; the macOS `/usr/bin/python3` works.
Data (logs, caches, mailbox, config) goes to `$MAILBOX_DIR`, default `~/.mailbox-mcp`
(Windows: `%USERPROFILE%\.mailbox-mcp`).

**Windows** (verified on a Windows 11 PC, 2026-10-17): wherever this page says `python3` or `/usr/bin/python3`, write
`py`. `python3` there is usually the Microsoft Store alias: it exits with code 49 and does nothing. For `python3 -m sidereus …` you can also run `C:\path\sidereus\sidereus.cmd …` from any folder
(it uses `py -3`, else `python`); `py -m sidereus` works only inside the clone.
`~/.claude/settings.json` is `%USERPROFILE%\.claude\settings.json`.
In PowerShell read a variable with `$env:SIDEREUS_PYTHON` (`echo %SIDEREUS_PYTHON%` is cmd syntax and prints
the text as is). `setx` applies only to windows opened afterwards: close and reopen PowerShell and Claude Code.

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

On Windows the viewer, paths, plugin hooks and MCP, session list, timeline, work-log popup, diff and the «Changes» chip
were checked on a real PC (2026-10-17). Not yet checked there: the logon service (§3), mailbox watch detection and
harness evidence rows. Off there: live process probes, terminal jump, the
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

Windows (not yet checked on a real PC) creates the logon task `Sidereus` with `schtasks /Create /SC ONLOGON` and runs it once.
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

Pick one way. ⚠ Not both: you would get every hook twice and two MCP servers (`sidereus` and `plugin:sidereus:sidereus`
in `claude mcp list`). If you have both, keep the plugin and run `claude mcp remove sidereus -s user`.

**Plugin (recommended).** Registers the `sidereus` MCP server and the nine hooks in
[HOOKS.md](HOOKS.md#claude-code-hooks). Its hooks run `python3` on macOS/Linux; on Windows they look on PATH
for Python 3.9+ as `py -3`, then `python3`, then `python` (the Microsoft Store `python3` alias is skipped, the find
is cached), and run through Git Bash, so install Git for Windows.
Its MCP server runs `python3`, or `SIDEREUS_PYTHON` when set (the hooks use the same variable).

**Windows, before installing the plugin:** run this once in PowerShell, then close and reopen PowerShell and Claude Code.
Without it `claude mcp list` shows `plugin:sidereus:sidereus: python3 ... ✘ Failed to connect`.

```powershell
setx SIDEREUS_PYTHON py
```

Install, inside Claude Code:

```text
/plugin marketplace add <path to your clone>
/plugin install sidereus@sidereus
```

Update after `git pull`:

```sh
claude plugin marketplace update sidereus
claude plugin update sidereus@sidereus
claude plugin list          # after restarting Claude Code: Version should be the new one
```

Claude Code keeps a cached copy per plugin version, so an update only arrives when `version` in
`plugin/.claude-plugin/plugin.json` changed. If Version stays the same, check `git status` in the clone: uncommitted
local edits stop `git pull`. Otherwise uninstall and install again.

Uninstall: `claude plugin uninstall sidereus@sidereus`, then `claude plugin marketplace remove sidereus`.

**Manual.** Let it do the work (Windows: `py -m sidereus setup-claude --write`):

```sh
python3 -m sidereus setup-claude --write
```

It shows the `claude mcp add` command it will run and a diff of `settings.json` (in `$CLAUDE_CONFIG_DIR`, else
`~/.claude`), asks `Apply? [y/N]`, then backs the file up to `settings.json.bak-YYYYMMDD-HHMMSS`, merges the hooks
and registers the MCP server. Re-running adds nothing twice. With the plugin installed it adds no hooks (they would
run twice). `--yes` skips the question for scripts; without a terminal and without `--yes` it writes nothing.

To do it by hand instead, print the lines with this clone's paths and Python (writes nothing):

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
- `claude mcp list` shows `plugin:sidereus:sidereus ... ✔ Connected` (plugin) or `sidereus ... ✔ Connected` (manual).
- A prompt does not show `UserPromptSubmit hook ... timed out after 10s`.

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
| `claude` is not recognized | Open a new terminal; the open one has the old PATH |
| Windows: `plugin:sidereus:sidereus ... ✘ Failed to connect` | `setx SIDEREUS_PYTHON py`, then reopen PowerShell and Claude Code (§5) |
| Windows: `UserPromptSubmit hook ... timed out after 10s` | Fixed in plugin 0.3.2. Update the plugin (§5) |
| Windows: `start` says the port is busy but nothing listens | Fixed in the current code. `git pull` |

Log: `~/.mailbox-mcp/viewer.err`. It is append-only, so old lines are history, not current errors.
