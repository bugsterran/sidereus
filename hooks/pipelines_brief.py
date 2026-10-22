#!/usr/bin/env python3
"""SessionStart + UserPromptSubmit hook: tells a session which pipelines its project has (`<cwd>/.claude/pipelines/*.json`).

New pipelines reach agent sessions automatically, without being told each time.
Output = SessionStart JSON with `additionalContext` (one line per pipeline + how to run one), at most MAX_BYTES.
Sidereus's «Apply» mode (config `pipeline_apply`) picks the how-to line (auto / ask first) or silences the hook (off).
⚠Metadata only: name · title · use · stage titles · missing agent names — never `task` or `rules` text.
UserPromptSubmit re-sends the brief only when the pipeline set changed since this session's last brief
(fingerprint in <data dir>/plbrief/<sid>) -- a pipeline created mid-session is otherwise never announced.
⚠Never blocks a session: any failure prints nothing and exits 0. Stdlib only, Python 3.9 (/usr/bin/python3).
"""
import glob
import json
import os
import hashlib
import re
import sys
import time

MAX_BYTES = 2560   # ⚠the how-to grew by the skip/model/SendMessage tag rules; six pipeline lines must still fit
CLAUDE_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")   # user agents root (sidereus.config.claude_home rule); patched in tests
BUILTIN = {"general-purpose", "Explore", "Plan", "main", "claude"}   # main/claude = orchestrator stage (pl_flow.NO_AGENT, JS PL_BUILTIN_AG)
_NAME = re.compile(r"[a-z0-9-]{1,40}")   # same file-stem rule as sidereus/pipeline_schema.py; `_defaults.json` etc. are skipped
_NAME_AG = re.compile(r"[A-Za-z0-9_.-]{1,64}")   # agent names echoed only when they look like a file stem
_RUN = ("follow .claude/pipelines/<name>.json yourself with the Agent tool "
        "(stage order, agent, model, skill, gate, onFail; a stage skill means its prompt says Follow the <skill> skill.); start each stage's Agent description with "
        "[pl:<name>/<stage title>] and pass its agent/model as subagent_type/model. "
        "Skip a stage only after a Bash described [pl-skip:<name>/<stage title>] <reason>; another model: "
        "[pl-model:<name>/<stage title>=<model>]; another agent: [pl-agent:<name>/<stage title>=<agent>]. In a run, SendMessage summaries start with the stage tag or [pl:-]. "
        "A stage whose agent is not installed runs as general-purpose with the same task.")
HOW = "Default = run the pipeline directly: " + _RUN
HOW_ASK = ("Before starting work on a request that fits one of these pipelines, ask the user which to use "
           "(AskUserQuestion: the fitting pipelines + «파이프라인 없이 진행»), then run the choice; "
           "questions and one-line fixes do not ask. To run one: " + _RUN)
# Codex has no Agent tool / SendMessage; pl_mark.py --platform codex marks stages by a leading shell `[pl:]` marker.
_RUN_CODEX = ("follow .claude/pipelines/<name>.json yourself, doing each stage's task in order "
              "(gate, onFail; stage agent/model are Claude settings, a stage skill means follow that skill). "
              "Start each stage with a shell command echo \"[pl:<name>/<stage title>]\" and end it with "
              "echo \"[pl-end:<name>/<stage title>]\" (\"|fail\" before \"]\" when its gate failed); echo \"[pl:-]\" clears.")
HOW_CODEX = "Default = run the pipeline directly: " + _RUN_CODEX
HOW_ASK_CODEX = ("Before starting work on a request that fits one of these pipelines, ask the user which to use "
                 "(the fitting pipelines + «파이프라인 없이 진행»), then run the choice; "
                 "questions and one-line fixes do not ask. To run one: " + _RUN_CODEX)
