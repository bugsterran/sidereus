#!/usr/bin/env python3
"""Pipeline flow hook: keeps a tagged pipeline run on its stage order and hands the main agent the next step.

PreToolUse (Task|Agent|SendMessage, Bash): a `[pl:<name>/<stage>]` tag opens/advances a run in
<data dir>/plmark/<session_id>.runs.json and denies: a jump past unrun, undeclared stages · an unknown stage title ·
an Agent/Task whose subagent_type or model is not the stage's · an untagged SendMessage while a run is open.
Bash descriptions `[pl-skip:<name>/<stage>]`, `[pl-model:<name>/<stage>=<model>]` and `[pl-agent:<name>/<stage>=<agent>]`
declare a skip / model override / subagent_type override.
Per-stage outcome `st` = {title: {s: run|done|skip|back|fail, t0, t1, n}} (n = dispatches).
Denies on a run: `deny` = count, `dl` = last DL_MAX {t, title, c} with c in DENY_CODES.
PostToolUse (Task|Agent|SendMessage): when the stage's dispatches are back, adds «PASS → next … / FAIL → …» context.
`--platform <key>` (other CLIs): a shell command STARTING with `[pl:<name>/<stage>]` (Pre) starts a stage and
`[pl-end:<name>/<stage>]` / `[pl-end:<name>/<stage>|fail]` (Post) ends it with the PASS / FAIL hand-off.
No `--platform` = cc (Claude Code), unchanged.
Run end (last stage done · `[pl-end:]` · main's `git commit`): when the project has an answer key
(<data dir>/eval/<repo key>/seeds.json) it launches `scripts/pl_eval.py score --auto` detached (no wait, no output).
Stores stage titles, counts and times only -- never descriptions, commands, task text or tool output.
Fail-open: any problem means no output and exit 0. Stdlib only, Python 3.9, no fcntl (Windows target).
"""
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

# Same derivation as sidereus/config.py DATA_DIR and hooks/pl_mark.py (this hook cannot import either).
DATA_DIR = os.path.expanduser(os.environ.get("MAILBOX_DIR") or "~/.mailbox-mcp")
MARK_DIR = os.path.join(DATA_DIR, "plmark")
CONFIG_PATH = None   # None = same rule as pipelines_brief.py; patched in tests
TAG = re.compile(r"\[pl:([a-z0-9-]{1,40})/([^\]\n]{1,40})\]")
SKIP_TAG = re.compile(r"\[pl-skip:([a-z0-9-]{1,40})/([^\]\n]{1,40})\]")
NONE_TAG = re.compile(r"\[pl-none:([a-z-]{1,20})\]")   # session-wide «no pipeline for this work» declaration
NONE_CATS = ("small-fix", "no-fit", "explore", "other")
EDITS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
END_TAG = re.compile(r"\[pl-end:([a-z0-9-]{1,40})/([^\]\n|]{1,40})\]")
MODEL_TAG = re.compile(r"\[pl-model:([a-z0-9-]{1,40})/([^\]\n=]{1,40})=([A-Za-z0-9._-]{1,40})\]")
AGENT_TAG = re.compile(r"\[pl-agent:([a-z0-9-]{1,40})/([^\]\n=]{1,40})=([A-Za-z0-9._:-]{1,64})\]")
# Renamed recommended stage titles (old -> new): old tags and legacy files map to the new title. ⚠Same map in sidereus/pipeline_schema.py RENAMED.
RENAMED = {"최종 검증": "재검증"}
CLAUDE_DIR = None    # None = $CLAUDE_CONFIG_DIR or HOME_DIR/.claude (user agents); patched in tests
BUILTIN = ("general-purpose", "Explore", "Plan")
NO_AGENT = ("", "main", "claude")   # a stage the main agent runs itself: no subagent_type check
SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
FIELD = {"Bash": "description", "Agent": "description", "Task": "description", "SendMessage": "summary"}
DISPATCH = ("Agent", "Task", "SendMessage")
# Same keys as sidereus/ext_store.py EXT_PLAT, plus cc; an unknown --platform does nothing.
PLATFORMS = ("cc", "gemini", "codex", "copilot", "cursor", "cline", "windsurf", "warp", "trae", "zed", "grok",
             "deepseek", "qwen", "kimi", "mistral", "ollama", "perplexity", "huggingface", "meta", "openrouter")
EMIT = ("cc", "codex", "gemini")   # platforms that read PostToolUse additionalContext; others get no stdout
EVENT = {"BeforeTool": "PreToolUse", "AfterTool": "PostToolUse"}   # Gemini names
CAMEL = {"preToolUse": "PreToolUse", "postToolUse": "PostToolUse", "postToolUseFailure": "PostToolUse"}   # Cursor names
SHELL = ("run_shell_command", "shell", "exec_command", "local_shell", "Bash",
         "PowerShell", "Shell")   # Bash/PowerShell only off cc; PowerShell = Claude Code's Windows shell tool; Shell = Cursor
# ⚠Same as pl_mark.py MARK; anchored at the command start so `grep "[pl:"` never counts.
MARK = re.compile(r"""^\s*(?:echo\s+|#\s*|:\s+)?["']?\[pl(-end)?:(?:(-)|([a-z0-9-]{1,40})/([^\]\n|]{1,40})(\|fail)?)\]""")
IDLE_S = 6 * 3600     # a run untouched this long is over; the next tag opens a new one
LOST_S = 45 * 60      # ⚠a dispatch refused or failed before running gets no Post; its slice is presumed lost after this
LOCK_WAIT_S, LOCK_STALE_S = 2.0, 5.0
NUDGE_S = 600         # at most one untagged-Bash reminder per open run in this window
# Async receipts: Agent run_in_background launch, SendMessage resume / queue (same texts sidereus/bgtasks_parse.py reads).
BG_RE = re.compile(r"async_launched|Async agent launched|Resuming agent|resumed from transcript|resumedAgentId|"
                   r"Message queued")


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


# Same as sidereus/gitinfo.py GIT_SAFE_OPTS (the plugin ships hooks/ only); ⚠repo config must not run programs.
GIT_SAFE_OPTS = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.quotePath=false"]


