#!/usr/bin/env python3
"""Surfaces pending mailbox room invites · unregistered identity · wake-hook guidance into the session context.

Why a hook: where the mailbox MCP is registered (checked: `mailbox_registered`), **tools are not missing**. What is
missing is notification — a session sees invites only when it calls `mailbox_room` itself, and never if it has no reason to.
`SessionStart` / `UserPromptSubmit` put stdout straight into the session context (official docs),
so one printed line lets the session read it and join by itself.

Design:
- No pending invites → **print nothing** — the hook runs on every prompt, so silence is the default.
- UserPromptSubmit announces **only new invites** (already-announced ones are remembered in a state file). Repeating
  the same invite every prompt eats context and gets ignored.
- Unregistered/wake notices are emitted **only at SessionStart**. Repeating them every prompt is noise.
- On failure, pass silently. A notification must never block the session.

Files:
- `identity.json`      : `{"<cwd>": "<id>"}` — identity registry (written by mailbox_login with remember)
- `identity-skip.json` : `{"<cwd>": true}` — paths that **declined** the unregistered notice. If present, no notice.
                         (Absence is normal. With no file it just passes silently)
- `config.local.json`  : `mailbox_watch = {mode, projects: {<abs path>: "on"|"off"}}` — off = no wake notice.
"""
import json
import os
import re
import subprocess
import sys
import time

_UP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isfile(os.path.join(_UP, "mailbox_config.py")):   # pipx/uv: sidereus/_bundle/hooks -> site-packages
    _UP = os.path.dirname(os.path.dirname(_UP))
sys.path.insert(0, _UP)
import mailbox_config  # noqa: E402

STORE = mailbox_config.data_dir()
ROOMS = os.path.join(STORE, "rooms.json")
IDENTITY = os.path.join(STORE, "identity.json")
SKIP = os.path.join(STORE, "identity-skip.json")
SEEN = os.path.join(STORE, "invite-seen.json")
CONFIG = mailbox_config.config_path()
ACCT_DIR = os.path.join(STORE, "acct")      # <sid> -> config dir (metadata only; read by sidereus.claude_roots)
ACCT_KEEP_S = 30 * 86400
ACCT_SCAN_MAX = 2000
# /clear pairing: SESSPID_DIR/<claude pid> = current sid; a clear appends {at, pid, old, new} (read by sidereus.sess_clear).
SESSPID_DIR = os.path.join(STORE, "sesspid")
CLEAR_FILE = os.path.join(STORE, "clears.jsonl")
CLEAR_MAX_BYTES = 128 * 1024        # over this, keep the newest CLEAR_KEEP lines
CLEAR_KEEP = 300
_SHELLS = {"sh", "bash", "zsh", "dash", "fish", "ksh", "tcsh", "csh"}
_SID_RE = re.compile(r"^[0-9a-zA-Z-]{8,64}$")


def _tilde(p):
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p.startswith(h + "/") else p


# Same rule as sidereus.config.claude_json (standalone hook: inlined, not imported).
CLAUDE_JSON = (os.path.join(os.path.expanduser(os.environ["CLAUDE_CONFIG_DIR"]), ".claude.json")
               if os.environ.get("CLAUDE_CONFIG_DIR") else os.path.expanduser("~/.claude.json"))


def mailbox_registered(cwd):
    """Is a mailbox MCP server visible to this session (user/project scope in ~/.claude.json, or cwd/.mcp.json)?

    ⚠mailbox-mcp is a separate package: without it the login prompt names tools the session does not have."""
    def has(servers):
        return isinstance(servers, dict) and any("mailbox" in str(k).lower() for k in servers)
    d = load(CLAUDE_JSON, {})
    if isinstance(d, dict):
        if has(d.get("mcpServers")):
            return True
        proj = (d.get("projects") or {}).get(cwd) if isinstance(d.get("projects"), dict) else None
        if isinstance(proj, dict) and has(proj.get("mcpServers")):
            return True
    m = load(os.path.join(cwd, ".mcp.json"), {}) if cwd else {}
    return isinstance(m, dict) and has(m.get("mcpServers"))


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def whoami(cwd):
    """(id, source). source: identity (path is in identity.json verbatim) · parent (ancestor path) · env · ""

    ★Resolution order matches the MCP server (`server.py:_me()`): identity.json[cwd] → MAILBOX_ME → none.
      env used to be checked first, but a global MAILBOX_ME was hardcoded in `~/.claude.json`, so
      **every unregistered project took someone else's id as its own**. The global env was removed;
      env now remains only for deliberate declarations, so it is checked last.
    ★The `default` fallback in `identity.json` was removed too — it promoted a guess to a real name.
    """
    ident = load(IDENTITY, {})
    if not isinstance(ident, dict):
        ident = {}
    if cwd and cwd in ident:
        return ident[cwd], "identity"
    # Check ancestor paths too — a session may start in a subdirectory. But this is **not a confirmed identity**
    # (see `is_registered` below): both server and viewer accept only the exact path key as identity.
    if cwd:
        p = os.path.dirname(cwd)
        while p and p != "/":
            if p in ident:
                return ident[p], "parent"
            up = os.path.dirname(p)
            if up == p:   # ⚠a Windows drive root (C:\\) is its own dirname and never equals "/": stop here
                break
            p = up
    env = (os.environ.get("MAILBOX_ME") or "").strip()
    if env:
        return env, "env"
    return "", ""


