#!/usr/bin/env python3
"""PreToolUse hook (Bash · Task|Agent|SendMessage): record the main agent's own pipeline stage for Sidereus.

A Bash description starting with `[pl:<name>/<stage>]` writes <data dir>/plmark/<session_id>.json; `[pl:-]` clears it.
Stores only name/title/t/cwd -- never the description or command (metadata only).
Every untagged Agent/Task in a project with pipelines is denied with a «tag it» reason (nudge).
`--platform <key>` (other CLIs): only a shell command that STARTS with `[pl:<name>/<stage>]` marks (with "hold": 1),
`[pl-end:...]` drops the hold, `[pl:-]` clears. No `--platform` = cc (Claude Code), unchanged.
Fail-open: prints only that deny, always exits 0. Stdlib only, Python 3.9.
"""
import json
import os
import re
import sys
import time

# Same derivation as sidereus/config.py DATA_DIR so the server reads the same folder.
DATA_DIR = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")
MARK_DIR = os.path.join(DATA_DIR, "plmark")
CONFIG_PATH = None   # None = same rule as pipelines_brief.py; patched in tests
NAME = re.compile(r"[a-z0-9-]{1,40}")
TAG = re.compile(r"\[pl:([a-z0-9-]{1,40})/([^\]\n]{1,40})\]")
SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
FIELD = {"Bash": "description", "Agent": "description", "Task": "description",
         "SendMessage": "summary"}
# Same keys as sidereus/ext_store.py EXT_PLAT, plus cc; an unknown --platform does nothing.
PLATFORMS = ("cc", "gemini", "codex", "copilot", "cursor", "cline", "windsurf", "warp", "trae", "zed", "grok",
             "deepseek", "qwen", "kimi", "mistral", "ollama", "perplexity", "huggingface", "meta", "openrouter")
EVENT = {"BeforeTool": "PreToolUse", "AfterTool": "PostToolUse"}   # Gemini names
CAMEL = {"preToolUse": "PreToolUse", "postToolUse": "PostToolUse", "postToolUseFailure": "PostToolUse"}   # Cursor names
SHELL = ("run_shell_command", "shell", "exec_command", "local_shell", "Bash", "Shell")   # Bash only off cc; Shell = Cursor
# ⚠Anchored at the command start: `grep "[pl:"` or a marker inside a script must never count.
MARK = re.compile(r"""^\s*(?:echo\s+|#\s*|:\s+)?["']?\[pl(-end)?:(?:(-)|([a-z0-9-]{1,40})/([^\]\n|]{1,40})(\|fail)?)\]""")


# --- session pipeline dirs: identical block in pl_mark.py · pl_flow.py · pipelines_brief.py (tests compare) ---
# ⚠A session often works in another project than its cwd (`cd ~/other`); reading only <cwd>/.claude/pipelines left it
#   with no brief, nudge or hand-off. Only places the session moved to count (Bash `cd` targets, transcript `cwd`):
#   paths merely read or written gave false matches (a session reading another repo's files got its pipelines).
HOME_DIR = os.path.expanduser("~")             # patched in tests
DIRS_DIR = os.path.join(DATA_DIR, "plbrief")   # <sid>.dirs cache (project paths only); patched in tests
DIRS_TTL, DIRS_TAIL, DIRS_MAX = 60, 256 * 1024, 8
_PLNAME = re.compile(r"[a-z0-9-]{1,40}")
# gitinfo's, plus absolute; plus Windows `cd /d C:\x`, `Set-Location|sl [-Path]`, quoted drive paths with spaces, `~` inside a path (8.3 `RUNNER~1`)
_CD_RE = re.compile(r"(?:^|[\s;&|(])(?:cd(?:\s+/[dD](?=\s+[\"']?[A-Za-z]:))?|(?i:set-location|sl)(?:\s+-(?i:path))?)"
                    r"\s+(?:\"([A-Za-z]:[^\"\n]*)\"|'([A-Za-z]:[^'\n]*)'|[\"']?([A-Za-z0-9_.~/\\][A-Za-z0-9_.\-/\\:~]*))")


def _git_root(d):
    cur = os.path.abspath(d)
    while True:
        if os.path.exists(os.path.join(cur, ".git")):   # dir, or file in a worktree
            return cur
        up = os.path.dirname(cur)
        if up == cur:
            return ""
        cur = up


def _has_pl(d):
    try:
        return any(n.endswith(".json") and _PLNAME.fullmatch(n[:-5])
                   for n in os.listdir(os.path.join(d, ".claude", "pipelines")))
    except OSError:
        return False