# Sidereus's «Apply» setting (sidereus/prefs.py `pipeline_apply`): auto = HOW, ask = HOW_ASK, off = no output.
BRIEF_DIR = os.path.join(os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp"), "plbrief")   # patched in tests
SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
CONFIG_PATH = None   # None = $MAILBOX_CONFIG or ($MAILBOX_DIR or ~/.mailbox-mcp)/config.local.json; patched in tests
DATA_DIR = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")


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


def _mode(cwd):
    """auto | ask | off for `cwd` (exact-path override, else global); ⚠any problem = auto (the old behaviour)."""
    try:
        p = CONFIG_PATH or os.path.expanduser(os.environ.get("MAILBOX_CONFIG") or os.path.join(
            os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp", "config.local.json"))
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get("pipeline_apply") or {}
        m = (v.get("projects") or {}).get(cwd) or v.get("mode")
        return m if m in ("auto", "ask", "off") else "auto"
    except Exception:
        return "auto"


def _clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


CODE_DIR = None   # None = Sidereus code dir found like pl_flow._score_script; patched in tests


def _is_code(d):
    """True when `d` is the Sidereus repo itself (its `"builtin": true` pipelines are hidden); unresolved = False."""
    for c in ([CODE_DIR] if CODE_DIR else [os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DATA_DIR]):
        if os.path.isfile(os.path.join(c, "sidereus", "config.py")):
            return os.path.realpath(c) == os.path.realpath(d)
    return False


def _have(cwd):
    """Agent names installed for `cwd`: stems of project and user `.claude/agents/*.md`."""
    out = set()
    for d in (os.path.join(cwd, ".claude", "agents"), os.path.join(CLAUDE_DIR, "agents")):
        out.update(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(d, "*.md")))
    return out


def _skill(s):
    """« (skill x)» suffix for a stage that names a skill (name only, filtered like agent names)."""
    k = s.get("skill")
    return " (skill %s)" % k if isinstance(k, str) and _NAME_AG.fullmatch(k) else ""


def _line(P, name, have=None):
    S = [s for s in P.get("stages") or [] if isinstance(s, dict) and isinstance(s.get("title"), str)]
    if not S:
        return None
    out = "- %s — %s" % (name, _clip(P.get("title") or name, 80))
    if isinstance(P.get("use"), str) and P["use"].strip():
        out += " · when: " + _clip(P["use"], 120)
    out += " · stages: " + " → ".join(_clip(s["title"], 24) + _skill(s) for s in S)
    miss = []
    for s in S:
        a = s.get("agent")
        if isinstance(a, str) and _NAME_AG.fullmatch(a) and a not in BUILTIN and a not in (have or set()) and a not in miss:
            miss.append(a)
    if miss:
        out += " · missing agents (run as general-purpose): " + ", ".join(miss)
    return out


def _short(d):
    h = HOME_DIR.rstrip(os.sep) + os.sep
    return "~/" + d[len(h):] if d.startswith(h) else d


def brief(cwd, extra=(), plat="cc"):
    """additionalContext text for project `cwd` plus the session's other projects `extra`, or "" when none has
    readable pipelines. Another project's pipeline is named «name (path)». plat "codex" = shell-marker how-to."""
    if not (isinstance(cwd, str) and os.path.isabs(cwd)):
        return ""
    lines, mode, other = [], None, False
    for d in [cwd] + [x for x in extra if x != cwd]:
        m = _mode(d)
        if m == "off":
            continue
        have, got = _have(d), False
        for p in sorted(glob.glob(os.path.join(d, ".claude", "pipelines", "*.json"))):
            name = os.path.basename(p)[:-5]
            if not _NAME.fullmatch(name):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    P = json.load(f)
                shown = name if d == cwd else "%s (%s)" % (name, _short(d))
                # builtin = Sidereus plumbing started by its own button; ⚠honoured only in the Sidereus repo
                ln = _line(P, shown, have) if isinstance(P, dict) and not (P.get("builtin") is True and _is_code(d)) else None
            except Exception:   # bad JSON / unreadable file: skip that one
                ln = None
            if ln:
                lines.append(ln)
                got = True
        mode = mode or (m if got else None)
        other = other or (got and d != cwd)
    if not lines:
        return ""
    if plat == "codex":
        how = HOW_ASK_CODEX if mode == "ask" else HOW_CODEX
    else:
        how = HOW_ASK if mode == "ask" else HOW
    head = ("Pipelines (.claude/pipelines/ of this project, or of the project in parentheses):" if other
            else "Pipelines in this project (.claude/pipelines/):")
    size = lambda xs: len("\n".join([head] + xs + [how]).encode("utf-8"))
    kept = []
    for i, ln in enumerate(lines):
        more = "- … +%d more (see .claude/pipelines/)" % (len(lines) - i)
        if size(kept + [ln]) > MAX_BYTES or (i + 1 < len(lines) and size(kept + [ln, more]) > MAX_BYTES):
            kept.append(more)
            break
        kept.append(ln)
    while kept and size(kept) > MAX_BYTES:   # the «more» marker itself did not fit
        kept.pop()
    return "\n".join([head] + kept + [how]) if kept else ""


def _stat_key(dirs):
    """Cheap key: one listdir + stats of the pipeline files per project (changes on any add/edit/remove)."""
    parts = []
    for root in dirs:
        d = os.path.join(root, ".claude", "pipelines")
        try:
            names = sorted(n for n in os.listdir(d) if n.endswith(".json") and _NAME.fullmatch(n[:-5]))
        except OSError:
            names = []
        parts.append(root)
        for n in names:
            try:
                st = os.stat(os.path.join(d, n))
                parts.append("%s:%d:%d" % (n, st.st_mtime_ns, st.st_size))
            except OSError:
                pass
    return hashlib.sha1("\n".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()


def _content_key(dirs):
    """Pipeline names + stage titles: an edit that changes neither (task text, model) does not re-brief."""
    parts = []
    for root in dirs:
        parts.append(root)
        for p in sorted(glob.glob(os.path.join(root, ".claude", "pipelines", "*.json"))):
            name = os.path.basename(p)[:-5]
            if not _NAME.fullmatch(name):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    P = json.load(f)
                S = [s["title"] for s in P.get("stages") or [] if isinstance(s, dict) and isinstance(s.get("title"), str)]
            except Exception:
                S = []
            parts.append(name + "=" + "\x1f".join(S))
    return hashlib.sha1("\n".join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()


def _changed(sid, dirs, first):
    """True when this session should get the brief now; records the fingerprint either way.
    ⚠Hashes only -- the file never holds names or titles."""
    path = os.path.join(BRIEF_DIR, sid)
    sk = _stat_key(dirs)
    try:
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        old = old if isinstance(old, dict) else {}
    except Exception:
        old = {}
    if not first and old.get("s") == sk:
        return False
    ck = _content_key(dirs)
    # No record yet on a prompt (session predates this hook): brief only if there is something to say.
    hit = first or (old.get("c") != ck if old else ck != hashlib.sha1("\n".join(dirs).encode("utf-8"), usedforsecurity=False).hexdigest())
    try:
        os.makedirs(BRIEF_DIR, exist_ok=True)
        tmp = path + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"s": sk, "c": ck}, f)
        os.replace(tmp, path)
    except OSError:
        return first   # ⚠cannot record: stay silent on prompts rather than repeat the brief every turn
    return hit


def _platform(argv):
    """`--platform <key>` value, else "cc". ⚠Flag only: the SessionStart payload carries no verified Codex marker."""
    if "--platform" not in argv:
        return "cc"
    i = argv.index("--platform") + 1
    return argv[i] if i < len(argv) else ""


def main(argv=None):
    plat = _platform(sys.argv[1:] if argv is None else argv)
    if plat not in ("cc", "codex"):
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            return 0
        cwd = data.get("cwd")
        event = "UserPromptSubmit" if data.get("hook_event_name") == "UserPromptSubmit" else "SessionStart"
        sid = data.get("session_id")
        dirs = [cwd]
        if isinstance(sid, str) and SID.match(sid) and isinstance(cwd, str) and os.path.isabs(cwd):
            dirs = session_dirs(data)
            if not _changed(sid, dirs, event == "SessionStart"):
                return 0
        elif event == "UserPromptSubmit":
            return 0
        text = brief(cwd, dirs[1:], plat)
        if text:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
                                        ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage; hook JSON is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    sys.exit(main())