def is_registered(src):
    """Is the identity **confirmed**? Confirmed = this exact path is in identity.json.

    ★Why exact paths only: the MCP server that permits writes (`identity.json.get(_PROJECT)`) and
      the viewer that picks invite targets (`mboxSrc === 'identity'`) both look at **exact path keys only**.
      Ids picked up via ancestor path/env are not identities there, so they count as unregistered here too.
      (In practice a single home-directory mapping makes everything under home 'registered' — that is not confirmed.)
    """
    return src == "identity"


def skipped(cwd):
    """Has the user chosen 'do not register' for this path?"""
    data = load(SKIP, {})
    if isinstance(data, dict):
        return bool(data.get(cwd))
    if isinstance(data, list):
        return cwd in data
    return False


def watch_mode(cwd):
    """'on' | 'off' from config `mailbox_watch` — longest project prefix of cwd wins, else `mode`; missing = on.

    ⚠Reads the file directly: mailbox_config.load() drops unknown keys, and a hook must not import sidereus/*."""
    cfg = load(CONFIG, {})
    mw = cfg.get("mailbox_watch") if isinstance(cfg, dict) else None
    if not isinstance(mw, dict):
        return "on"
    best, val = -1, mw.get("mode")
    here = os.path.normcase(os.path.normpath(cwd)) if cwd else ""   # ⚠normcase: Windows ignores case, `/` = `\`
    projects = mw.get("projects")
    # ⚠Same tie-break as sidereus/prefs.watch_on: keys equal after normcase (Windows case/slash) rank by exact spelling,
    # then sorted order — never dict order, or the result flips with the order keys were saved in.
    exact = -1
    for p in sorted(k for k in (projects if isinstance(projects, dict) else {}) if isinstance(k, str) and k):
        v = projects[p]
        root = os.path.normcase(os.path.normpath(os.path.expanduser(p)))
        rank = (len(root), int(p == cwd))
        if (here == root or here.startswith(root.rstrip(os.sep) + os.sep)) and rank > (best, exact):
            (best, exact), val = rank, v
    return "off" if val == "off" else "on"


# ★Monitor is off by company policy (DISABLE_TELEMETRY). New mail wakes the session via the Stop async hook
#   `mailbox_wake.py` (asyncRewake) — never tell a session to start Monitor / watch.sh.
WAKE_EN = ("New mail wakes this session via the Stop hook (mailbox_wake) — do not start Monitor or watch.sh."
           " When woken, read it with mailbox_inbox.")
# Codex has no mailbox_wake/Monitor: ext-hooks/gemini_mail_stop.py --platform codex holds the turn end once on new mail.
WAKE_EN_CODEX = "New mail is delivered at turn end by the Stop hook — when it arrives, read it with mailbox_inbox."
PLATFORM = "cc"   # set from --platform in main(); only "codex" changes anything


def notice_unregistered(cwd, watch=True):
    """Unregistered-identity notice. SessionStart only — the goal is for the session to ask the user and register."""
    folder = os.path.basename(cwd.rstrip("/")) or "unknown"
    # Model-facing text is English only; the session asks the user in the user's own language.
    print("\n".join([
        f"[mailbox] This project has no registered mailbox identity (path: {cwd}).",
        "Until it is registered it cannot receive room invites, and posting is blocked by the identity guard.",
        'Ask the user with AskUserQuestion, in the user\'s language — "This project has no mailbox id. Register one?"',
        f"  Options: (1) register as `{folder}`  (2) type a name  (3) no (don't ask again)",
        'Register with mailbox_login {as_id:"<name>"} — remember (default) saves it to identity.json.',
    ] + ([WAKE_EN] if watch else []) + [
        f"If the user picks (3), add this path to {_tilde(SKIP)}.",
        "Do not choose an id yourself before the user answers.",
    ]))


