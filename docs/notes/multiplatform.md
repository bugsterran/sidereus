# Multi-platform (Windows · Linux) support — deferred investigation

⚠Do not confuse this with a similarly named job — **external CLI (Gemini · Codex) integration** is `docs/notes/ext-agents.md`.

2026-09-22 measured; Windows phase 1 shipped 2026-09-28. README states Windows as **supported but untested** on a real machine.
⚠Line refs from the 2026-09-22 count pointed into the old single-file `chat_server.py` (now ~320 lines) and are dropped — the Mac-only list lives in `sidereus/config.py:48-57` (`IS_MAC` gate).

★What blocks it is **external commands**, not syntax — **0** `sys.platform` · `platform.system()` branches, 0 POSIX-only
stdlib modules, 0 `chmod` · `0o600` · `umask`, 0 frontend `⌘` · `metaKey` · `navigator.platform`.

## Blockers

| Item | Count | Typical spot | Replacement |
|---|---|---|---|
| Mac-only external commands | **9** (of 22 `subprocess`) | list below | varies per item |
| ~~`text=True` without encoding~~ done | 15 | `sidereus/live_probe.py` `agent_view()` etc. | `encoding="utf-8", errors="replace"` |
| ~~`open()` without encoding~~ done | 12 | `sidereus/bus.py` `_atomic_write()` · `mailbox_core.py` | `encoding="utf-8"` |
| `os.replace` (no inter-process lock) | **8** | `sidereus/bus.py` `_atomic_write` · `hooks/room_auto.py:46` | retry wrapper |
| launchd services | **3 plists + 8 docs** | `~/Library/LaunchAgents/<label>.*.plist` | systemd user unit / Task Scheduler |
| POSIX assumption in path building | **2** | `sidereus/ident.py` `_cwd_from_slug()` · `_proj_name()` | `os.path` · `pathlib` |
| ext-hooks example command lines | **17** (3 files) | `ext-hooks/*-example.json` | «6» below |

**9 Mac-only commands** — `ps` (`-Ao`, `-Ewwo`) · `lsof` (2) ·
`pmset -g log` · `security find-generic-password` · `caffeinate` ·
`sysctl -n kern.boottime` · `open`. The other 13 are portable: `git` 8 · `claude`/`ccusage` 4.
⚠The `-E` (environment) in `ps -Ewwo` is BSD-only — Linux uses `/proc/<pid>/environ`.

- The 4 `ps` · `lsof` spots ⇒ all covered by `psutil` (`process_iter(['pid','ppid','cmdline','cwd'])`).
  ⚠But it breaks the **«no external libraries» rule** (`AGENTS.md`) — decide that first.
- `pmset` ⇒ Linux `journalctl -u systemd-suspend` · Windows `powercfg /sleepstudy`. Different formats, so new parsers.
- `security` ⇒ Linux `secret-tool` (libsecret) · Windows DPAPI/Credential Manager.
- `caffeinate` ⇒ Linux `systemd-inhibit --what=idle` · Windows `SetThreadExecutionState` (ctypes).
- `sysctl kern.boottime` ⇒ Linux `/proc/uptime` · Windows `GetTickCount64`.
- `open <url>` ⇒ `webbrowser.open()` covers all 3 platforms (cheapest).
- Service startup ⇒ Linux `systemd --user` unit (`Restart=on-failure` + backup via an `OnCalendar` timer ·
  `Persistent=true` matches launchd catch-up runs) · Windows `schtasks /sc onlogon` («run missed task as soon as possible») or NSSM.

## Big if touched

1. **Session detection, 4 spots** (`ps` · `lsof`) — without a replacement, the session list · cwd · busy state go entirely empty. The screen rests on it.
2. **`_cwd_from_slug`** (`sidereus/ident.py:146`) — turns the slug back into `/`. It cannot produce Windows `C:\`,
   so **every project name falls to `?`** (same symptom as seen on 2026-08-19).
3. **`security find-generic-password`** — without it the quota panel is gone.

## Doable now (without porting)

1. ~~Pin encoding in 27 spots~~ **done 2026-09-22** — `encoding="utf-8"` on 15 `subprocess` + 12 `open()` (reads use `errors="replace"`).
   ⚠Do not drop `errors="replace"` — specifying the encoding makes it strict and broken bytes raise (measured: `text=True` alone raises the same).
2. ~~Gather the 9 Mac-only calls in one place~~ **done 2026-09-22** — `IS_MAC = sys.platform == "darwin"` (`sidereus/config.py:56`) + comment listing Mac-only features.
   All 9 pass through the gate, and **on non-Mac only that feature is silently disabled** (each function's existing «not found» value: `[]` · `{}` · `None` · `0.0`). `open <url>` replaced by `webbrowser.open()` (a path that never runs, since the plist uses `--no-open`).
   ⚠Disabled only, **not a replacement** — on Linux and Windows the session list is still empty («Big if touched 1» above).

## Outside the code

- **Other CLI hook paths** — the 17 `"command"` entries in `ext-hooks/{codex,gemini,generic}-*.json` are
  fixed to `/usr/bin/python3 ~/.mailbox-mcp/…` ⇒ on Windows
  `"py -3 C:\\Users\\<id>\\.mailbox-mcp\\ext-hooks\\ext_hook.py --platform X"`; **it is JSON, so backslashes are doubled**.
- **Which Python runs it** — the `/usr/bin/python3` (3.9.6) assumption is baked into the gate rule (`AGENTS.md`) and the 17 lines above.
- `cc-status` (Mach-O without source) is not in this project but in 3 hooks in `~/.claude/settings.json` — separate matter.

## Windows phase 1 (2026-09-28) · left for phase 2

Phase 1 = start only (done): `sidereus_cli.py start|stop|status [--install-service]` (schtasks logon task) · `file_lock`/`pid_alive` (sidereus/config.py) · Mac-only features disabled.
⚠After phase 1 the session list is still empty — phase 2 is below.

- Session detection (4 `ps` · `lsof` spots) ⇒ ctypes `CreateToolhelp32Snapshot` (pid · ppid · exe) + `NtQueryInformationProcess` (cmdline · cwd from the PEB).
- Quota token (`security find-generic-password`) ⇒ ctypes `CredReadW` (Credential Manager).
- ~~Stay awake (`caffeinate`) ⇒ `SetThreadExecutionState`~~ **done** — `sidereus/awake.py:33`.
- Boot time (`sysctl kern.boottime`) ⇒ `GetTickCount64`.
- Sleep log (`pmset -g log`) ⇒ `powercfg /sleepstudy` (or event log Kernel-Power) parser.
- `watch.sh` · `backup.sh` · `backup-data.sh` ⇒ port to PowerShell or Python.