def _head(proj):
    """Short HEAD of the run's repo, or "" (git missing, not a repo, slow); never raises."""
    try:
        root = _git_root(os.path.realpath(proj)) if proj else ""
        if not root:
            return ""
        kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
        p = subprocess.run(["git"] + GIT_SAFE_OPTS + ["-C", root, "rev-parse", "--short", "HEAD"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1,
                           env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"), **kw)
        h = (p.stdout or "").strip()
        return h if p.returncode == 0 and re.fullmatch(r"[0-9a-f]{4,40}", h) else ""
    except Exception:
        return ""


def _now():
    return time.time()


WHY_MAX = 32 * 1024   # <sid>.why cap; past it only the newer half of the lines is kept
_WORD = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def _why(ev, code):
    """Diagnostic: one line `<iso> <event> <tool> <code>` in plmark/<sid>.why for a silent early exit.
    ⚠Metadata only (sid from the payload, never tool input); must never raise."""
    try:
        sid = ev.get("session_id") if isinstance(ev, dict) else None
        if not isinstance(sid, str) or not SID.match(sid):
            return
        w = [x if isinstance(x, str) and _WORD.match(x) else "-" for x in (ev.get("hook_event_name"), ev.get("tool_name"), code)]
        if not os.path.isdir(MARK_DIR):   # a silent exit never creates the data dir
            return
        p = os.path.join(MARK_DIR, sid + ".why")
        if os.path.isfile(p) and os.path.getsize(p) > WHY_MAX:
            with open(p, encoding="utf-8", errors="replace") as f:
                ls = f.readlines()
            with open(p, "w", encoding="utf-8") as f:
                f.writelines(ls[len(ls) // 2:])
        with open(p, "a", encoding="utf-8") as f:
            f.write("%s %s %s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(_now())), w[0], w[1], w[2]))
    except Exception:
        pass


# --- auto catch-rate scoring at run end (scripts/pl_eval.py score --auto dedupes per (pipeline, commit)) ---
SCORE_SCRIPT = None   # None = <hook dir>/../scripts/pl_eval.py, else <data dir>/scripts/pl_eval.py; patched in tests
_CLOSED = []          # (project dir, pipeline name, since) of runs this hook call ended


def _closed(proj, name, since=None):
    """since = closing `git commit` Pre time: the scorer skips unless a commit at/after it landed."""
    _CLOSED.append((proj, name, since))


def _score_script():
    if SCORE_SCRIPT:
        return SCORE_SCRIPT
    for d in (os.path.dirname(os.path.dirname(os.path.abspath(__file__))), DATA_DIR):
        p = os.path.join(d, "scripts", "pl_eval.py")
        if os.path.isfile(p):
            return p
    return None


def _spawn(argv):
    """Detached child: no wait, no pipes. ⚠Never let it block or fail the tool call."""
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    subprocess.Popen(argv, **kw)


REPORT_SCRIPT = None   # None = pl_report.py next to pl_eval.py; patched in tests


def _report_script():
    if REPORT_SCRIPT:
        return REPORT_SCRIPT
    sc = _score_script()
    p = os.path.join(os.path.dirname(sc), "pl_report.py") if sc else ""
    return p if p and os.path.isfile(p) else None


def _key(proj):
    """= sidereus/arch_verify.repo_key (sha1 of realpath, 16 hex)."""
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- persisted path key, not security
    return hashlib.sha1(os.path.realpath(proj).encode("utf-8", "surrogateescape"), usedforsecurity=False).hexdigest()[:16]


def _autoscore():
    """Score each run ended in this call where seeds.json exists, and ask for the weekly report (pl_report --auto)."""
    todo, _CLOSED[:] = list(dict.fromkeys(_CLOSED)), []
    for proj, name, since in todo:
        try:
            if not (isinstance(proj, str) and os.path.isabs(proj) and isinstance(name, str) and _PLNAME.fullmatch(name)):
                continue
            key = _key(proj)
            pf, sc = os.path.join(proj, ".claude", "pipelines", name + ".json"), _score_script()
            if sc and os.path.isfile(os.path.join(DATA_DIR, "eval", key, "seeds.json")) and os.path.isfile(pf):
                _spawn([sys.executable or "python3", sc, "score", "--repo", proj, "--pipeline", pf, "--auto"]
                       + (["--since", str(int(since))] if since else []))
            rp = _report_script()
            # ⚠--data-dir: the child derives every path from it, so a hook run against a patched DATA_DIR stays there
            if rp and os.path.isfile(pf) and _git_root(os.path.realpath(proj)):
                _spawn([sys.executable or "python3", rp, "--repo", proj, "--pipeline", pf, "--auto", "--data-dir", DATA_DIR])
        except Exception:
            pass


# --- run ledger: one row per ended run in DATA_DIR/eval/<key>/runs.jsonl (sidereus/pl_outcome.py reads it) ---
OC_LEDGER_MAX = 2000   # = sidereus/pl_outcome.py OC_LEDGER_MAX
_HEXH = re.compile(r"[0-9a-f]{4,40}")


def _ledger_add(r, name, now):
    """Append ended run `r` as {name, t0, end, lb, deny, dc, h0, h1}. ⚠Titles, counts and hashes only, never tool
    input; only for a git repo (the result layer needs one); fail-silent — this hook runs live."""
    try:
        proj = r.get("proj") if isinstance(r, dict) else None
        if not (isinstance(proj, str) and os.path.isabs(proj) and isinstance(name, str) and _PLNAME.fullmatch(name)):
            return
        if not _git_root(os.path.realpath(proj)):
            return
        dc = {}
        for e in r.get("dl") if isinstance(r.get("dl"), list) else []:
            if isinstance(e, dict) and e.get("c") in DENY_CODES:
                dc[e["c"]] = dc.get(e["c"], 0) + 1
        lb = [{"f": e.get("f"), "g": e.get("g"), "n": int(e.get("n") or 0)} for e in r.get("lb") or []
              if isinstance(e, dict) and isinstance(e.get("f"), str) and isinstance(e.get("g"), str)]
        row = {"name": name, "t0": float(r.get("t0") or now), "end": float(now), "lb": lb, "deny": int(r.get("deny") or 0), "dc": dc}
        for k in ("h0", "h1"):
            if isinstance(r.get(k), str) and _HEXH.fullmatch(r[k]):
                row[k] = r[k]
        d = os.path.join(DATA_DIR, "eval", _key(proj))
        os.makedirs(d, mode=0o700, exist_ok=True)
        p = os.path.join(d, "runs.jsonl")
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with _Lock(p) as lk:   # ⚠sessions end runs concurrently: an unlocked trim drops the other session's row
            if not lk.ok:
                return
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    old = f.readlines()
            except OSError:
                old = []
            if len(old) < OC_LEDGER_MAX:
                with open(p, "a", encoding="utf-8") as f:
                    f.write(line)
                return
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".runs-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(old[-(OC_LEDGER_MAX - 1):] + [line])
                os.replace(tmp, p)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    except Exception:
        pass


def _installed(agent, dirs):
    """True when `agent` is a builtin or a project/user `.claude/agents/<agent>.md` (same rule as 48b plAgMissing)."""
    if agent in BUILTIN:
        return True
    c = os.environ.get("CLAUDE_CONFIG_DIR")
    user = CLAUDE_DIR or (os.path.expanduser(c) if c else os.path.join(HOME_DIR, ".claude"))
    return any(os.path.isfile(os.path.join(d, "agents", agent + ".md"))
               for d in [os.path.join(x, ".claude") for x in dirs if x] + [user])


def _fit(ev, tool, name, s, r, dirs):
    """(code "agent"|"model", deny reason) when an Agent/Task does not use the stage's agent and model, else None.
    ⚠An omitted model is a mismatch: the run record cannot tell which model the agent file picks."""
    if tool not in ("Agent", "Task"):
        return None
    ti = ev.get("tool_input") or {}
    want = (r.get("agents") or {}).get(s["title"]) or s.get("agent")
    want = want if isinstance(want, str) else ""
    sub = ti.get("subagent_type") if isinstance(ti.get("subagent_type"), str) and ti.get("subagent_type") else "general-purpose"
    ok_ag = want in NO_AGENT or sub == want or (sub == "general-purpose" and not _installed(want, dirs))
    m = r["models"].get(s["title"]) or s.get("model")
    m = m.strip().lower() if isinstance(m, str) else ""
    got = ti.get("model").strip().lower() if isinstance(ti.get("model"), str) else ""
    if ok_ag and (not m or m == "inherit" or got == m):
        return None
    exp = "subagent_type %s" % (want if want not in NO_AGENT else sub)
    if want not in NO_AGENT and not _installed(want, dirs):
        exp += " (not installed: general-purpose also accepted)"
    if m and m != "inherit":
        exp += " and model %s" % m
    return ("model" if ok_ag else "agent",
            "[pl:%s/%s] expects %s; this call has subagent_type %s, model %s. Dispatch again with those, or declare "
            "another model or agent first with a Bash description [pl-model:%s/%s=<model>] or [pl-agent:%s/%s=<agent>]."
            % (name, s["title"], exp, sub[:64], got[:40] or "(none)", name, s["title"], name, s["title"]))


def _open_run(path, now):
    """(name, stage) of an open run in this session's runs file (touched within LOST_S, «Apply» on), else None."""
    for n, r in sorted(_load(path)["runs"].items()):
        if isinstance(r, dict) and not r.get("end") and now - float(r.get("t1") or 0) <= LOST_S \
                and r.get("tail") != r.get("cur") and not _apply_off(r.get("proj") or r.get("cwd")):
            return n, r.get("cur") or ""
    return None


def _apply_off(cwd):
    """True when Sidereus's «Apply» is off for `cwd` (same rule as pl_mark.py); any problem = not off."""
    try:
        p = CONFIG_PATH or os.path.expanduser(os.environ.get("MAILBOX_CONFIG") or os.path.join(DATA_DIR, "config.local.json"))
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get("pipeline_apply") or {}
        return ((v.get("projects") or {}).get(cwd) or v.get("mode")) == "off"
    except Exception:
        return False


def _project(ev, tool, name, title, keep):
    """Project dir whose <name>.json this call belongs to, or None (ambiguous).
    Order: the cwd project (cwd or its git root) when it owns <name>; else the open run's project `keep`; else the most
    recent `cd` target owning it (session_dirs is newest first). ⚠Fit scoring let a same-named pipeline of a repo the
    session only cd'd into take a run started in the cwd project; fit now only ranks owners found outside the
    session's dirs (_known_owner): stage title +1, stage agent == subagent_type +2, cwd breaks ties."""
    rel = os.path.join(".claude", "pipelines", name + ".json")
    cwd = ev.get("cwd") or ""   # a hook event without cwd must not raise
    hits = [d for d in session_dirs(ev, every=True) if d and os.path.isfile(os.path.join(d, rel))]
    own = [d for d in (cwd, _git_root(cwd) if cwd else "") if d and os.path.isfile(os.path.join(d, rel))]
    if own:
        return own[0]
    if hits:
        return keep if keep in hits else hits[0]
    hits = _known_owner(rel, ev)
    if keep in hits or len(hits) <= 1:
        return keep if keep in hits else (hits[0] if hits else None)
    sub = (ev.get("tool_input") or {}).get("subagent_type") if tool in ("Agent", "Task") else None
    score = {}
    for d in hits:
        pl = _stages(d, name)
        s = [x for x in (pl[0] if pl else []) if x["title"] == title]
        score[d] = (1 if s else 0) + (2 if s and isinstance(sub, str) and s[0].get("agent") == sub else 0)
    top = max(score.values())
    best = [d for d in hits if score[d] == top]
    if len(best) == 1:
        return best[0]
    return cwd if cwd in best else None


CLAUDE_JSON = None   # None = $CLAUDE_CONFIG_DIR/.claude.json or HOME_DIR/.claude.json; patched in tests
PROJ_STORE = None    # None = DATA_DIR/pipeline-projects.json (sidereus/pipeline_projects.py PROJ_STORE); patched in tests
TOUCH_TAIL = 1500000   # same tail as sidereus/gitinfo.session_repos (server `repos`)


def _known_owner(rel, ev=None):
    """Known projects (~/.claude.json `projects` keys + Sidereus's added projects) owning `rel`: the sole owner, else the
    owners this session touched. ⚠A session launched in another folder found no pipelines and recorded nothing, so
    Sidereus drew another session's stale run. Any error = []."""
    try:
        own = [k for k in _known_keys() if os.path.isfile(os.path.join(k, rel))]
        return own if len(own) <= 1 else _touched(own, (ev or {}).get("transcript_path"))
    except Exception:
        return []


def _known_keys():
    """Absolute project dirs from ~/.claude.json `projects` keys + Sidereus's added projects (deduped, file order)."""
    c = os.environ.get("CLAUDE_CONFIG_DIR")
    # ⚠guard before expanduser: expanduser(None) raised when CLAUDE_CONFIG_DIR is unset (every Codex process) -> []
    cjs = [CLAUDE_JSON] if CLAUDE_JSON else ([os.path.join(os.path.expanduser(c), ".claude.json")] if c else []) + [
        os.path.join(HOME_DIR, ".claude.json")]
    st = PROJ_STORE or os.path.join(DATA_DIR, "pipeline-projects.json")
    h = HOME_DIR.rstrip(os.sep) + os.sep   # ⚠default files only under HOME_DIR: tests patch it, so they never read live ones
    ks = []
    for p in [x for x in cjs if CLAUDE_JSON or x.startswith(h)] + [st] * bool(PROJ_STORE or st.startswith(h)):
        try:
            with open(p, encoding="utf-8") as f:
                v = json.load(f)
        except Exception:
            continue
        v = v.get("projects") if isinstance(v, dict) else v
        ks += list(v) if isinstance(v, (dict, list)) else []
    out = []
    for k in ks:
        if isinstance(k, str) and os.path.isabs(k) and k not in out:
            out.append(k)
    return out


def known_pipelines(ev, skip=()):
    """(name, project) pairs _known_owner resolves for this session, projects in `skip` left out (pl_mark nudge).
    ⚠A session in another repo was told only its own pipelines and tagged a relayed run `[pl:-]`. Any error = []."""
    try:
        out = []
        for k in _known_keys():
            if k in skip:
                continue
            try:
                ns = sorted(n[:-5] for n in os.listdir(os.path.join(k, ".claude", "pipelines"))
                            if n.endswith(".json") and _PLNAME.fullmatch(n[:-5]))
            except OSError:
                continue
            out += [(n, k) for n in ns if k in _known_owner(os.path.join(".claude", "pipelines", n + ".json"), ev)]
        return out
    except Exception:
        return []


def _touched(own, tp):
    """Owners whose paths appear in tool_use inputs of the transcript tail (sidereus/gitinfo.session_repos = server `repos`).
    ⚠Several known projects often own the same pipeline name; only the ones the session works in are candidates."""
    if not (isinstance(tp, str) and os.path.isabs(tp)):
        return []
    with open(tp, "rb") as f:
        size = os.path.getsize(tp)
        if size > TOUCH_TAIL:
            f.seek(size - TOUCH_TAIL)
            f.readline()
        raw = f.read().decode("utf-8", "replace")
    blob = []
    for line in raw.splitlines():
        if '"tool_use"' not in line:
            continue
        try:
            c = (json.loads(line).get("message") or {}).get("content")
        except Exception:
            continue
        for b in c if isinstance(c, list) else []:
            inp = b.get("input") if isinstance(b, dict) and b.get("type") == "tool_use" else None
            if isinstance(inp, dict):
                blob += [inp[k] for k in ("file_path", "path", "notebook_path", "command") if isinstance(inp.get(k), str)]
    hd = HOME_DIR.rstrip(os.sep) + "/"   # ⚠callable repl: a `C:\Users` home as a template string is a bad `\U` escape
    s = re.sub(r"(?<![\w/.-])~/", lambda _m: hd, "\n".join(blob) + "\n")   # `cd ~/x` counts like the server
    s = _pkey(s)
    return [d for d in own if any(_pkey(d) + e in s for e in ("/", " ", "\n", "'", '"'))]


def _pkey(s):
    """Unchanged on POSIX. ⚠Windows: tool inputs mix `\\` and `/` (`~/x` expands onto a `C:\\` home) and ignore case."""
    return s if os.sep == "/" else s.replace("\\", "/").lower()


def _ren(t):
    return RENAMED.get(t, t) if isinstance(t, str) else t


def _ren_stage(s):
    """Copy of stage `s` with its title and onFail goto/then under their current names."""
    s = dict(s, title=_ren(s["title"]))
    if isinstance(s.get("onFail"), dict):
        s["onFail"] = dict(s["onFail"], **{k: _ren(s["onFail"][k]) for k in ("goto", "then") if k in s["onFail"]})
    return s


def _stages(cwd, name):
    """Stage dicts of <cwd>/.claude/pipelines/<name>.json, or None (missing/bad)."""
    try:
        with open(os.path.join(cwd, ".claude", "pipelines", name + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        st = [_ren_stage(s) for s in d["stages"] if isinstance(s, dict) and isinstance(s.get("title"), str)]
        after = [a for a in (d.get("after") or []) if isinstance(a, str)]
    except Exception:
        return None
    return (st, after) if st else None


class _Lock(object):
    """O_CREAT|O_EXCL lockfile (portable); a lock older than LOCK_STALE_S is taken over."""

    def __init__(self, path):
        self.path, self.ok = path + ".lock", False

    def __enter__(self):
        end = time.monotonic() + LOCK_WAIT_S
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                self.ok = True
                return self
            except OSError:
                try:
                    if time.time() - os.path.getmtime(self.path) > LOCK_STALE_S:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
            if time.monotonic() >= end:
                return self
            time.sleep(0.02)

    def __exit__(self, *a):
        if self.ok:
            try:
                os.remove(self.path)
            except OSError:
                pass


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get("runs"), dict):
            return d
    except Exception:
        pass
    return {"v": 1, "runs": {}}


def _save(path, d):
    tmp = path + ".tmp.%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _idx(st, title):
    for i, s in enumerate(st):
        if s["title"] == title:
            return i
    return -1


def _onfail(s):
    f = s.get("onFail")
    return f if isinstance(f, dict) and isinstance(f.get("goto"), str) else None


def _plain_next(st, i):
    """Index of the next stage after i that is not onlyOnJump, or -1."""
    for j in range(i + 1, len(st)):
        if not st[j].get("onlyOnJump"):
            return j
    return -1


def _new_run(cwd, now):
    return {"cwd": cwd, "t0": now, "t1": now, "cur": "", "done": [], "inflight": {}, "ret": "",
            "loops": {}, "skipok": [], "end": 0, "st": {}, "models": {}, "agents": {}, "lb": [], "deny": 0, "dl": []}


DENY_CODES = ("jump", "agent", "model", "tag", "stage", "stop", "gate", "skipgate")   # gate/skipgate: pl_guard requireGates; same set as sidereus/harness_flow.py HF_DENY_CODES
DL_MAX = 20   # deny log entries kept per run


def _deny_note(r, title, code, now):
    """Count one deny on run `r`: deny += 1, dl += {t, title, c}. ⚠Fixed code + stage title only, never the tool
    input; never raises — this hook runs live."""
    try:
        r["deny"] = int(r.get("deny") or 0) + 1
        dl = r["dl"] if isinstance(r.get("dl"), list) else []
        dl.append({"t": now, "title": title, "c": code})
        r["dl"] = dl[-DL_MAX:]
    except Exception:
        pass


def _resume_note(r, now, why):
    """Pass `why` through; when it is falsy (allowed Pre) stamp dl[-1]["r"] = now once (time only); never raises."""
    try:
        dl = r.get("dl")
        if not why and isinstance(dl, list) and dl and isinstance(dl[-1], dict) and "r" not in dl[-1]:
            dl[-1]["r"] = now
    except Exception:
        pass
    return why


def _is_open(r, now):
    return isinstance(r, dict) and not r.get("end") and now - float(r.get("t1") or 0) <= IDLE_S


def _deny_save(path, name, title, code, now):
    """Record a deny on this session's open run `name` (lock + atomic save); fail-silent, nothing when none is open."""
    try:
        if not os.path.isfile(path):
            return   # ⚠no runs file = no open run; also keeps _Lock from waiting LOCK_WAIT_S on a missing dir
        with _Lock(path) as lk:
            if not lk.ok:
                return
            d = _load(path)
            r = d["runs"].get(name)
            if _is_open(r, now):
                _deny_note(r, title, code, now)
                _save(path, d)
    except Exception:
        pass


LB_MAX = 16   # loop-back edges kept per run


def _lb(r, f, g, now):
    """Count one loop-back f→g in r["lb"] as {f, g, n, t} (titles only); ⚠never raises — this hook runs live."""
    try:
        lb = r["lb"] if isinstance(r.get("lb"), list) else []
        for e in lb:
            if isinstance(e, dict) and e.get("f") == f and e.get("g") == g:
                e["n"], e["t"] = int(e.get("n") or 0) + 1, now
                break
        else:
            lb.append({"f": f, "g": g, "n": 1, "t": now})
        r["lb"] = lb[-LB_MAX:]
    except Exception:
        pass


def _mark(r, title, s, now, n=0):
    """Set stage outcome `s` (run|done|skip|back|fail) in r["st"]; keys s/t0/t1/n (+ ag ids) only (metadata)."""
    e = r["st"].get(title)
    e = e if isinstance(e, dict) else {}
    if s == "skip" and e.get("s") in ("done", "back", "fail"):
        return   # ⚠a later skip of a stage that already ran this run keeps its real outcome, times and pass count
    if "t0" not in e or s == "skip" or e.get("s") == "skip":
        e["t0"] = now
    r["st"][title] = {"s": s, "t0": e["t0"], "t1": now, "n": int(e.get("n") or 0) + n}
    if isinstance(e.get("ag"), list):
        r["st"][title]["ag"] = e["ag"]
    if e.get("m") in (True, False):
        r["st"][title]["m"] = e["m"]
    if "p0" in e and s != "skip":
        r["st"][title]["p0"], r["st"][title]["k"] = e["p0"], e.get("k") or 2
    if isinstance(e.get("ps"), list):
        r["st"][title]["ps"] = e["ps"]   # ⚠this dict is rebuilt: every new stage key needs a carry line here
    if isinstance(e.get("cm"), list):
        r["st"][title]["cm"] = e["cm"]


PS_MAX = 6   # closed earlier passes kept per stage
CM_MAX = 4   # commit times kept per stage


def _ps(e, old):
    """Append the pass `old` is closing to e["ps"] as {a, b, s} (times + outcome only); ⚠never raises — this hook runs live."""
    try:
        a = old.get("p0", old.get("t0"))
        if isinstance(a, (int, float)) and isinstance(old.get("t1"), (int, float)) and isinstance(old.get("s"), str):
            ps = [x for x in (e.get("ps") if isinstance(e.get("ps"), list) else []) if isinstance(x, dict)]
            ps.append({"a": a, "b": old["t1"], "s": old["s"]})
            e["ps"] = ps[-PS_MAX:]
    except Exception:
        pass


AG_IDS_MAX = 8   # continued-agent ids kept per stage
_AG_ID = re.compile(r"[0-9A-Za-z_-]{1,64}")


def _ag_note(r, title, to):
    """Record a SendMessage target id under `title` (an agent dispatched for another stage, continued into this one);
    ⚠ids only — never the message. Never raises: this hook runs live."""
    try:
        e = r["st"].get(title)
        if not isinstance(e, dict) or not isinstance(to, str) or not _AG_ID.fullmatch(to):
            return
        ids = [x for x in (e.get("ag") if isinstance(e.get("ag"), list) else []) if x != to] + [to]
        e["ag"] = ids[-AG_IDS_MAX:]
    except Exception:
        pass


# Background Agent launch receipt: "agentId: <id>" (text) or "agentId": "<id>" (structured); id only, never the body.
# ⚠Searched JSON-dumped: "\nagentId" reads as "nagentId", so an escape counts as a boundary; "subagentId" must not match.
_BG_AID_RE = re.compile(r"""(?:(?<![A-Za-z])|(?<=\\[nrt]))agentId["']?\s*[:=]\s*["']?([0-9A-Za-z_-]{1,64})""")


def _bg_aid(ev):
    """agentId from a background Agent/Task PostToolUse receipt, or None. Never raises."""
    try:
        resp = ev.get("tool_response")
        v = resp.get("agentId") if isinstance(resp, dict) else None
        if isinstance(v, str) and _AG_ID.fullmatch(v):   # structured receipt first; regex is the fallback
            return v
        if isinstance(resp, dict):   # ⚠an invalid top-level agentId must not be re-found by the regex as a prefix
            resp = {k: x for k, x in resp.items() if k != "agentId"}
        txt = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
        m = _BG_AID_RE.search(txt[:4000])
        return m.group(1) if m and _AG_ID.fullmatch(m.group(1)) else None
    except Exception:
        return None


def _cm_stage(r, name, ev):
    """Stage a subagent's commit stamps: the one listing its agent_id in `ag`, else the single stage whose pipeline
    agent is its agent_type (running one preferred), else cur. ⚠Never raises: this hook runs live."""
    cur = r.get("cur")
    try:
        st, aid = r.get("st") or {}, ev.get("agent_id")
        if isinstance(aid, str) and aid:
            hit = [t for t, e in st.items() if isinstance(e, dict) and isinstance(e.get("ag"), list) and aid in e["ag"]]
            if len(hit) == 1:
                return hit[0]
            if cur in hit:
                return cur
        at = ev.get("agent_type")
        pl = _stages(r.get("proj"), name) if isinstance(at, str) and at and at not in NO_AGENT else None
        if pl:
            hit = [s["title"] for s in pl[0] if s.get("agent") == at and isinstance(st.get(s["title"]), dict)]
            run = [t for t in hit if st[t].get("s") == "run"]
            if len(hit) == 1:
                return hit[0]
            if len(run) == 1:
                return run[0]
    except Exception:
        pass
    return cur


def _jumped(st, r, title):
    """Stages a Pre of `title` would pass over without running or a `[pl-skip:]` declaration."""
    t, c = _idx(st, title), _idx(st, r["cur"])
    if c < 0:
        # ⚠A new run (or one opened by a [pl-skip:] declaration) starting mid-way left earlier stages «Waiting» forever.
        return [s["title"] for s in st[:max(t, 0)] if not s.get("onlyOnJump") and s["title"] not in r["skipok"]]
    if t <= c:
        return []
    # ⚠A skipped loop-back return stage (onFail `then`) is the new start: measuring from `cur` re-listed stages already run.
    k = _idx(st, r.get("ret") or "")
    if r.get("ret") in r["skipok"] and k > c:
        c = k
    allowed = {r["cur"], r["ret"]}
    n = _plain_next(st, c)
    if n >= 0:
        allowed.add(st[n]["title"])
    f = _onfail(st[c])
    if f:
        allowed.update([f["goto"], f.get("then") or ""])
    if title in allowed:
        return []
    return [s["title"] for s in st[c + 1:t] if not s.get("onlyOnJump") and s["title"] not in r["skipok"]]


def _reopen(st, r, g):
    """Loop-back to stage index `g`: drop skip declarations from `g` on (st[t]["s"] skip marks stay)."""
    # ⚠Without this a skip declared in round 1 waved the same stage through `_jumped` in every later round.
    r["skipok"] = [x for x in r["skipok"] if _idx(st, x) < g]


def pre(tool, cwd, name, title, st, r, now, shell=False):
    """Advance run `r` for a tagged Pre; returns a deny reason or None (nothing changed on a deny)."""
    skipped = _jumped(st, r, title)
    if skipped:
        # ⚠Denied every time: a deny-once guard let the retry through, so stages were skipped without a record.
        return ("You skipped %s; run it, or declare each skip first with a Bash description "
                "[pl-skip:%s/<stage>] <one-line reason>, then dispatch again." % (", ".join(skipped), name))
    t = _idx(st, title)
    c = _idx(st, r["cur"])
    if 0 <= t < c:
        _reopen(st, r, t)
        f = _onfail(st[c])
        if f and f["goto"] == title:
            r["loops"][r["cur"]] = int(r["loops"].get(r["cur"]) or 0) + 1
            _lb(r, r["cur"], title, now)
            then = f.get("then")
            r["ret"] = then if isinstance(then, str) and _idx(st, then) >= 0 else r["cur"]
            _mark(r, r["cur"], "back", now)   # sent back (e.g. review fixes), not failed; a later pass marks it done
        elif (r["st"].get(r["cur"]) or {}).get("s") == "run":
            _mark(r, r["cur"], "back", now)   # ⚠undeclared backward move: no lb edge, but never leave it «run» forever
    elif t > c >= 0 and (r["st"].get(r["cur"]) or {}).get("s") == "run":
        _mark(r, r["cur"], "done", now)   # moving on from a stage that gets no Post (Bash, background)
    if title == r["ret"]:
        r["ret"] = ""   # the pending return stage is being run now
    count = tool in DISPATCH or shell
    old = r["st"].get(title)
    again = isinstance(old, dict) and (old.get("s") in ("done", "back", "skip", "fail") or title != r["cur"])
    if count or title != r["cur"] or title not in r["st"]:
        _mark(r, title, "run", now, 1 if count else 0)
    if again and r["st"][title]["t0"] != now:
        e = r["st"][title]
        _ps(e, old)
        e["p0"], e["k"] = now, int(old.get("k") or 1) + 1   # a new pass: elapsed is shown per pass, t0 stays the first start
    e = r["st"][title]
    if tool in DISPATCH and "m" in e:
        e["m"] = False   # a dispatch after main's own work: no longer main-only
    elif tool not in DISPATCH and "m" not in e and (shell or e.get("n", 0) == 0):
        e["m"] = True    # only main's own Bash/shell markers so far (n counts dispatches)
    if title != r["cur"]:
        r["inflight"] = {}   # ⚠counts left by background dispatches of another stage would block every hand-off
        # HEAD at stage start (one git call per transition; a fresh run reuses h0)
        h = r.get("h0") if not r["cur"] and r.get("h0") else _head(r.get("proj"))
        if h:
            r["h1"] = h
    r["cur"], r["t1"] = title, now
    if tool in DISPATCH:
        r["inflight"][title] = int(r["inflight"].get(title) or 0) + 1
    return None


def _step(name, s):
    out = "[pl:%s/%s] · agent %s" % (name, s["title"], s.get("agent") or "-")
    for k in ("model", "skill", "gate"):
        if isinstance(s.get(k), str) and s.get(k):
            out += " · %s %s" % (k, s[k])
    return out


def post(name, title, st, after, r, bg, now):
    """Hand-off text for a returned dispatch of `title`, or None while slices are still out."""
    i = _idx(st, title)
    if i < 0:
        return None
    left = max(0, int(r["inflight"].get(title) or 0) - 1)
    r["inflight"][title] = left   # ⚠bg too: a background dispatch gets only this Post, skipping it leaked the count
    if not bg:
        if left and now - float(r["t1"] or 0) <= LOST_S:   # t1 = last Pre of this (current) stage
            return None
        r["inflight"][title] = 0
    if title != r["cur"]:
        return None   # a late slice of a stage the run already left
    nxt = r["ret"] or ""
    j = _idx(st, nxt) if nxt else _plain_next(st, i)
    # ⚠ret is cleared by the Pre that runs it, not here: the skip guard needs it to let a jump (e.g. to an
    # onlyOnJump stage) through.
    if not bg and title not in r["done"]:
        r["done"].append(title)
    if not bg:
        _mark(r, title, "done", now)
    if j < 0:
        if bg:
            r["fin"] = title   # ⚠no later event ends a bg last stage; Sidereus closes the run once its agents finish
            return "[pl:%s] when it finishes: last stage — run complete." % name
        r["end"] = now
        _ledger_add(r, name, now)
        return "Run complete" + (": " + " · ".join(after) if after else ".")
    lines = [("When it finishes, next: " if bg else "PASS → next: ") + _step(name, st[j])]
    f = _onfail(st[i])
    if f:
        mx = int(f.get("max") or 1)
        k = int(r["loops"].get(title) or 0) + 1
        then = f.get("then")
        if k <= mx:
            lines.append("FAIL → SendMessage the %s agent tagged [pl:%s/%s] (round %d/%d; at max → %s)"
                         % (f["goto"], name, f["goto"], k, mx,
                            ("[pl:%s/%s]" % (name, then)) if then else "stop and report"))
        else:
            lines.append("FAIL → round limit %d/%d reached: %s" % (mx, mx,
                         ("[pl:%s/%s]" % (name, then)) if then else "stop and report"))
    if st[i].get("onError") == "continue":
        lines.append("Failed fan-out slices do not block.")
    return "\n".join(lines)


def end(name, title, st, after, r, fail, now):
    """Hand-off for a shell `[pl-end:]`: the result is known, so only the PASS or the FAIL branch is given."""
    i = _idx(st, title)
    if i < 0 or title != r["cur"]:
        return None
    if not fail:
        r["inflight"][title] = 1   # one marker = one slice; the start marker never counted it
        t = post(name, title, st, after, r, False, now)
        return "\n".join(x for x in t.split("\n") if not x.startswith("FAIL")) if t else t
    r["inflight"][title] = 0
    _mark(r, title, "fail", now)
    f = _onfail(st[i])
    if not f:
        return "FAIL → %s has no onFail: stop and report." % title
    mx, k, then = int(f.get("max") or 1), int(r["loops"].get(title) or 0) + 1, f.get("then")
    g = _idx(st, f["goto"])
    if k > mx or g < 0:
        return "FAIL → round limit %d/%d reached: %s" % (mx, mx, ("[pl:%s/%s]" % (name, then)) if then else "stop and report")
    # ⚠The loop-back is counted here, and cur moves to the goto stage so its start marker is not counted again by pre().
    r["loops"][title] = k
    _lb(r, title, f["goto"], now)
    _reopen(st, r, g)
    r["ret"] = then if isinstance(then, str) and _idx(st, then) >= 0 else title
    r["cur"], r["t1"], r["inflight"] = f["goto"], now, {}
    return "FAIL (round %d/%d) → next: %s" % (k, mx, _step(name, st[g]))


def _platform(argv):
    if "--platform" not in argv:
        return "cc"
    i = argv.index("--platform") + 1
    return argv[i] if i < len(argv) else ""


def _shell_cmd(ti):
    """Same as pl_mark.py shell_cmd."""
    c = ti.get("command", ti.get("cmd")) if isinstance(ti, dict) else None
    if isinstance(c, list):
        c = c[-1] if c else None
    return c if isinstance(c, str) else None


def _is_bg(ev):
    ti = ev.get("tool_input") or {}
    if isinstance(ti, dict) and ti.get("run_in_background") is True:
        return True
    resp = ev.get("tool_response")
    try:
        txt = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
    except Exception:
        return False
    return bool(BG_RE.search(txt[:4000]))   # only matched, never stored or echoed


def _nudge(ev, desc, path, now):
    """Untagged Bash Pre while a run is open: additionalContext reminder (never a deny), once per NUDGE_S; fail-silent."""
    try:
        # ⚠main only: a subagent's Bash shares the session id and would spend the run's one nudge per window
        if ev.get("hook_event_name") != "PreToolUse" or ev.get("tool_name") != "Bash" or ev.get("agent_id") \
                or "[pl:-]" in desc or "[pl-" in desc:
            return
        o = _open_run(path, now)
        r = _load(path)["runs"].get(o[0]) if o else None   # lockless peek: most untagged Bash end here, no lock wait
        if not isinstance(r, dict) or now - float(r.get("nudge_t") or 0) < NUDGE_S:
            return
        with _Lock(path) as lk:
            if not lk.ok:
                return
            d = _load(path)
            r = d["runs"].get(o[0])
            if not isinstance(r, dict) or now - float(r.get("nudge_t") or 0) < NUDGE_S:
                return
            r["nudge_t"] = now
            _save(path, d)   # ⚠raises on failure, so nothing prints: an unsaved nudge_t would nudge on every Bash
        txt = ("Pipeline run %s is open (stage %s): start the description of stage-work Bash with [pl:%s/%s], "
               "or [pl:-] for work outside the run." % (o[0], o[1] or "-", o[0], o[1] or "<stage>"))
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": txt}},
                                    ensure_ascii=False))
    except Exception:
        pass


def _deny(why):
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                        "permissionDecisionReason": why}}, ensure_ascii=False))
    return True