def _scan_dirs(tp, cwd):
    """Git roots with pipelines the session moved into in the transcript tail, newest first.
    ⚠The mailbox data dir is skipped: every session touches it for mail, and its pipelines would nudge them all."""
    try:
        size = os.path.getsize(tp)
        with open(tp, "rb") as f:
            if size > DIRS_TAIL:
                f.seek(size - DIRS_TAIL)
                f.readline()
            raw = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    home = HOME_DIR.rstrip(os.sep)
    skip = {os.path.normpath(DATA_DIR), home}
    out, seen, roots = [], set(), set()
    for line in reversed(raw.splitlines()):
        if '"tool_use"' not in line and '"cwd"' not in line:
            continue
        try:
            e = json.loads(line)
            c = (e.get("message") or {}).get("content") if e.get("type") == "assistant" else None
        except Exception:
            continue
        found = [e["cwd"]] if isinstance(e.get("cwd"), str) and os.path.isabs(e["cwd"]) else []
        for b in c if isinstance(c, list) else []:
            inp = b.get("input") if isinstance(b, dict) and b.get("type") == "tool_use" else None
            if not isinstance(inp, dict) or not isinstance(inp.get("command"), str):
                continue
            for m in _CD_RE.finditer(inp["command"]):   # ⚠`cd` targets only, never other path arguments
                t = next((g for g in m.groups() if g), "")
                if t == "~" or t[:2] in ("~/", "~" + os.sep):
                    found.append(home + t[1:])
                elif t and not t.startswith("~"):
                    found.append(os.path.join(cwd, t))   # ⚠an absolute target (/x, C:\x) replaces cwd
            for p in reversed(found):   # newest first: a later `cd` of one command beats an earlier one
                p = os.path.normpath(p)
                if not os.path.normcase(p).startswith(os.path.normcase(home + os.sep)) or p in seen:
                    continue
                seen.add(p)
                r = _git_root(p if os.path.isdir(p) else os.path.dirname(p))
                if r and r not in roots and r not in skip and r != cwd:
                    roots.add(r)
                    if _has_pl(r):
                        out.append(r)
                        if len(out) >= DIRS_MAX:
                            return out
    return out


def session_dirs(ev, every=False):
    """[cwd] + other project roots with pipelines this session works in (cached DIRS_TTL s per session).
    No transcript = [cwd] alone (the old behaviour). `every` = scan even when the cwd has pipelines (pl_flow picks by fit)."""
    cwd, sid, tp = ev.get("cwd"), ev.get("session_id"), ev.get("transcript_path")
    if not (isinstance(tp, str) and os.path.isabs(tp) and isinstance(sid, str) and SID.match(sid)) or (not every and _has_pl(cwd)):
        return [cwd]   # ⚠a cwd with its own pipelines never borrows another project's
    path = os.path.join(DIRS_DIR, sid + ".dirs")
    dirs = None
    try:
        if time.time() - os.path.getmtime(path) < DIRS_TTL:
            with open(path, encoding="utf-8") as f:
                dirs = json.load(f)
    except Exception:
        dirs = None
    if not isinstance(dirs, list):
        dirs = _scan_dirs(tp, cwd)
        try:
            os.makedirs(DIRS_DIR, exist_ok=True)
            tmp = path + ".tmp.%d" % os.getpid()
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dirs, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            pass
    return [cwd] + [d for d in dirs if isinstance(d, str) and os.path.isabs(d) and d != cwd]
# --- end session pipeline dirs ---


def _apply_off(cwd):
    """True when Sidereus's «Apply» is off for `cwd` (same config rule as pipelines_brief.py); any problem = not off."""
    try:
        p = CONFIG_PATH or os.path.expanduser(os.environ.get("MAILBOX_CONFIG") or os.path.join(DATA_DIR, "config.local.json"))
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get("pipeline_apply") or {}
        return ((v.get("projects") or {}).get(cwd) or v.get("mode")) == "off"
    except Exception:
        return False


_FLOW = None   # sibling pl_flow.py, loaded on the first nudge


def _flow():
    """pl_flow module (same folder), or None; HOME_DIR/DATA_DIR follow this module's so tests stay off live files."""
    global _FLOW
    try:
        if _FLOW is None:
            import importlib.util
            sp = importlib.util.spec_from_file_location(
                "pl_flow_nudge", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pl_flow.py"))
            m = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(m)
            _FLOW = m
        _FLOW.HOME_DIR, _FLOW.DATA_DIR = HOME_DIR, DATA_DIR
        return _FLOW
    except Exception:
        return None


def nudge(ev, sid, desc):
    """Deny reason for an untagged Agent/Task in a project with pipelines, else None.

    ⚠Every time, not once per session: a once-only nudge left sessions tagging some dispatches and not others,
    so runs lit only in part. `[pl:-]` is the one-token opt-out for work outside a pipeline.
    """
    cwd = ev.get("cwd")
    if "[pl:" in desc or not (isinstance(cwd, str) and os.path.isabs(cwd)):
        return None
    found = []   # (name, project dir): cwd first, then the projects this session works in
    for d in session_dirs(ev):
        try:
            ns = sorted(n[:-5] for n in os.listdir(os.path.join(d, ".claude", "pipelines"))
                        if n.endswith(".json") and NAME.fullmatch(n[:-5]))
        except OSError:
            continue
        if ns and not _apply_off(d):
            found += [(n, d) for n in ns]
    if not found:
        return None
    count = {}
    for n, _ in found:
        count[n] = count.get(n, 0) + 1
    names = [n if count[n] == 1 else "%s (%s)" % (n, os.path.basename(d)) for n, d in found]
    shown = ", ".join(names[:8]) + (" …" if len(names) > 8 else "")
    where = "This project has" if all(d == cwd for _, d in found) else "This session's projects have"
    # ⚠pipelines pl_flow resolves outside the session's dirs: a session in another repo tagged a relayed run [pl:-]
    fl = _flow()
    ext = [x for x in (fl.known_pipelines(ev, {d for _, d in found}) if fl else []) if not _apply_off(x[1])]
    more = ""
    if ext:
        en = ["%s (%s)" % (n, os.path.basename(d)) for n, d in ext]
        more = " Also valid (known projects): %s." % (", ".join(en[:8]) + (" …" if len(en) > 8 else ""))
    return ("%s pipelines: %s.%s If this work is a pipeline stage, prefix the description with "
            "[pl:<name>/<stage title>]; otherwise prefix [pl:-]." % (where, shown, more))


def _platform(argv):
    if "--platform" not in argv:
        return "cc"
    i = argv.index("--platform") + 1
    return argv[i] if i < len(argv) else ""


def shell_cmd(ti):
    """Command string of a shell tool input, or None. A list (Codex `shell` argv, unverified) gives its last item."""
    c = ti.get("command", ti.get("cmd")) if isinstance(ti, dict) else None
    if isinstance(c, list):
        c = c[-1] if c else None
    return c if isinstance(c, str) else None


def _write(path, rec):
    os.makedirs(MARK_DIR, exist_ok=True)
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, path)


