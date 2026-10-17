# Configuration

**English** · [Korean](CONFIG.ko.md)

## Files and precedence

| | Location | Contents |
|---|---|---|
| Data | `$MAILBOX_DIR`, default `~/.mailbox-mcp` | bus, cursors, presence, caches, logs, `config.local.json`, `backup/` |
| Code | the folder the scripts are in | `chat_server.py`, `mailbox_*.py`, shell scripts, `hooks/`, `ext-hooks/` |

Data and code can be the same folder. Config file: `$MAILBOX_CONFIG`, else `$MAILBOX_DIR/config.local.json`, else built-in defaults.
Each value: environment variable > config file > default.

```sh
/usr/bin/python3 mailbox_config.py                 # config path + merged settings (JSON)
/usr/bin/python3 mailbox_config.py --get KEY       # one value; lists/objects print as JSON
/usr/bin/python3 mailbox_config.py --port          # resolved viewer port
/usr/bin/python3 mailbox_config.py --label NAME    # launchd label for job NAME
```

On Windows run them as `py mailbox_config.py ...`. The data dir default is `%USERPROFILE%\.mailbox-mcp`.

A missing or unreadable config file prints one warning and the defaults apply.

## Keys (`config.local.json`)

Copy `config.example.json`. Keys starting with `_` are comments. An unknown key or a value of the wrong type is ignored with one warning.

| Key | Type | Default | Effect |
|---|---|---|---|
| `self.ids` | string list | `[]` | Ids this install posts as. The first is the monitor identity. |
| `self.aliases` | string list | `[]` | Addresses that count as mail to me. Empty = `self.ids`. |
| `alias_strip_prefixes` | string list | `[]` | With `MAILBOX_ME=<prefix>x`, also answer to `x`. |
| `default_room` | string | `"general"` | Room the viewer opens and posts to. 1..64 chars, no `/ \`. |
| `viewer_me` | string | UI-language default | Name on posts made from the viewer. 1..64 chars. Unset (or `"user"` / its Korean form) = the UI language's default: `user` in English, the Korean word for "user" in Korean; posts under either spelling stay yours. |
| `readcheck_peer` | string | `""` | Peer for `readcheck.py` with no argument. |
| `saver_view_path` | string | `"~/.claude/hooks/.saver-view.json"` | Snapshot written by an external saver hook (not shipped). Missing file: no saver chip or advice line. Optional `levels` (`[{lv, cap, rules}]`) and `how` (strings) fill Settings › «Saver mode» › «What each level does»; absent or malformed = fold hidden. |
| `saver_hook_dir` | string | `"~/.claude/hooks"` | Folder of the saver hook's `.saver-force.json` and goal file. Absolute or `~`, no `..`. |
| `hook_session_patterns` | string list | `[]` | Regexes for the working dirs of hook-spawned sessions; matches are hidden. |
| `launchd_label_prefix` | string | `"io.sidereus"` | `--label viewer` prints `<prefix>.viewer`. Used by `ext-hooks/demo.sh` and the MCP down hint. The shipped plists do not read it. |
| `launchd_labels` | object | `{"viewer": "", "watch": "", "databackup": ""}` | Full label per job. Non-empty overrides `<prefix>.<name>`. |
| `quota_probe` | bool | `false` | While the quota lookup returns 429, send one paid Haiku call (`max_tokens 1`, about $0.00002; ~$0.02/month if 429 all month) every 120 s to read the credit ratio from headers. |
| `quota_lookup` | bool | `true` | `false`: never read the OAuth token from the keychain or call `api.anthropic.com`. The 5h/7d figures in the status bar go blank. See [SECURITY.md](../SECURITY.md). |
| `keep_awake` | bool | `true` | `false`: never hold `caffeinate` while sessions work. |
| `compact_history` | list of `["YYYY-MM-DD", int\|null]` | `[]` | Auto-compact threshold history: date it took effect, tokens (`null` = off). Dates strictly ascending, at most 50 rows, values 1000..10000000. `[]` = only the current setting. |
| `port` | int | `8799` | Viewer port, 1024..65535. Out of range is rejected, not clamped. See [Port](#port). |
| `features` | object `{id: bool}` | `{}` | Feature toggles (`features/<id>.json`). Missing id = on. A feature whose dependency is off is off. Unknown ids are refused. |
| `pipeline_apply` | `{mode, projects}` | `{"mode": "auto", "projects": {}}` | Pipelines tab «Apply». `mode`: `auto`, `ask` or `off`. `projects`: `{absolute path: mode}`, at most 200. Read by `hooks/pipelines_brief.py`. |
| `mailbox_watch` | `{mode, projects}` | `{"mode": "on", "projects": {}}` | Settings «Mailbox watch». `mode`: `on` or `off`; `projects` as above, longest prefix wins. Read by the SessionStart hook. |
| `claude_roots` | list of `{dir, label}` | `[]` | Extra Claude Code config dirs to read. See [Several Claude accounts](#several-claude-accounts). |

Server-side keys apply after a viewer restart.

### Port

Resolution: `--port N` (server only) > `SIDEREUS_PORT` > `port` > 8799. The server, `sidereus_cli.py`, the MCP server,
`hooks/file_peers_notice.py`, `ext-hooks/ext_hook.py` and the saver hook all resolve it the same way.
`sidereus_cli.py start --port N` writes it to the config file. After a change, open a new tab at the new address.

Saving «Port» in Settings can also move the port in `env.OTEL_EXPORTER_OTLP_ENDPOINT` of `~/.claude/settings.json`,
in the same confirm, only while the value is `http://127.0.0.1:<port>` or `http://localhost:<port>`.
Running sessions pick it up after their restart. `--port` on the CLI never touches that file.