PAST_MAX = 5   # replaced runs kept per pipeline in runs.json "past" (oldest first)
PAST_KEYS = ("st", "lb", "cur", "end", "t0", "t1")   # ⚠only what pl_runs reads: runs.json over its read cap parses as nothing


def _archive(d, name, old):
    """Append replaced run `old` (PAST_KEYS only) to d["past"][name], capped at PAST_MAX; ⚠never raises — runs live."""
    try:
        past = d["past"] if isinstance(d.get("past"), dict) else {}
        lst = [x for x in (past.get(name) if isinstance(past.get(name), list) else []) if isinstance(x, dict)]
        lst.append({k: old[k] for k in PAST_KEYS if k in old})
        past[name] = lst[-PAST_MAX:]
        d["past"] = past
    except Exception:
        pass


def _boundary(st, r, title, now, cont=False):
    """Close open run `r` when `title` is the first stage and the run is already past it, or (unless `cont`, a
    SendMessage continuing one of its agents) any earlier stage while the run sits on its last stage (a new change).
    A declared loop-back to it (cur's onFail goto, or pending ret) and a re-mark at cur stay in the same run.
    Returns True when closed; the caller's `_run_of` then archives it and opens a fresh run."""
    if not _is_open(r, now):
        return False
    t, c = _idx(st, title), _idx(st, r.get("cur") or "")
    # ⚠A run sitting on its last stage is finished: a backward tag at any stage is a new request (one starting at
    #   stage 2 after main did stage 1 itself reused the run and showed the old request's done marks).
    if not (0 <= t < c and (t == _plain_next(st, -1) or (not cont and _plain_next(st, c) < 0))):
        return False
    f = _onfail(st[c])
    if (f and f["goto"] == title) or r.get("ret") == title:
        return False
    stt = r.get("st") if isinstance(r.get("st"), dict) else {}
    r["st"] = stt
    if isinstance(stt.get(r["cur"]), dict) and stt[r["cur"]].get("s") == "run":
        _mark(r, r["cur"], "done", now)   # same close as _commit_close
    r["end"], r["t1"] = now, now
    return True