def notice_wake(me):
    """Registered session: one line saying the Stop hook wakes it. SessionStart only.

    ⚠No «watcher off» warning any more — without Monitor that is the normal state."""
    cx = PLATFORM == "codex"
    print(f"[mailbox] id `{me}` · " + (WAKE_EN_CODEX if cx else WAKE_EN))


def codex_id(cwd):
    """Codex session's mailbox id: identity.json["codex:<realpath>"] or "<basename>-codex"; "" if it equals a Claude id.

    ⚠Same rule as ext-hooks/gemini_mail_stop.py gemini_id (inlined: standalone hook). identity.json[cwd] is the Claude id."""
    ident = load(IDENTITY, {})
    ident = ident if isinstance(ident, dict) else {}
    real = os.path.realpath(cwd)
    me = ident.get("codex:" + real)
    if not isinstance(me, str) or not me:
        me = os.path.basename(real.rstrip("/")) + "-codex"
    return "" if me in {v for k, v in ident.items() if not str(k).startswith("codex:")} else me


def _platform(argv):
    """`--platform <key>` value, else "cc". ⚠Flag only: the SessionStart payload carries no verified Codex marker."""
    if "--platform" not in argv:
        return "cc"
    i = argv.index("--platform") + 1
    return argv[i] if i < len(argv) else ""


def record_acct(event, sid):
    """SessionStart: write ACCT_DIR/<sid> = this session's Claude config dir; prune old records. Errors are silent."""
    if event != "SessionStart" or not isinstance(sid, str) or not _SID_RE.match(sid):
        return
    try:
        cfg = os.path.abspath(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"))
        os.makedirs(ACCT_DIR, exist_ok=True)
        path = os.path.join(ACCT_DIR, sid)
        try:
            with open(path, encoding="utf-8") as f:
                same = f.read() == cfg + "\n"
        except OSError:
            same = False
        if same:
            os.utime(path, None)
        else:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(cfg + "\n")
            os.replace(tmp, path)
        cut = time.time() - ACCT_KEEP_S
        with os.scandir(ACCT_DIR) as it:
            for i, e in enumerate(it):
                if i >= ACCT_SCAN_MAX:
                    break
                try:
                    if e.is_file(follow_symlinks=False) and e.stat(follow_symlinks=False).st_mtime < cut:
                        os.unlink(e.path)
                except OSError:
                    pass
    except Exception:
        pass


def _prune(d):
    """Delete files in `d` older than ACCT_KEEP_S (bounded scan)."""
    cut = time.time() - ACCT_KEEP_S
    with os.scandir(d) as it:
        for i, e in enumerate(it):
            if i >= ACCT_SCAN_MAX:
                break
            try:
                if e.is_file(follow_symlinks=False) and e.stat(follow_symlinks=False).st_mtime < cut:
                    os.unlink(e.path)
            except OSError:
                pass


def _claude_pid():
    """Pid of the Claude process: the hook's parent, or its parent when the hook was launched through a shell."""
    p = os.getppid()
    if sys.platform == "win32":
        return p          # ⚠no `ps` on Windows (Git Bash's MSYS ps has no -o); a spawn attempt only adds hook latency
    try:
        r = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(p)], capture_output=True, text=True, timeout=2)
        parts = r.stdout.strip().split(None, 1)
        if len(parts) == 2 and os.path.basename(parts[1]).lstrip("-") in _SHELLS and int(parts[0]) > 1:
            return int(parts[0])
    except Exception:
        pass
    return p


