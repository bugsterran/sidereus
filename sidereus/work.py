"""Session and agent work views (GET /api/work) and the allowed-cwd gate."""
import os
import re
import time
from sidereus import claude_roots
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _proj_name, _sid8, _slug
from sidereus.live import _sid_transcript
from sidereus.steps import (AGENT_SAYS_MAX, AGENT_STEPS_MAX, SESS_TAIL, _cap_edit_bodies, _open_or_tail,
    _res_is_code, _work_scan)
from sidereus.agents import _agent_meta
from sidereus.sessions import sessions_rows
from sidereus.redact import redact_work


_ALLOW = [0.0, {}]


def _allowed_cwds(ttl=5):
    """**Allowed repo list** used by the work log and diff. Cached briefly.

    ★Why (2026-09-02; the work log sometimes failed to load): these endpoints reran all of `sessions()` per request —
      it contains `ps` (with timeout), git and transcript parsing, so it is heavy, and the moment process lookup slowed
      (the `⚠ process lookup is slow` warning really appears) the list wobbled and **open tabs died with
      "Only sessions shown on screen can be opened.".**
      The 2.5 s poll already does the same computation, so holding it 5 s removes the wobble."""
    if _ALLOW[1] and time.time() - _ALLOW[0] < ttl:
        return _ALLOW[1]
    got = {}
    try:
        for r in sessions_rows():   # ⚠request path: poll snapshot, never a cold sessions()
            # ⚠a Gemini row never replaces the Claude row of the same cwd (it has no repos — diff/branch allow list would shrink)
            if r.get("cwd") and (r.get("plat") in (None, "", "cc") or r["cwd"] not in got):
                got[r["cwd"]] = r
    except Exception:
        return _ALLOW[1] or {}        # on failure use **the last value** (never kill the tab with an empty list)
    _ALLOW[0] = time.time()
    _ALLOW[1] = got
    return got


_SID_SAFE = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$")   # session id — hex and hyphens only


def _under_projects(fp):
    """realpath of fp if it lies strictly under one Claude root's projects dir, else "".
    ⚠Path guard for every root: never the root dir itself (settings, credentials) and never a `..` escape."""
    try:
        rp = os.path.realpath(fp)
    except (OSError, ValueError, TypeError):
        return ""
    for p in claude_roots.projects_dirs(CLAUDE_PROJECTS):
        base = os.path.realpath(p).rstrip(os.sep)
        if base and rp.startswith(base + os.sep):   # ⚠"/" strips to "" and would match everything
            return rp
    return ""