def _run_of(d, name, cwd, now, fresh=True):
    """Run `name` in loaded runs file `d`, normalised; with `fresh` an ended or idle one is replaced by a new run
    (the replaced one goes to d["past"])."""
    old = d["runs"].get(name)
    r = dict(_new_run(cwd, now), **old) if isinstance(old, dict) else None
    if not r or (fresh and (r.get("end") or now - float(r.get("t1") or 0) > IDLE_S)):
        if isinstance(old, dict):
            _archive(d, name, old)
        r = _new_run(cwd, now)
    for k in ("st", "models", "agents", "loops", "inflight"):
        if not isinstance(r.get(k), dict):
            r[k] = {}
    for k in ("skipok", "lb"):
        if not isinstance(r.get(k), list):
            r[k] = []
    d["runs"][name] = r
    return r


def _skip_ends(st, r):
    """True when cur is finished (done/skipped, nothing in flight, no pending return) and every plain stage after it is skipped."""
    c, cur = _idx(st, r.get("cur") or ""), r.get("cur") or ""
    e = r["st"].get(cur) if isinstance(r.get("st"), dict) else None
    if c < 0 or r.get("ret") or int(r["inflight"].get(cur) or 0) or not (cur in r["skipok"] or (isinstance(e, dict) and e.get("s") in ("done", "skip"))):
        return False
    j = _plain_next(st, c)
    while j >= 0:
        if st[j]["title"] not in r["skipok"]:
            return False
        j = _plain_next(st, j)
    return True