def record_clear(event, source, sid):
    """SessionStart: SESSPID_DIR/<pid> = sid; on source "clear" append the pid's previous sid -> new sid. Errors are silent.

    ⚠`claude agents` keeps listing the pre-/clear sid; this pid record is the only link between the two."""
    if event != "SessionStart" or not isinstance(sid, str) or not _SID_RE.match(sid):
        return
    try:
        pid = int(_claude_pid())
        if pid <= 1:
            return
        os.makedirs(SESSPID_DIR, exist_ok=True)
        path = os.path.join(SESSPID_DIR, str(pid))
        if source == "clear":
            try:
                with open(path, encoding="utf-8") as f:
                    old = f.read().strip()
            except OSError:
                old = ""
            if _SID_RE.match(old) and old != sid:
                line = json.dumps({"at": int(time.time()), "pid": str(pid), "old": old, "new": sid}) + "\n"
                with open(CLEAR_FILE, "a", encoding="utf-8") as f:
                    f.write(line)
                if os.path.getsize(CLEAR_FILE) > CLEAR_MAX_BYTES:
                    with open(CLEAR_FILE, encoding="utf-8") as f:
                        keep = f.readlines()[-CLEAR_KEEP:]
                    tmp = CLEAR_FILE + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.writelines(keep)
                    os.replace(tmp, CLEAR_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(sid + "\n")
        os.replace(tmp, path)
        _prune(SESSPID_DIR)
    except Exception:
        pass


def main(argv=None):
    global PLATFORM
    PLATFORM = _platform(sys.argv[1:] if argv is None else argv)
    if PLATFORM not in ("cc", "codex"):
        return
    try:
        raw = sys.stdin.read()
        inp = json.loads(raw) if raw.strip() else {}
    except Exception:
        inp = {}

    event = inp.get("hook_event_name") or ""
    cwd = inp.get("cwd") or os.getcwd()
    sid = inp.get("session_id") or ""
    if PLATFORM == "codex":   # ⚠acct/sesspid records are Claude config dir / Claude pid; Codex ids always have a default
        me = codex_id(cwd)
        if event == "SessionStart" and me and watch_mode(cwd) == "on":
            notice_wake(me)
    else:
        record_acct(event, sid)
        record_clear(event, inp.get("source") or "", sid)
        me, src = whoami(cwd)

    # Identity/wake notices only once at SessionStart. They are mutually exclusive.
    if event == "SessionStart" and PLATFORM == "cc":
        watch_on = watch_mode(cwd) == "on"
        if not is_registered(src):
            if not skipped(cwd) and mailbox_registered(cwd):
                notice_unregistered(cwd, watch_on)
        elif watch_on:
            notice_wake(me)

    # --- from here: the existing invite notice (unchanged) ---
    if not me:
        return

    rooms = load(ROOMS, {})
    pending = []
    for name, r in (rooms.items() if isinstance(rooms, dict) else []):
        if not isinstance(r, dict):
            continue
        if me in (r.get("invited") or []) and me not in (r.get("members") or []):
            pending.append((name, r))
    if not pending:
        return

    # UserPromptSubmit: new ones only — don't repeat the same invite every turn
    if event == "UserPromptSubmit":
        seen = load(SEEN, {})
        key = sid or me
        before = set(seen.get(key) or [])
        fresh = [(n, r) for n, r in pending if n not in before]
        if not fresh:
            return
        seen[key] = sorted(before | {n for n, _ in pending})
        try:
            with open(SEEN, "w", encoding="utf-8") as f:
                json.dump(seen, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        pending = fresh

    lines = [f"[mailbox] {len(pending)} pending room invite(s) — your id is `{me}`."]
    for name, r in pending:
        who = ", ".join(r.get("members") or []) or "none"
        topic = r.get("topic") or ""
        lines.append(f'  · **{name}**' + (f" — {topic}" if topic else ""))
        lines.append(f"    members: {who}")
        lines.append(f'    to join: mailbox_room {{ action: "join", room: "{name}" }}')
    lines.append("Unless the user told you to enter the room, do not join it yourself — just be aware the invite exists.")
    print("\n".join(lines))


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage; hook output is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    # ⚠Codex parses SessionStart stdout that starts with `[` or `{` as JSON and fails the hook on «[mailbox] …»,
    #   so under --platform codex the text goes out wrapped as hookSpecificOutput.additionalContext.
    import contextlib
    import io
    _cx = _platform(sys.argv[1:]) == "codex"
    _buf = io.StringIO()
    try:
        with (contextlib.redirect_stdout(_buf) if _cx else contextlib.nullcontext()):
            main()
    except Exception:
        pass          # a notification failure must never block the session
    if _cx and _buf.getvalue().strip():
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": _buf.getvalue().rstrip("\n")}}, ensure_ascii=False))