### Several Claude accounts

If you run Claude Code with several config dirs (one per account, via `CLAUDE_CONFIG_DIR`), Sidereus finds them: the default account
(`$CLAUDE_CONFIG_DIR`, else `~/.claude`), `~/.claude` when the viewer runs with `CLAUDE_CONFIG_DIR`, every `~/.claude-*` with a
`projects/` folder, and `claude_roots` in `config.local.json` (restart to apply; `/` and your home are refused).
A root's label is its `claude_roots` label, else its name in the Orbit registry (`~/.claude-accounts`), else the folder name.
A root shows as signed in when its `.claude.json` names a different account than the default account. Sessions of other accounts resume with `CLAUDE_CONFIG_DIR`; usage, files and failures cover all roots; the settings and tools views use the default account only.
On screen (account bands, status-bar layer, «Main account», pickers): [GUIDE](GUIDE.md#check-whether-quota-lasts-until-the-reset).
Browser-side keys (UIS): `mbAcctPick.<view>` per view (`hist`, `tok`, `retro` included; «All accounts» by default), `mbKpiAcct` for «Show in bar». The older «Only main account» setting carries over once as the Sessions pick.
While another account is main, the plan, token estimates and pace (default account's) are hidden.
Setting up accounts and logging in is Claude Code's topic: <https://code.claude.com/docs/en/authentication>.
To pick an account per folder from the terminal, see the optional [Orbit](../plugins/orbit/README.md) plugin; Sidereus does not need it.

⚠ Don't switch accounts in one config dir with `/logout` and `/login`. Its sessions mix and Sidereus cannot tell them apart.

## Settings API

Settings › «Preferences» uses two routes. Writable keys: `saver_hook_dir`, `compact_history`, `viewer_me`,
`default_room`, `port`, `features`, `pipeline_apply`, `mailbox_watch`, `claude_roots` (the last four are not listed in `GET`'s `keys`: three have their own panes, `claude_roots` has no UI yet).

| Route | Body | Response |
|---|---|---|
| `GET /api/prefs` | | `{ok, path, keys:{k:{value, default, src, restart:true}}, mailbox_watch, ...}`; `src` is `env`, `file`, `default` or `claude` |
| `POST /api/prefs/set` | `{key, value}` or `{key, reset:true}` | `{ok, value, restart:true}`; 400 `{ok:false, err}`; 403 without the viewer Origin |

- ⚠ A key set by an environment variable is read-only (`src:"env"`).
- Writes go to a temp file and are renamed into place, with a `.bak`. Unknown and `_` keys in the file are kept.
- A config file that does not parse is never overwritten.

Two keys write Claude Code's `settings.json` (`src:"claude"`) — the default account's `~/.claude/settings.json` and every other account's (`~/.claude-*` and registered folders). The default account is the reference; an account file that is missing, invalid or a symlink is skipped and never created, and the page names it. The OTEL port is written to the default account only.

| Key | settings.json key | Type | Notes |
|---|---|---|---|
| `cc_auto_compact` | `autoCompactEnabled` | bool | Absent = `true`. |
| `cc_compact_window` | `autoCompactWindow` | int | 50000..1000000; out of range is rejected, not clamped. Also adds `[today, value]` to `compact_history` (same date replaced). |

- ⚠ Only these two keys, plus the OTEL port above, are ever written. Every other byte stays the same.
- With 2+ accounts a «Per account» switch appears: each account gets its own row, prefilled from its current values. After a preview + confirm only accounts whose values changed are written, each with a backup.
- A missing or symlinked extra account is skipped, never created.
- They apply to new Claude Code sessions; no viewer restart. `reset` is not supported.
- Backup: `tool-trash/<ts>/settings.json` in the data dir (other accounts: `tool-trash/<ts>/<label>/settings.json`). A missing or unparsable file is refused. A file that changed during the write returns 409.

## Environment variables

| Variable | Read by | Default | Effect |
|---|---|---|---|
| `MAILBOX_DIR` | all scripts | `~/.mailbox-mcp` | Data dir. |
| `MAILBOX_HOME` | `watch.sh` | unset | Old name for `MAILBOX_DIR`. |
| `MAILBOX_CONFIG` | `mailbox_config.py`, hooks | unset | Config file path. |
| `MAILBOX_ME` | `mailbox_core.py`, `monitor_stream.py`, `watch.sh`, `hooks/` | `self.ids[0]` | Identity of this session. |
| `MAILBOX_ALIASES` | `mailbox_core.py` | `self.aliases` | Comma-separated "to me" addresses. |
| `MAILBOX_SELF` | `mailbox_core.py`, `watch.sh` | `self.ids` | Comma-separated ids treated as my own posts. `watch.sh` sets it to `MAILBOX_ME` if unset. |
| `MAILBOX_VIEWER_ME` | `sidereus/config.py` | `viewer_me` | Name on viewer posts. |
| `MAILBOX_VIEWER_ROOM` | `sidereus/config.py` | `default_room` | Room the viewer opens. |
| `SIDEREUS_PORT` | server, CLI, MCP, hooks | `port` | Viewer port. |
| `CLAUDE_CONFIG_DIR` | server, MCP | `~/.claude` | Claude Code config root: transcripts, `settings.json`, skills/agents/plugins, and `.claude.json` inside it (unset: `~/.claude.json`). |
| `SIDEREUS_LAUNCHD_LABEL` | `mcp/sidereus_mcp.py` | from config | Viewer job label in the MCP down hint. |
| `SIDEREUS_QUOTA_PROBE` | `sidereus/quota.py` | `quota_probe` | `1` / `0`: paid quota probe on / off. |
| `SIDEREUS_QUOTA_LOOKUP` | `sidereus/quota.py` | `quota_lookup` | `1` / `0`: allow / forbid the keychain read and quota API call. |
| `MAILBOX_CARD_WAIT` | `sidereus/notes.py` | off | `1`: «Alerts» card when a session goes idle waiting for input. |
| `MAILBOX_CARD_CTX` | `sidereus/notes.py` | off | `1`: «Alerts» card when context is nearly full. |
| `MAILBOX_NAG_S` | `monitor_stream.py` | `300` | Seconds unacknowledged before a reminder. |
| `MAILBOX_NAG_EVERY_S` | `monitor_stream.py` | `600` | Seconds between reminders. |
| `MAILBOX_NAG_MAX_TIMES` | `monitor_stream.py` | `2` | Reminders per message. |
| `MAILBOX_NAG_MAX_AGE_S` | `monitor_stream.py` | `86400` | No reminder for messages older than this. |
| `MAILBOX_HOLD_QUIET_S` | `monitor_stream.py` | `60` | Hold output until the bus is quiet this long. |
| `MAILBOX_HOLD_MAX_S` | `monitor_stream.py` | `180` | Flush held output at least this often. |
| `MAILBOX_BODY_CAP` | `monitor_stream.py` | `3000` | Characters of a body printed. |
| `MAILBOX_SKIP_QUIET_S` | `monitor_stream.py` | `1800` | Warn if nothing was delivered for this long. |
| `MAILBOX_MCP_SRC` | `backup.sh` | `~/projects/mailbox-mcp` | Mailbox MCP server checkout included in code backups. |
| `SIDEREUS_EVIDENCE` | `scripts/check.sh` | `$MAILBOX_DIR/evidence.jsonl` | Gate-run record file (one JSON line per run, counts only; last 200 kept past 400). |

- ⚠ The launchd watch daemon starts without `MAILBOX_ME`; its identity comes from `self.*`. An empty or wrong `self.ids` drops or misattributes mail.
- ⚠ `self.ids[0]` (or `MAILBOX_ME`) names the cursor file `stream-<id>.cursor`. Changing it starts a new cursor.

## Services (macOS launchd)

macOS only. On Windows only the viewer has an autostart (below); the watch and data-backup jobs have
none, and their shell scripts need Git Bash or WSL.

Save each job as `~/Library/LaunchAgents/<Label>.plist`. Use absolute paths for `<CODE_DIR>` and `<DATA_DIR>`;
launchd does not expand `~`. Put `MAILBOX_DIR` and other variables in an `EnvironmentVariables` dict.
Create `<DATA_DIR>` first: launchd cannot write a log into a missing folder.

Viewer:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>io.sidereus.viewer</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string><CODE_DIR>/chat_server.py</string>
    <string>--no-open</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string><DATA_DIR>/viewer.log</string>
  <key>StandardErrorPath</key><string><DATA_DIR>/viewer.err</string>
  <key>WorkingDirectory</key><string><DATA_DIR></string>
</dict>
</plist>
```

The other two jobs use the same skeleton with these changes:

| Job | Label | ProgramArguments | Schedule | Logs |
|---|---|---|---|---|
| Watch | `io.sidereus.watch` | `/bin/bash <CODE_DIR>/watch_loop.sh` | `RunAtLoad`, `KeepAlive`, `ThrottleInterval 10` | `<DATA_DIR>/watch.log`, `watch.err` |
| Data backup | `io.sidereus.databackup` | `/bin/bash <CODE_DIR>/backup-data.sh` | `StartCalendarInterval` Hour 9 Minute 5, `RunAtLoad`; no `KeepAlive` | `<DATA_DIR>/backup/data/backup-data.log` (both) |

- `watch_loop.sh` restarts `watch_bus.py`, which exits on each new message by design.
- ⚠ `KeepAlive` on the backup job would rerun it forever. A missed 09:05 run happens on wake.
- Create `<DATA_DIR>/backup/data` before loading the backup job.

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.sidereus.viewer.plist   # load
launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer                             # restart
launchctl bootout gui/$(id -u)/io.sidereus.viewer                                  # unload
rm ~/Library/LaunchAgents/io.sidereus.viewer.plist   # also delete it, or stop/status still see a service
```

Windows (unverified): `--install-service` creates the logon task `Sidereus` (`schtasks /Create /SC ONLOGON`, runs
`pythonw.exe chat_server.py --no-open`). It is not restarted if it dies. Creating it may need an Administrator prompt;
on `Access is denied`, rerun from «Run as administrator». Restart: `schtasks /End /TN Sidereus` then
`schtasks /Run /TN Sidereus`. Remove: `/End`, then `schtasks /Delete /TN Sidereus /F`.

## Backups

| Script | Includes | Output | Keeps |
|---|---|---|---|
| `backup.sh` (manual) | `*.py`, `*.sh`, `config.example.json`, `hooks/`, `ext-hooks/`, `config.local.json`, `$MAILBOX_MCP_SRC/{src,pyproject.toml}` | `$MAILBOX_DIR/backup/mailbox-<stamp>.tar.gz` | 10 |
| `backup-data.sh` (launchd) | `bus.jsonl`, `acks.jsonl`, `cards.jsonl`, `rooms.json`, `profiles.json`, `identity.json` | `$MAILBOX_DIR/backup/data/mailbox-data-<stamp>.tar.gz` | 7; skipped if unchanged |

Cursors, PID files and presence are excluded: restoring them would rewind delivery. Backups stay on the local machine.

## Distribution exclusions

`.distignore` (gitignore syntax) lists what a published copy must not contain: `config.local.json`, live data
(bus, cursors, presence, caches, identity), logs, backups, screenshots, tool state and internal notes.
They are install-specific or hold private conversation data.

## Using with oh-my-claudecode

Sidereus runs next to oh-my-claudecode (OMC) 3.x and 5.x without changing OMC or `~/.claude`.

- **HUD quota.** One poller serves both: Sidereus writes the usage cache under both the 3.x and 5.x file names
  in the OMC plugin dir, and reads OMC's cache when it is fresher.
- **Mail delivery.** If an OMC hook ends a turn with `continue: false`, the mailbox Stop hook's block is dropped;
  the same mail is delivered again on the next stop.
- **Do not run `/omc-setup` in this repo.** It writes a `CLAUDE.md`, and Claude Code then ignores `AGENTS.md`.
- **Hook overlap.** On 5.x, set `OMC_SKIP_HOOKS=keyword-detector,skill-injector` (add `persistent-mode,workflow-drift-guard`
  if they get in the way of pipeline runs). 3.x has no such switch.
- The «Tools» view folds each OMC command into the skill of the same name and hides agent templates.
- Other plugins: [HOOKS › Coexisting with other hooks](HOOKS.md#coexisting-with-other-hooks) lists what each hook can do and how to turn it off.