def _declare(ev, cwd, path, desc, now):
    """Bash `[pl-skip:name/stage]` / `[pl-model:name/stage=model]` / `[pl-agent:name/stage=agent]`: record on the run;
    deny reason for an unknown stage, else None. Only the stage title and model/agent name are stored, never the reason text."""
    decl = [(m.group(1), _ren(m.group(2).strip()), None, None) for m in SKIP_TAG.finditer(desc)]
    decl += [(m.group(1), _ren(m.group(2).strip()), m.group(3), None) for m in MODEL_TAG.finditer(desc)]
    decl += [(m.group(1), _ren(m.group(2).strip()), "*", m.group(3)) for m in AGENT_TAG.finditer(desc)]   # "*" = agent only
    decl += [(m.group(1), _ren(m.group(2).strip()), "", None) for m in END_TAG.finditer(desc)]   # "" = close the run
    for name, title, model, agent in decl:
        old = _load(path)["runs"].get(name)
        keep = old.get("proj") if isinstance(old, dict) and not old.get("end") else None
        proj = _project(ev, "Bash", name, title, keep)
        pl = _stages(proj, name) if proj else None
        if not pl or _apply_off(proj):
            continue
        if _idx(pl[0], title) < 0:
            _deny_save(path, name, "", "stage", now)   # ⚠"" title: an unknown title is description text
            return "%s has no stage %s; stages: %s" % (name, title, " → ".join(x["title"] for x in pl[0]))
        os.makedirs(MARK_DIR, exist_ok=True)
        with _Lock(path) as lk:
            if not lk.ok:
                continue
            d = _load(path)
            if model == "":
                r = d["runs"].get(name)
                if isinstance(r, dict) and not r.get("end"):
                    r = _run_of(d, name, cwd, now, False)
                    _mark(r, title, "done", now)
                    r["end"] = now
                    _ledger_add(r, name, now)
                    _save(path, d)
                    _closed(r.get("proj") or proj, name)
                continue
            o = d["runs"].get(name)
            if model is None and _boundary(pl[0], o, title, now):   # skipping the first stage of a run already past it = a new run
                _ledger_add(o, name, now)
            if model is None and _is_open(o, now) and 0 <= _idx(pl[0], title) <= _idx(pl[0], o.get("cur") or ""):
                continue   # ⚠the open run already passed this stage: a no-op, never a second run
            if model is None and isinstance(o, dict) and o.get("stop") and o.get("end") \
                    and _idx(pl[0], title) > _idx(pl[0], o.get("cur") or ""):
                continue   # ⚠skipping the rest of a stopped run acknowledges the stop; a fresh run here stayed open forever
            r = _run_of(d, name, cwd, now)
            r["proj"] = proj
            if model is None:
                if title not in r["skipok"]:
                    r["skipok"].append(title)
                _mark(r, title, "skip", now)
                if _skip_ends(pl[0], r):   # ⚠no Post follows a skip: without this the run stayed open until idle
                    r["end"] = now
                    _ledger_add(r, name, now)
                    _closed(proj, name)
            elif agent is not None:
                r["agents"][title] = agent
            else:
                r["models"][title] = model.lower()
            _save(path, d)
    return None


def _none_load(p):
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _none_save(p, d):
    os.makedirs(MARK_DIR, exist_ok=True)
    tmp = p + ".tmp.%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, p)


NONE_LOG = "none-log.jsonl"   # per-project declaration log in MARK_DIR (pl_runs.pl_none_counts reads it)
NONE_LOG_MAX = 262144         # bytes; over it the log is trimmed to its newest half
NONE_LOG_KEEP_S = 90 * 86400  # lines older than this are dropped at trim time


def _none_trim(p, now):
    """Rewrite the log keeping lines newer than NONE_LOG_KEEP_S, then at most the newest NONE_LOG_MAX // 2 bytes."""
    with _Lock(p) as lk:
        if not lk.ok:
            return
        with open(p, "rb") as f:
            lines = f.read().splitlines(True)
        keep = []
        for b in lines:
            try:
                if now - float(json.loads(b).get("t")) <= NONE_LOG_KEEP_S:
                    keep.append(b)
            except Exception:
                pass
        n, out = 0, []
        for b in reversed(keep):
            n += len(b)
            if n > NONE_LOG_MAX // 2:
                break
            out.append(b)
        tmp = p + ".tmp.%d" % os.getpid()
        with open(tmp, "wb") as f:
            f.write(b"".join(reversed(out)))
        os.replace(tmp, p)


def _none_log(proj, cat, now):
    """R1: append {v, proj, cat, t} to MARK_DIR/NONE_LOG. ⚠R2: category, time and project path only. Fail-silent."""
    try:
        os.makedirs(MARK_DIR, exist_ok=True)
        p = os.path.join(MARK_DIR, NONE_LOG)
        line = (json.dumps({"v": 1, "proj": proj, "cat": cat, "t": now}) + "\n").encode("utf-8")
        # ⚠same lock as _none_trim: an append between its read and os.replace lands in the old inode and is lost;
        # on lock timeout (LOCK_WAIT_S) append anyway: a rare lost line beats blocking the tool
        with _Lock(p):
            fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
        with open(p, "rb") as f:
            first = f.readline(4096)
        try:
            old = now - float(json.loads(first).get("t")) > NONE_LOG_KEEP_S
        except Exception:
            old = True   # a bad first line is dropped by the trim
        if old or os.path.getsize(p) > NONE_LOG_MAX:
            _none_trim(p, now)
    except Exception:
        pass   # ⚠a log failure must never block the tool


def _none_decl(sid, desc, now, ev=None):
    """Bash `[pl-none:<category>]`: store {v, cat, t} in plmark/<sid>.none.json and log it for the project; deny reason
    for an unknown category. ⚠Category and time only, never the description; ⚠never <sid>.json (agents.plm_of) or .runs.json."""
    if "[pl-none:" not in desc:
        return None
    m = NONE_TAG.search(desc)
    if not m or m.group(1) not in NONE_CATS:
        return "Unknown [pl-none:] category; use one of: %s" % ", ".join(NONE_CATS)
    try:
        proj = _none_proj(ev, "Bash") if isinstance(ev, dict) else None
    except Exception:
        proj = None
    if proj and m.group(1) != "explore" and _strict(proj) and not _apply_off(proj):
        return ("Strict mode (.claude/pipelines/_policy.json): [pl-none:%s] is not accepted here. "
                "Run small changes through [pl:quick-fix/수정]; [pl-none:explore] allows exploring only." % m.group(1))
    _none_save(os.path.join(MARK_DIR, sid + ".none.json"), {"v": 1, "cat": m.group(1), "t": now})
    if proj:
        _none_log(proj, m.group(1), now)
        if m.group(1) == "no-fit" and not ev.get("agent_id"):
            txt = _none_nudge(proj, now)
            _NONE_NOTE[:] = [txt, proj, now] if txt else []
    return None


NONE_NUDGE = "none-nudge.json"   # MARK_DIR {proj: t of the last no-fit nudge}
NONE_NUDGE_N = 3                 # no-fit declarations in the window (this one included) that trigger the nudge
NONE_NUDGE_S = 7 * 86400         # count window and per-project quiet period
_NONE_NOTE = []                  # [text, proj, t] of this Pre call's nudge; main() merges it into the flow's output


def _none_nudge(proj, now):
    """R1-R3 (#16): text for the Nth no-fit declaration of `proj` in NONE_NUDGE_S unless stamped in the window, else None.
    ⚠Count, window and project path only (the log holds no description). Stamping is _none_stamp's. Fail-silent."""
    try:
        p = os.path.join(MARK_DIR, NONE_LOG)
        with open(p, "rb") as f:
            f.seek(max(0, os.path.getsize(p) - NONE_LOG_MAX))
            lines = f.read(NONE_LOG_MAX).splitlines()
        n = 0
        for b in lines:
            try:
                x = json.loads(b)
                t = x.get("t")
                if x.get("proj") == proj and x.get("cat") == "no-fit" and not isinstance(t, bool) \
                        and 0 <= now - float(t) <= NONE_NUDGE_S:
                    n += 1
            except Exception:
                pass   # a cut first line or a bad row is skipped
        if n < NONE_NUDGE_N:
            return None
        sp = os.path.join(MARK_DIR, NONE_NUDGE)
        d = _none_load(sp)
        last = d.get(proj)
        if isinstance(last, (int, float)) and not isinstance(last, bool) and now - last < NONE_NUDGE_S:
            return None
        return ("Project %s had %d [pl-none:no-fit] declarations in the last 7 days. Offer the user a draft pipeline "
                "for this kind of work, and write .claude/pipelines/<name>.json only after the user agrees."
                % (proj, n))
    except Exception:
        return None