def shell_mark(ev, sid):
    """Other CLIs: a leading shell marker sets / ends / clears the mark. Stores name/title/t/cwd/hold only."""
    if EVENT.get(ev.get("hook_event_name"), ev.get("hook_event_name")) == "PostToolUse":
        return
    cmd = shell_cmd(ev.get("tool_input"))
    m = MARK.match(cmd) if cmd else None
    if not m:
        return
    path = os.path.join(MARK_DIR, sid + ".json")
    if m.group(2):
        try:
            os.remove(path)
        except OSError:
            pass
        return
    title = m.group(4).strip()
    if not title:
        return
    if m.group(1):   # end: the stage is over, so the 45-min hold goes; the plain 2-min window from `t` applies
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except Exception:
            return
        if isinstance(rec, dict) and rec.pop("hold", None) is not None:
            _write(path, rec)
        return
    cwd = ev.get("cwd")
    # ⚠hold: a shell marker is one short command, not a long Bash call; without it the mark died after 2 min.
    _write(path, {"name": m.group(3), "title": title, "t": time.time(),
                  "cwd": cwd if isinstance(cwd, str) else "", "hold": 1})


def norm_ev(ev):
    """Off cc: Cursor camelCase event -> PascalCase; an empty cwd (Cursor tool events) -> first absolute workspace root."""
    if not isinstance(ev, dict):
        return ev
    e = ev.get("hook_event_name")
    if isinstance(e, str) and e in CAMEL:
        ev["hook_event_name"] = CAMEL[e]
    cwd, roots = ev.get("cwd"), ev.get("workspace_roots")
    if not (isinstance(cwd, str) and os.path.isabs(cwd)) and isinstance(roots, list):
        r = [x for x in roots if isinstance(x, str) and os.path.isabs(x)]
        if r:
            ev["cwd"] = r[0]
    return ev


def main(argv=None):
    plat = _platform(sys.argv[1:] if argv is None else argv)
    if plat not in PLATFORMS:
        return
    ev = json.loads(sys.stdin.read() or "{}")
    if plat != "cc":
        ev = norm_ev(ev)
        sid = ev.get("session_id") if isinstance(ev, dict) else None
        if isinstance(sid, str) and SID.match(sid) and ev.get("tool_name") in SHELL:
            shell_mark(ev, sid)
        return
    # ⚠A tagged Agent/Task/SendMessage only CLEARS main's mark: dispatching means main hands off and waits,
    # it is not working that stage. Only Bash sets it.
    tool = ev.get("tool_name") if isinstance(ev, dict) else None
    field = FIELD.get(tool)
    if not field:
        return
    sid = ev.get("session_id")
    if not isinstance(sid, str) or not SID.match(sid):
        return
    ti = ev.get("tool_input") or {}
    desc = ti.get(field) if isinstance(ti, dict) else None
    if not isinstance(desc, str):
        return
    if tool in ("Agent", "Task"):
        why = nudge(ev, sid, desc)
        if why:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "permissionDecision": "deny", "permissionDecisionReason": why}}))
            return
    path = os.path.join(MARK_DIR, sid + ".json")
    if "[pl:-]" in desc or (tool != "Bash" and "[pl:" in desc):
        try:
            os.remove(path)
        except OSError:
            pass
        return
    m = TAG.search(desc)
    if not m:
        return
    title = m.group(2).strip()
    if not title:
        return
    cwd = ev.get("cwd")
    _write(path, {"name": m.group(1), "title": title, "t": time.time(),
                  "cwd": cwd if isinstance(cwd, str) else ""})


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage; hook JSON is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