def _slug_files(cwd):
    """Transcripts of cwd's slug dir in every Claude root, newest first."""
    out = []
    for p in claude_roots.projects_dirs(CLAUDE_PROJECTS):
        d = os.path.join(p, _slug(cwd))
        try:
            out += [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")]
        except OSError:
            continue
    try:
        return sorted(out, key=os.path.getmtime, reverse=True)
    except OSError:
        return []


def _sid_path(cwd, sid):
    """Session id -> that session's transcript path ("" if malformed or not found).

    ⚠`sid` is **external input** (query parameter). Whitelist it before using it as a file name, and reject
      a normalized path outside every Claude root's projects dir — `../` must not read arbitrary files.
    ★Lookup order: cwd slug → full depth-1 scan (existing convention of `_sid_transcript` `:1090`).
      The timeline may override cwd with `srow.cwd`, so the file may not be under that slug."""
    if not sid or not _SID_SAFE.match(sid):
        return ""
    cands = [os.path.join(p, _slug(cwd or ""), sid + ".jsonl") for p in claude_roots.projects_dirs(CLAUDE_PROJECTS)]
    hit = _sid_transcript(sid)
    if hit:
        cands.append(hit)
    for c in cands:
        rp = _under_projects(c)
        if rp and os.path.isfile(rp):
            return rp
    return ""


def _past_row(cwd, sid):
    """Allow row for a finished session no longer in `sessions()` — its transcript must sit under cwd's own slug dir."""
    fp = _sid_path(cwd, sid) if (cwd and sid) else ""
    if not fp or os.path.basename(os.path.dirname(fp)) != _slug(cwd):
        return None
    return {"cwd": cwd, "project": _proj_name(cwd), "_fp": fp}


def session_work(cwd, sid="", at=None):
    """**What the session (main shell) did recently** — same view and parser as the subagent modal.

    Shown the same way as subagents: the work popup is the one owner-approved exception to "metadata only" (AGENTS.md rule 1).
    With `sid`, **that session's file** is read; cwd alone opened the newest session in that folder, not the clicked one.
    ⚠Every current caller sends `sess:<cwd>|<sid>`; the no-sid branch (cwd's newest) is kept only for old saved tabs.
    ★Reads only the tail — session transcripts grow to 910MB."""
    # History tab opens finished sessions too: lookup widened by sid+slug, content unchanged.
    row = _allowed_cwds().get(cwd or "") or _past_row(cwd, sid)
    if not row:
        return {"ok": False, "msg": "Only sessions shown on screen can be opened."}
    if sid:
        fp = _sid_path(cwd, sid)
        if not fp:
            return {"ok": False, "msg": "Cannot read the transcript for session {sid}.", "vars": {"sid": _sid8(sid)}}
    else:
        files = _slug_files(cwd)
        if not files:
            return {"ok": False, "msg": "Could not find the session transcript."}
        fp = files[0]
    # `at` only with a sid: the window ending at that moment (a failure seen in the retro tab), else the live tail.
    at = at if (sid and isinstance(at, (int, float)) and 0 < at < 1e11) else None   # also drops nan/inf
    sc, err = _work_scan(_open_or_tail(fp, tail=SESS_TAIL, at=at), cwd)
    if err:
        return dict({"ok": False}, **err)
    steps, says, results, _prompt, first, last, luser = sc
    for st in steps:
        r = results.get(st.get("id"))
        if r:
            r["code"], r["lang"] = _res_is_code(st.get("tool"), st.get("arg"))
            st["res"] = r
        st.pop("id", None)
    tools = {}
    for st in steps:
        tools[st["tool"]] = tools.get(st["tool"], 0) + 1
    # ★Let the screen say which session (clicking an old bar was indistinguishable from the newest).
    #   ⛔Metadata only — up to the first 8 chars of the session id.
    _lab = (" · session " + _sid8(sid)) if sid else ""
    steps = steps[-AGENT_STEPS_MAX:]
    cut_ed = _cap_edit_bodies(steps)
    return redact_work({"ok": True, "sid": sid or "", "cutEdits": cut_ed,
            "type": (row.get("project") or os.path.basename(cwd) or "Session") + _lab,
            "desc": cwd + _lab, "depth": 1, "first": first, "last": last,
            # the instruction slot gets **the last** human utterance — only the tail is read, so the "first user" is not the instruction
            "prompt": luser, "says": says[-AGENT_SAYS_MAX:],
            "cutSays": max(0, len(says) - AGENT_SAYS_MAX),
            "steps": steps[-AGENT_STEPS_MAX:], "cutSteps": 0, "tail": SESS_TAIL, "at": int(at) if at else None,
            "tools": sorted(tools.items(), key=lambda kv: -kv[1]),
            "size": (os.path.getsize(fp) if os.path.exists(fp) else 0), **_work_acct(sid, fp)})


def _work_acct(sid, fp):
    """acct · acctDir (~-shortened) · acctPrimary for the header; {} with a single account (no change there)."""
    accs = claude_roots.accounts()
    if len(accs) < 2:
        return {}
    lab, d = claude_roots.acct_of(sid or os.path.basename(fp)[:-6], fp)
    prim = not lab
    if prim:
        p = next((a for a in accs if a.get("primary")), None) or {}
        lab, d = p.get("label") or "", p.get("dir") or ""
    home = claude_roots.SCAN_HOME.rstrip(os.sep)
    if d and home and (d == home or d.startswith(home + os.sep)):
        d = "~" + d[len(home):]
    return {"acct": lab, "acctDir": d, "acctPrimary": prim} if lab else {}


_AID_RE = re.compile(r"^a[0-9a-f]{6,40}$")   # agent id = subagents/agent-<id>.meta.json


def agent_work(cwd, tid, sid=""):
    """What the subagent did — **tool footprints** (name, target, time) plus its own text replies (`says`,
    steps.py assistant text blocks — the approved work-popup exception, AGENTS.md rule 1).

    ★Not uploading conversation bodies is this page's principle (file header comment). But for "what did the agent
      do", the tool calls are the answer, so metadata suffices — what it read and ran is all in the footprints.
    ★cwd is validated against the same allow list as diff; tid only if it really exists in that session's meta."""
    past = _past_row(cwd, sid)
    row = _allowed_cwds().get(cwd or "") or past
    if not row:
        return {"ok": False, "msg": "Only sessions shown on screen can be opened."}

    files = _slug_files(cwd)
    if past:
        files = [past["_fp"]] + [f for f in files if f != past["_fp"]]   # parent session first: past agents lie beyond files[:6]
    if not files:
        return {"ok": False, "msg": "Could not find the session transcript."}
    # ★Don't look at **only the newest** transcript — opening a new session in the same path (measured: repo-A and
    #   repo-B have 2 transcripts each) kills any tab open on the previous session's agent.
    #   Scan the project's transcripts newest first to find **the session holding that tid**.
    m = None
    for _f in files[:6]:
        _md = _agent_meta(_f[:-len(".jsonl")], ttl=5)
        # ⚠A resumed agent's row tid is the SendMessage tool_use id, not meta toolUseId: also accept the agent id (meta file name).
        #   Strict id pattern + lookup among this session's scanned meta only; the id never becomes a path.
        _mm = _md.get(tid) or (next((v for v in _md.values() if v.get("_id") == tid), None) if _AID_RE.match(tid or "") else None)
        if _mm:
            m = _mm
            break
    if not m:
        return {"ok": False, "msg": "Could not find that subagent's record (it may not be written yet)."}

    fp = m.get("_file") or ""
    # ★Instruction and agent utterances are included too.
    #   **This view alone is an exception** to the header's "metadata only" rule — it exists for the user to see their own
    #   sessions' work, and that decision was the user's. In return there are caps, and truncation is stated.
    _sc, _err = _work_scan(_open_or_tail(fp), cwd)
    if _err:
        return dict({"ok": False}, **_err)
    steps, says, results, prompt, first, last, _luser = _sc
    # attach results to each footprint — they are in the same file, so no extra reads
    for st in steps:
        r = results.get(st.get("id"))
        if r:
            r["code"], r["lang"] = _res_is_code(st.get("tool"), st.get("arg"))
            st["res"] = r
        st.pop("id", None)
    cut = max(0, len(steps) - AGENT_STEPS_MAX)
    tools = {}
    for st in steps:
        tools[st["tool"]] = tools.get(st["tool"], 0) + 1
    steps = steps[-AGENT_STEPS_MAX:]
    cut_ed = _cap_edit_bodies(steps)
    return redact_work({"ok": True, "cutEdits": cut_ed, "type": m.get("agentType") or "agent", "desc": m.get("description") or "",
            "depth": m.get("spawnDepth") or 1, "first": first, "last": last,
            "prompt": prompt, "says": says[-AGENT_SAYS_MAX:], "cutSays": max(0, len(says) - AGENT_SAYS_MAX),
            "steps": steps[-AGENT_STEPS_MAX:], "cutSteps": cut,
            "tools": sorted(tools.items(), key=lambda kv: -kv[1]),
            "size": (os.path.getsize(fp) if os.path.exists(fp) else 0)})