def _none_stamp(proj, now):
    """Record the nudge for `proj` in NONE_NUDGE (stale entries dropped). Raises on failure."""
    sp = os.path.join(MARK_DIR, NONE_NUDGE)
    d = {k: v for k, v in _none_load(sp).items() if isinstance(v, (int, float)) and not isinstance(v, bool)
         and now - v < NONE_NUDGE_S}
    d[proj] = now
    _none_save(sp, d)


def _none_emit(flow_out):
    """stdout text for this Pre: the flow's output with the pending nudge merged in, or the flow's output unchanged.
    ⚠Stamped only when the nudge goes out: a deny / unparseable flow output keeps it for the next no-fit."""
    try:
        txt, proj, now = _NONE_NOTE
        if flow_out:
            o = json.loads(flow_out)
            h = o.get("hookSpecificOutput") if isinstance(o, dict) else None
            if not (isinstance(h, dict) and set(o) == {"hookSpecificOutput"} and h.get("hookEventName") == "PreToolUse"
                    and set(h) == {"hookEventName", "additionalContext"} and isinstance(h["additionalContext"], str)):
                return flow_out
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                          "additionalContext": h["additionalContext"] + "\n\n" + txt}}
        else:
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": txt}}
        _none_stamp(proj, now)   # ⚠before printing: an unsaved stamp would nudge on every no-fit declaration
        return json.dumps(out, ensure_ascii=False)
    except Exception:
        return flow_out


def _none_proj(ev, tool):
    """Pipeline project of this edit (walk up from the edited file to its git root) or commit (cwd / its git root).
    ⚠Not session_dirs: any repo seen in the transcript would lend its pipelines to an edit in a repo without them."""
    if tool == "Bash":
        cwd = ev.get("cwd")
        return next((x for x in (cwd, _git_root(cwd)) if x and _has_pl(x)), None)
    ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
    fp = ti.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    if not (isinstance(fp, str) and os.path.isabs(fp)):
        return None
    cur, top = os.path.dirname(os.path.abspath(fp)), _git_root(os.path.dirname(os.path.abspath(fp)))
    while True:
        if _has_pl(cur):
            return cur
        up = os.path.dirname(cur)
        if cur == top or up == cur:
            return None
        cur = up


STRICT_GRACE_S = 15 * 60   # strict mode: edits/commits still allowed this long after a run of this session ended


def _strict(proj):
    """True only for <proj>/.claude/pipelines/_policy.json == {"enforce": "writes"}; anything else (missing,
    unreadable, unknown value) = False, i.e. the deny-once behaviour."""
    try:
        with open(os.path.join(proj, ".claude", "pipelines", "_policy.json"), encoding="utf-8") as f:
            d = json.load(f)
        return isinstance(d, dict) and d.get("enforce") == "writes"
    except Exception:
        return False


def _strict_why(proj, names):
    """Deny reason for strict mode: each pipeline name with its `use` line (clipped, metadata only)."""
    rows = []
    for n in names:
        try:
            with open(os.path.join(proj, ".claude", "pipelines", n + ".json"), encoding="utf-8") as f:
                u = json.load(f).get("use")
        except Exception:
            u = None
        u = " ".join(u.split())[:80] if isinstance(u, str) else ""
        rows.append("- %s%s" % (n, ": " + u if u else ""))
    return ("Strict mode (.claude/pipelines/_policy.json): no pipeline run is open in this session, so file edits "
            "and git commit are denied. Run the work through one with [pl:<name>/<stage>] tags:\n%s\n"
            "Small changes: [pl:quick-fix/수정]. [pl-none:explore] allows exploring only." % "\n".join(rows))


def _readonly(proj, name):
    """True only when <proj>/.claude/pipelines/<name>.json has "readonly": true; missing/unreadable = False, so the
    run still licenses edits as before (the readonly skip never applies on doubt)."""
    try:
        if not (isinstance(name, str) and _PLNAME.fullmatch(name) and isinstance(proj, str)):
            return False
        with open(os.path.join(proj, ".claude", "pipelines", name + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        return isinstance(d, dict) and d.get("readonly") is True
    except Exception:
        return False


_SHELL_PUNCT = "();<>|&\n"   # ⚠an unquoted newline separates commands like `;`
_SHELL_SEP = set(";|&()\n")   # punctuation that ends one shell command
# ⚠words that come before the real command: `if x; then sed -i …`, `FOO=1 tee f`, `env -u X tee f`
_SHELL_KW = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "time"}
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
# POSIX scratch roots (built from os.sep for tests/test_win_static.py); on Windows they resolve to \dev, \tmp on the
# current drive, which only widens the pass list there; tempfile.gettempdir() covers the Windows temp dir
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z0-9_]+)\1")
_WRITE_PASS = tuple(os.path.join(os.sep, *x) for x in (("dev",), ("tmp",), ("private", "tmp")))


def _punct(t):
    return bool(t) and all(c in _SHELL_PUNCT for c in t)


def _drop_heredocs(cmd):
    """Shell text without heredoc bodies (the `<<WORD` line itself stays): a body is data, not commands."""
    out, pend = [], []
    for line in cmd.split("\n"):
        if pend:
            if line.strip() == pend[0]:
                pend.pop(0)
            continue
        out.append(line)
        pend = [m.group(2) for m in _HEREDOC.finditer(line)]
    return "\n".join(out)


def _bash_writes(cmd, cwd, proj):
    """Heuristic: True when the shell command writes a file inside `proj` via > >> &> >| (>& to a file), tee or
    sed -i, also after then/do/VAR=/env prefixes. ⚠python -c, cp, mv are not caught. Unparseable text (ValueError) = False (fail-open)."""
    try:
        lx = shlex.shlex(_drop_heredocs(cmd or ""), posix=True, punctuation_chars=_SHELL_PUNCT)
        lx.whitespace, lx.whitespace_split = " \t\r", True
        toks = list(lx)
    except ValueError:
        return False
    base_dir = cwd if isinstance(cwd, str) else proj
    targets, i, n, cur = [], 0, len(toks), base_dir   # cur: directory after a literal `cd`; None = unknown
    pre = env = False   # pre: previous word was a command prefix; env: inside `env`'s own options
    while i < n:
        t, prev = toks[i], toks[i - 1] if i else None
        head = not _punct(t) and (pre or prev is None or _punct(prev) and any(c in _SHELL_SEP for c in prev))
        pre = False
        if head and (t in _SHELL_KW or _ASSIGN.match(t) or os.path.basename(t) == "env"
                     or env and t.startswith("-")):
            env, pre = env or os.path.basename(t) == "env", True
            i += 2 if env and t in ("-u", "-C") else 1   # env -u NAME / -C DIR take a value
            continue
        env = False
        if _punct(t) and ">" in t:
            op = t[t.find(">"):]
            if i + 1 < n and not _punct(toks[i + 1]):
                tg = toks[i + 1]
                # ⚠>& N / >&- duplicate a descriptor; only a word target is a file
                if not (tg.isdigit() or (op.startswith(">&") and tg == "-")):
                    targets.append((tg, cur))
                i += 1
        elif head:
            base = os.path.basename(t)
            j, args = i + 1, []
            while j < n and not _punct(toks[j]):
                args.append(toks[j])
                j += 1
            if base == "cd":
                # ⚠a later relative target resolves against a literal cd; any other form = unknown dir (fail-open)
                a = args[0] if args else ""
                lit = bool(a) and cur is not None and not (a[0] in "~-" or "$" in a or "`" in a)
                cur = os.path.normpath(os.path.join(cur, a)) if lit else None
            elif base == "tee":
                targets += [(a, cur) for a in args if a and not a.startswith("-")]
            elif base in ("sed", "gsed") and any(a == "--in-place" or a.startswith("--in-place=")
                                                 or re.match(r"-[A-Za-z]*i", a) for a in args):
                words, script = [], any(a in ("-e", "-f") or a.startswith("--expression") for a in args)
                k = 0
                while k < len(args):
                    a = args[k]
                    if a in ("-e", "-f"):
                        k += 2
                        continue
                    if a and not a.startswith("-"):
                        words.append(a)
                    k += 1
                targets += [(w, cur) for w in (words if script else words[1:])]
            i = j - 1
        i += 1
    root = os.path.realpath(proj)
    tmpd = os.environ.get("TMPDIR")
    passes = [os.path.realpath(p) for p in _WRITE_PASS + (tempfile.gettempdir(),) + ((tmpd,) if tmpd else ())]
    for tg, d in targets:
        tg = os.path.expanduser(os.path.expandvars(tg))
        if "$" in tg or "`" in tg or (d is None and not os.path.isabs(tg)):
            continue   # unresolved expansion or unknown cd: unknown target, fail-open
        p = os.path.realpath(os.path.join(d or base_dir, tg))
        # ⚠a tmp root passes only when the repo itself is not under it (test repos live in /tmp on Linux)
        if any((p == q or p.startswith(q + os.sep)) and not (root == q or root.startswith(q + os.sep)) for q in passes):
            continue
        if p == root or p.startswith(root + os.sep):
            return True
    return False


FIX_PL = "security-fix"
FIX_REQ_S = 86400   # an open security-fix request gates its repo this long after it was sent
FIX_REVIEW = "리뷰"   # fallback only: the review is the file's last stage, so a renamed title still lifts the gate


def _fix_titles():
    """(first, last) stage titles of DATA_DIR/.claude/pipelines/security-fix.json; the shipped titles if unreadable."""
    got = _stages(DATA_DIR, FIX_PL)
    return (got[0][0]["title"], got[0][-1]["title"]) if got else ("수정", FIX_REVIEW)


def _fix_reviewed(sid, at):
    """True when recipient session `sid` has a security-fix run (current or in "past") started at/after `at` whose
    review stage is done. ⚠pl_reqs stamps `closed` only while a viewer tab polls, so the hook cannot wait for it."""
    try:
        if not (isinstance(sid, str) and SID.match(sid)):
            return False
        d = _load(os.path.join(MARK_DIR, sid + ".runs.json"))
        past = d.get("past") if isinstance(d.get("past"), dict) else {}
        runs = [d["runs"].get(FIX_PL)] + list(past.get(FIX_PL) or [])[-PAST_MAX:]
        review = _fix_titles()[1]
        for r in runs:
            if isinstance(r, dict) and isinstance(r.get("st"), dict) and float(r.get("t0") or 0) >= at \
                    and (r["st"].get(review) or {}).get("s") == "done":
                return True
        return False
    except Exception:
        return False


def _fix_req(repo, now):
    """Newest open security-fix request (DATA_DIR/plreq.json, written only by sidereus/pl_reqs.py) for `repo`, else
    None. ⚠Read-only, metadata only; any read/parse error = None (fail-open: this hook runs for every session)."""
    try:
        with open(os.path.join(DATA_DIR, "plreq.json"), encoding="utf-8") as f:
            reqs = json.load(f).get("reqs")
        root, best = os.path.realpath(repo), None
        for r in reqs if isinstance(reqs, list) else ():
            if not (isinstance(r, dict) and r.get("pipeline") == FIX_PL and not r.get("stop") and not r.get("closed")
                    and isinstance(r.get("repo"), str) and os.path.isabs(r["repo"])):
                continue
            at = r.get("at")
            if isinstance(at, bool) or not isinstance(at, (int, float)) or not at or now - at >= FIX_REQ_S:
                continue
            if os.path.realpath(r["repo"]) == root and (best is None or at > best["at"]) \
                    and not _fix_reviewed(r.get("sid"), float(at)):
                best = {"repo": r["repo"], "at": float(at)}
        return best
    except Exception:
        return None


def _fix_gate(ev, sid, tool, sub, now):
    """R3: an open security-fix request for the repo of this edit / commit / shell write denies it unless this session
    has a security-fix run open (or ended < STRICT_GRACE_S ago); applies with no _policy.json. True when denied; fail-open.
    ⚠[pl-none], the nudge stamp and «Apply» off never lift it; the run matches by name only (it runs from the home with --repo)."""
    try:
        cwd = ev.get("cwd")
        if tool == "Bash":
            repo = _git_root(cwd) or cwd
        elif tool in EDITS:
            ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
            fp = ti.get("notebook_path" if tool == "NotebookEdit" else "file_path")
            if not (isinstance(fp, str) and os.path.isabs(fp)):
                return False
            repo = _git_root(os.path.dirname(os.path.abspath(fp)))
        else:
            return False
        req = _fix_req(repo, now) if repo else None   # plreq.json first: no request = no shell parsing
        if not req:
            return False
        if tool == "Bash":
            cmd = _shell_cmd(ev.get("tool_input")) or ""
            if not _commit_m(cmd) and not _bash_writes(cmd, cwd, repo):
                return False
        r = _load(os.path.join(MARK_DIR, sid + ".runs.json"))["runs"].get(FIX_PL)
        if isinstance(r, dict):
            if not r.get("end") and (sub or now - float(r.get("t1") or 0) <= IDLE_S):
                return False
            if r.get("end") and 0 <= now - float(r.get("end") or 0) <= STRICT_GRACE_S:
                return False
        return _deny("An open security-fix request for %s (sent %s) gates edits and git commit in that repo. It lifts "
                     "when the run's review stage finishes, on «Stop», or after 24 h. Open the run with an Agent/Bash description tagged [pl:security-fix/%s], "
                     "following %s, or the owner can press «Stop» on the request line."
                     % (req["repo"], time.strftime("%Y-%m-%d %H:%M", time.localtime(req["at"])), _fix_titles()[0],
                        os.path.join(DATA_DIR, ".claude", "pipelines", FIX_PL + ".json")))
    except Exception:
        return False


def _none_gate(ev, sid, tool, desc, now):
    """First file edit / main `git commit` of a session in a pipeline project with no open run and no [pl-none]:
    deny once with the pipeline names; in strict mode (_strict) deny every time. True when denied; fail-open."""
    try:
        sub = bool(ev.get("agent_id"))
        if _fix_gate(ev, sid, tool, sub, now):   # ⚠before the no-pipelines return: the request's repo may have none
            return True
        if tool == "Bash":
            cmd = _shell_cmd(ev.get("tool_input")) or ""
            # a tagged command already follows the pipeline protocol
            # ⚠no tag short-circuit here: in strict mode a bare/unknown tag must not pass (checked below off strict)
            if not _commit_m(cmd):
                bp = _none_proj(ev, tool)   # strict only: a shell write into the repo is gated like an edit
                if not (bp and _strict(bp) and _bash_writes(cmd, ev.get("cwd"), bp)):
                    return False
        elif tool not in EDITS:
            return False
        proj = _none_proj(ev, tool)
        if not proj or _apply_off(proj):
            return False
        strict = _strict(proj)
        if sub and not strict:
            return False
        p = os.path.join(MARK_DIR, sid + ".none.json")
        if not strict:
            d = _none_load(p)
            if d.get("cat") or d.get("nudge") or "[pl" in desc:
                return False
        runs = _load(os.path.join(MARK_DIR, sid + ".runs.json"))["runs"].items()
        for rn, r in runs:
            # ⚠strict: a read-only pipeline run (review) never licenses edits or commits
            if strict and isinstance(r, dict) and _readonly(r.get("proj") or r.get("cwd") or proj, rn):
                continue
            # ⚠subagent: any un-ended run counts (no IDLE_S), so a long stage is never cut off mid-way
            if isinstance(r, dict) and not r.get("end") and (sub or now - float(r.get("t1") or 0) <= IDLE_S):
                return False
            # ⚠strict: a foreground last stage sets `end`, so the orchestrator's final commit comes just after it
            if strict and isinstance(r, dict) and r.get("end") and 0 <= now - float(r.get("end") or 0) <= STRICT_GRACE_S:
                return False
        names = sorted(n[:-5] for n in os.listdir(os.path.join(proj, ".claude", "pipelines"))
                       if n.endswith(".json") and _PLNAME.fullmatch(n[:-5]))
        if strict:
            # ⚠deny every time, no nudge stamp: a once-only deny let retries edit with no run at all
            return _deny(_strict_why(proj, names))
        _none_save(p, {"v": 1, "nudge": now})   # ⚠before the deny: an unsaved nudge would deny every edit
        return _deny("This project has pipelines (%s) and no run is open in this session. Run the work through one "
                     "with [pl:<name>/<stage>] tags, or declare it outside them once with a Bash description "
                     "[pl-none:<category>] (category: %s). Shown once per session; retrying proceeds."
                     % (", ".join(names), " | ".join(NONE_CATS)))
    except Exception:
        return False


def _none_clear(ev, now):
    """A tagged Pre that left a run open drops `nudge` from <sid>.none.json (keeps `cat`; no keys left = file removed).
    ⚠Ended runs leave the session row after PLR_KEEP_S, so a stale nudge would read as undeclared work. Fail-silent."""
    try:
        sid, ti = ev.get("session_id"), ev.get("tool_input")
        desc = ti.get(FIELD.get(ev.get("tool_name"), "description")) if isinstance(ti, dict) else None
        cmd = _shell_cmd(ti) or ""
        if ev.get("hook_event_name") not in ("PreToolUse", "BeforeTool") or not (isinstance(sid, str) and SID.match(sid)) \
                or not (TAG.search(desc if isinstance(desc, str) else "") or MARK.match(cmd)):
            return
        p = os.path.join(MARK_DIR, sid + ".none.json")
        d = _none_load(p)
        if "nudge" not in d or not any(isinstance(r, dict) and not r.get("end") and now - float(r.get("t1") or 0) <= IDLE_S
                                       for r in _load(os.path.join(MARK_DIR, sid + ".runs.json"))["runs"].values()):
            return
        d.pop("nudge", None)
        if d.get("cat"):
            _none_save(p, d)
        else:
            os.remove(p)
    except Exception:
        pass


def _none_pre(plat, ev):
    """cc main-session Pre: `[pl-none:]` declaration, then the first-edit / commit gate. True when denied; fail-open."""
    try:
        sid, tool, ti = ev.get("session_id"), ev.get("tool_name"), ev.get("tool_input")
        if plat != "cc" or ev.get("hook_event_name") != "PreToolUse" or not (isinstance(sid, str) and SID.match(sid)) \
                or not (isinstance(ev.get("cwd"), str) and os.path.isabs(ev["cwd"])):
            return False
        desc = ti.get("description") if tool == "Bash" and isinstance(ti, dict) else None
        desc = desc if isinstance(desc, str) else ""
        why = _none_decl(sid, desc, _now(), ev)
        return _deny(why) if why else _none_gate(ev, sid, tool, desc, _now())
    except Exception:
        return False


def _norm_ev(ev):
    """Off cc: Cursor camelCase event -> PascalCase; an empty cwd (Cursor tool events) -> first absolute workspace root.
    ⚠Without it `_flow` returns early (cwd must be absolute) and no Cursor run ever opens."""
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
    if not isinstance(ev, dict):
        return
    if plat != "cc":
        ev = _norm_ev(ev)
    denied = False
    del _NONE_NOTE[:]
    try:
        try:   # pipeline `guards` (hooks/pl_guard.py); ⚠fail-open: a missing or broken guard module runs the flow unguarded
            import importlib.util as _iu
            import types as _ty
            _sp = _iu.spec_from_file_location("pl_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pl_guard.py"))
            _g = _iu.module_from_spec(_sp)
            _sp.loader.exec_module(_g)
            _me = _ty.SimpleNamespace(**globals())   # this module's current (test-patched) names
        except Exception:
            _g = None
        denied = _none_pre(plat, ev)
        if not denied:
            # ⚠one JSON object per Pre: with a nudge pending the flow's output is buffered and wins if non-empty
            if _NONE_NOTE:
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        denied = _g.run(plat, ev, _me, _flow) if _g else _flow(plat, ev)
                finally:
                    sys.stdout.write(_none_emit(buf.getvalue()))
            else:
                denied = _g.run(plat, ev, _me, _flow) if _g else _flow(plat, ev)
    except Exception as e:   # __main__ swallows it; leave the type name only
        _why(ev, "exc:" + type(e).__name__)
        raise
    finally:
        if not denied:   # ⚠a denied `git commit` never ran: closing the run anyway made every skip open a new run
            _none_clear(ev, _now())
            _commit_close(ev, _now())
        _autoscore()


# `git commit` / `git -C <dir> commit` as a word; the command text itself is never stored.
# ⚠Global options and a path prefix (/usr/bin/git, git -c k=v, git --no-pager) must still match: strict mode gates commits on it.
_COMMIT_RE = re.compile(r"(?:^|[\s;&|(])(?:\S*/)?git(?:\s+(?:-C\s+(\"[^\"]*\"|'[^']*'|\S+)|-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+commit(?![\w-])")
# ⚠--dry-run counts only as an option of that same commit command; a bare substring test let a message text carry it.
_DRY_RE = re.compile(r"\scommit(?![\w-])[^;&|\n]*?\s--dry-run(?![\w-])")


def _commit_m(cmd):
    """Match of a real (not --dry-run) `git commit` in a shell command, else None."""
    m = _COMMIT_RE.search(cmd or "")
    return None if not m or _DRY_RE.search(re.sub(r"\"[^\"]*\"|'[^']*'", "", cmd[m.start():])) else m


def _commit_close(ev, now):
    """Shell Pre running `git commit` closes this session's open run(s) of that project: cur «run» -> done, end=now.
    ⚠Fail-silent and never denies — a commit is the natural end of one change, so the next tag opens a fresh run."""
    try:
        if EVENT.get(ev.get("hook_event_name"), ev.get("hook_event_name")) != "PreToolUse" or ev.get("tool_name") not in SHELL:
            return
        # ⚠A subagent's hook event carries the parent's session_id plus agent_id. A stage agent that commits its own
        #   slice is still mid-stage; closing on it marked a live implement stage «Stopped» while its agent ran on.
        #   So a subagent commit only stamps cm; main's commit stamps and closes.
        sub = bool(ev.get("agent_id"))
        sid, cwd, cmd = ev.get("session_id"), ev.get("cwd"), _shell_cmd(ev.get("tool_input"))
        m = _commit_m(cmd)
        if not m or not (isinstance(sid, str) and SID.match(sid) and isinstance(cwd, str) and os.path.isabs(cwd)):
            return
        # ⚠The commit's own tag picks the runs it may close: `[pl:-]` = work outside every run, `[pl:<name>/...]` = that
        #   run only. A pipeline whose file lives in this repo but drives another one (arch-map) was closed mid-run by an
        #   unrelated commit here, so its next stage was denied as a jump past stages that had run.
        ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
        desc = ti.get("description") if isinstance(ti.get("description"), str) else ""
        mk, tg = MARK.match(cmd), TAG.search(desc)
        if "[pl:-]" in desc or (mk and mk.group(2)):
            return
        only = tg.group(1) if tg else (mk.group(3) if mk else None)
        dirs = [cwd]
        if m.group(1):
            c = m.group(1).strip("\"'")
            dirs.append(c if os.path.isabs(c) else os.path.join(cwd, c))
        dirs = [os.path.realpath(x) for x in dirs]
        dirs += [g for g in (_git_root(x) for x in dirs) if g]
        path = os.path.join(MARK_DIR, sid + ".runs.json")
        if not os.path.exists(path):
            return
        with _Lock(path) as lk:
            if not lk.ok:
                return
            d, hit = _load(path), False
            for rn, r in d["runs"].items():
                proj = r.get("proj") if isinstance(r, dict) else None
                if (only and rn != only) or not isinstance(proj, str) or not proj or r.get("end") or now - float(r.get("t1") or 0) > IDLE_S:
                    continue
                p = os.path.realpath(proj)
                if not any(x == p or x.startswith(p + os.sep) for x in dirs):
                    continue
                st = r.get("st") if isinstance(r.get("st"), dict) else {}
                cur = r.get("cur")
                r["st"], hit = st, True
                # ⚠A slice agent of an earlier stage can commit after the run moved on: stamp its own stage, not cur.
                c = _cm_stage(r, rn, ev) if sub else cur
                if isinstance(st.get(c), dict):   # commit times of that stage (newest last, CM_MAX)
                    cm = [x for x in (st[c].get("cm") if isinstance(st[c].get("cm"), list) else []) if isinstance(x, (int, float))]
                    st[c]["cm"] = (cm + [now])[-CM_MAX:]
                if sub:
                    continue
                # ⚠A commit tagged for this run at a stage with a next stage (release: tag commits, deploy follows) is
                #   mid-run: closing it archived the run and denied the next stage as a jump. Untagged/last-stage closes.
                sd = _stages(proj, rn) if only else None
                ci = _idx(sd[0], cur) if sd else -1
                if ci >= 0 and _plain_next(sd[0], ci) >= 0:
                    r["t1"] = now
                    continue
                if isinstance(st.get(cur), dict) and st[cur].get("s") == "run":
                    _mark(r, cur, "done", now)
                r["end"], r["t1"] = now, now
                _ledger_add(r, rn, now)
                _closed(proj, rn, now)
            if hit:
                _save(path, d)
    except Exception:
        pass


def _closed_tail(r, st, title, now):
    """True when a Bash of `title` hits a run closed on its last stage `title`: only that stage's t1 moves.
    ⚠more Bash of a closed last stage must not open a new run (its outcome map would reset); t1 moves so the stage's
    elapsed covers that work instead of reading 0s. Last stage only: a run closed on an earlier stage swallowed that
    stage's Bash mark of the next run (e.g. main's requirements stage), so the following dispatch was denied as
    skipping it."""
    if not (isinstance(r, dict) and r.get("end") and r.get("cur") == title
            and _plain_next(st, _idx(st, title)) < 0 and now - float(r["end"]) <= IDLE_S):
        return False
    e = (r.get("st") or {}).get(title)
    if isinstance(e, dict):
        e["t1"] = now
    return True


def _flow(plat, ev):
    event, tool = ev.get("hook_event_name"), ev.get("tool_name")
    sid, cwd = ev.get("session_id"), ev.get("cwd")
    if not isinstance(sid, str) or not SID.match(sid) or not (isinstance(cwd, str) and os.path.isabs(cwd)):
        return
    shell = ""   # "" = cc tag · "start" · "end" · "fail" (shell marker)
    if plat == "cc":
        field = FIELD.get(tool)
        if not field or (event == "PostToolUse" and tool not in DISPATCH):
            return
        ti = ev.get("tool_input") or {}
        desc = ti.get(field) if isinstance(ti, dict) else None
        desc = desc if isinstance(desc, str) else ""
        path = os.path.join(MARK_DIR, sid + ".runs.json")
        if event == "PreToolUse" and tool == "Bash" and "[pl-" in desc:
            why = _declare(ev, cwd, path, desc, _now())
            if why:
                return _deny(why)
        m = TAG.search(desc)
        if not m:
            # ⚠Untagged Agent/Task is already denied by pl_mark.py nudge; only SendMessage is checked here.
            if event == "PreToolUse" and tool == "SendMessage" and "[pl:-]" not in desc:
                o = _open_run(path, _now())
                if o:
                    _deny("Pipeline run %s is open (stage %s): start the summary with [pl:%s/<stage>], or [pl:-] "
                          "if this message is outside the run." % (o[0], o[1] or "-", o[0]))
                    _deny_save(path, o[0], o[1], "tag", _now())
                    return True
            _nudge(ev, desc, path, _now())
            return
        name, title = m.group(1), _ren(m.group(2).strip())
    else:
        event = EVENT.get(event, event)
        cmd = _shell_cmd(ev.get("tool_input")) if tool in SHELL else None
        m = MARK.match(cmd) if cmd else None
        if not m or m.group(2):
            return
        shell = "fail" if m.group(5) else "end" if m.group(1) else "start"
        if (shell == "start") == (event == "PostToolUse"):   # start counts on Pre, end on Post
            return
        name, title = m.group(3), _ren(m.group(4).strip())
    path = os.path.join(MARK_DIR, sid + ".runs.json")   # ⚠never <sid>.json: agents.plm_of reads that name
    now = _now()
    old = _load(path)["runs"].get(name)   # lockless peek: only for the open run's project
    keep = old.get("proj") if isinstance(old, dict) and not old.get("end") and now - float(old.get("t1") or 0) <= IDLE_S else None
    proj = _project(ev, tool, name, title, keep)
    pl = _stages(proj, name) if proj else None
    if not pl or _apply_off(proj):
        _why(ev, "no-project" if not proj else "no-stages" if not pl else "apply-off")
        return
    st, after = pl
    if _idx(st, title) < 0:
        if event == "PreToolUse" and not shell:
            _deny("%s has no stage %s; stages: %s" % (name, title, " → ".join(x["title"] for x in st)))
            _deny_save(path, name, "", "stage", now)
            return True
        return
    os.makedirs(MARK_DIR, exist_ok=True)
    out = None
    with _Lock(path) as lk:
        if not lk.ok:
            _why(ev, "lock")
            return
        d = _load(path)
        r = d["runs"].get(name)
        if event == "PostToolUse":
            if not isinstance(r, dict) or r.get("end"):
                _why(ev, "post-no-run" if not isinstance(r, dict) else "post-ended")
                return
            r = _run_of(d, name, cwd, now, False)
            if shell:
                text = end(name, title, st, after, r, shell == "fail", now)
                text = text if plat in EMIT else None
            else:
                bg = _is_bg(ev)
                if bg and tool in ("Agent", "Task"):   # a background agent's later commit then matches this stage by id
                    _ag_note(r, title, _bg_aid(ev))
                text = post(name, title, st, after, r, bg, now)
            if r.get("end"):   # post() ended the run (last stage back)
                _closed(r.get("proj") or proj, name)
            if text:
                out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        else:
            if tool == "Bash" and _closed_tail(r, st, title, now):
                _save(path, d)
                return
            # ⚠Before was_open: a boundary-closed run is not open, so a refused dispatch below saves nothing.
            if _boundary(st, r, title, now, tool == "SendMessage"):   # ⚠SendMessage = a fix loop of this run's agent
                _ledger_add(r, name, now)
            was_open = _is_open(r, now)
            r = _run_of(d, name, cwd, now)
            r["proj"] = proj   # later Bash/SendMessage/Post of this run use the same file
            fit = None if shell else _fit(ev, tool, name, st[_idx(st, title)], r, [proj, cwd, _git_root(cwd)])
            if fit:
                _deny(fit[1])
                if was_open:   # only the count is saved: the refused dispatch never ran, so no new run is created
                    _deny_note(r, title, fit[0], now)
                    try:
                        _save(path, d)
                    except Exception:
                        pass
                return True
            if "h0" not in r:   # HEAD at run start; ⚠not in _commit_close (Pre runs before the commit exists)
                h = _head(proj)
                if h:
                    r["h0"] = h
            why = _resume_note(r, now, pre(tool, cwd, name, title, st, r, now, bool(shell)))
            if why and shell:
                # ⚠No deny contract is verified for other CLIs: the jump is recorded as skip and the stage starts anyway.
                for x in _jumped(st, r, title):
                    r["skipok"].append(x)
                    _mark(r, x, "skip", now)
                why = _resume_note(r, now, pre(tool, cwd, name, title, st, r, now, True) and None)
            if not why and tool == "SendMessage":
                ti = ev.get("tool_input")
                _ag_note(r, title, ti.get("to") if isinstance(ti, dict) else None)
            if not why and tool == "Bash" and not shell and not r["ret"] and _plain_next(st, _idx(st, title)) < 0:
                # ⚠No `end` here: an ended run never takes the main marker, so the stage read as over while main still
                #   worked through it. It stays «run» until a `git commit` or pl_runs' stale close; `tail` exempts it
                #   from the untagged-SendMessage deny (it gets no Post, so it would deny for LOST_S).
                r["tail"] = title
                r["st"][title]["t1"] = now
            if why:
                _deny_note(r, title, "jump", now)
                out = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                              "permissionDecision": "deny", "permissionDecisionReason": why}}
        _save(path, d)
    if out:
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return bool(out) and event == "PreToolUse"


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows codepage cannot encode Korean deny reasons; hook JSON is UTF-8
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
