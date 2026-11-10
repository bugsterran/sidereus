"""Session and agent work views (GET /api/work) and the allowed-cwd gate."""
import json
import os
import re
import time
from sidereus import claude_roots
from sidereus import ext_presence, plat_pi   # module access: tests patch `plat_pi.root`
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _proj_name, _sid8, _slug
from sidereus.live import _sid_transcript
from sidereus.steps import (AGENT_SAYS_MAX, AGENT_STEPS_MAX, SESS_TAIL, _cap_edit_bodies, _open_or_tail,
    _res_is_code, _work_scan)
from sidereus.agents import _agent_meta, _wf_meta, wf_agent_files
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
    got, reps = {}, {}
    try:
        for r in sessions_rows():   # ⚠request path: poll snapshot, never a cold sessions()
            c = r.get("cwd")
            if not c:
                continue
            # ⚠repos are per session: two sessions in one cwd touch different repos, so union them (order kept)
            #   or the dropped row's repos vanish from pipeline chips and structure warm-up.
            reps.setdefault(c, [])
            reps[c] += [x for x in (r.get("repos") or []) if x not in reps[c]]
            # ⚠a Gemini row never replaces the Claude row of the same cwd (it has no repos — diff/branch allow list would shrink)
            if r.get("plat") in (None, "", "cc") or c not in got:
                got[c] = r
        # copies: the rows belong to the shared poll snapshot
        got = {c: dict(r, repos=reps[c]) for c, r in got.items()}
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
        base = os.path.realpath(p)
        if base == os.path.dirname(base):   # ⚠a root ("/", "D:\") would match everything; rstrip(os.sep) kept "D:"
            continue
        if os.path.normcase(rp).startswith(os.path.normcase(base) + os.sep):   # normcase: Windows ignores case
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

    Shown the same way as subagents: the work log is the one owner-approved exception to "metadata only" (AGENTS.md rule 1).
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
    steps.py assistant text blocks — the approved work-log exception, AGENTS.md rule 1).

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
        # ⚠Workflow agents live under subagents/workflows/wf_*/ and their meta has no toolUseId, so _agent_meta skips them.
        #   Match the aid against scanned file names only; the id never becomes a path.
        if _AID_RE.match(tid or ""):
            _wp = next((p for p in wf_agent_files(_f[:-len(".jsonl")])
                        if os.path.basename(p) == "agent-" + tid + ".jsonl"), None)
            if _wp:
                m = dict(_wf_meta(_wp), _file=_wp, _id=tid)
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


def _pi_file(sid):
    """pi session file of `sid`, re-checked under `plat_pi.root()/sessions` (a symlink out is refused), else ""."""
    try:
        fp = (plat_pi.one(sid) or {}).get("path") or ""
    except Exception:
        return ""
    return fp if plat_pi.path_ok(fp) and os.path.isfile(fp) else ""


def _pi_abs(p, cwd):
    # pi tools take cwd-relative paths; `_edit_target` and the diff tree need absolute ones
    if isinstance(p, str) and p and not os.path.isabs(p) and os.path.isabs(cwd or ""):
        return os.path.normpath(os.path.join(cwd, p))
    return p


def _pi_input(name, a, cwd):
    """pi tool call -> (Claude tool name, Claude-shape input) so `_scan_blocks` applies the same allow-list.
    ⚠Schema of pi's built-ins (core/tools/*.d.ts): bash{command} · read{path} · write{path, content} ·
      edit{path, edits[{oldText, newText}]} (old calls carry top-level oldText/newText). Others keep their arguments."""
    a = a if isinstance(a, dict) else {}
    if name == "bash":
        return "Bash", {"command": a.get("command")}
    if name == "read":
        return "Read", {"file_path": _pi_abs(a.get("path"), cwd)}
    if name == "write":
        return "Write", {"file_path": _pi_abs(a.get("path"), cwd), "content": a.get("content")}
    if name == "edit":
        eds = a.get("edits") if isinstance(a.get("edits"), list) else (
            [{"oldText": a.get("oldText"), "newText": a.get("newText")}] if isinstance(a.get("oldText"), str) else [])
        return "Edit", {"file_path": _pi_abs(a.get("path"), cwd),
                        "edits": [{"old_string": x.get("oldText"), "new_string": x.get("newText")}
                                  for x in eds if isinstance(x, dict)]}
    return name, a


def _pi_text(c):
    # text blocks only: images, thinking and anything else never leave the file
    if isinstance(c, str):
        return c
    return [{"type": "text", "text": b.get("text")} for b in (c if isinstance(c, list) else [])
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)]


def _pi_lines(fp, cwd, names):
    """Tail of a pi session file as Claude-shape transcript lines for `_work_scan`; fills `names` {call id: pi tool name}.
    Only `message` entries of role user/assistant/toolResult; assistant `thinking` is dropped."""
    for ln in _open_or_tail(fp, tail=SESS_TAIL):
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        m = o.get("message") if isinstance(o, dict) and o.get("type") == "message" else None
        if not isinstance(m, dict):
            continue
        ts = o.get("timestamp") if isinstance(o.get("timestamp"), str) else None
        role = m.get("role")
        if role == "user":
            e = {"type": "user", "message": {"role": "user", "content": _pi_text(m.get("content"))}}
        elif role == "assistant":
            bl = []
            for b in m.get("content") if isinstance(m.get("content"), list) else []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and isinstance(b.get("text"), str):
                    bl.append({"type": "text", "text": b["text"]})
                elif b.get("type") == "toolCall" and isinstance(b.get("name"), str) and b["name"]:
                    nm, inp = _pi_input(b["name"], b.get("arguments"), cwd)
                    cid = b.get("id") if isinstance(b.get("id"), str) else ""
                    if cid:
                        names[cid] = b["name"][:64]
                    bl.append({"type": "tool_use", "id": cid or None, "name": nm, "input": inp})
            e = {"type": "assistant", "message": {"role": "assistant", "content": bl}}
        elif role == "toolResult" and isinstance(m.get("toolCallId"), str):
            e = {"type": "user", "message": {"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": m["toolCallId"], "content": _pi_text(m.get("content")),
                "is_error": bool(m.get("isError"))}]}}
        else:
            continue
        if ts:
            e["timestamp"] = ts
        yield json.dumps(e)


def ext_work_log(plat, sid, now=None):
    """External session work panel; for a pi session with a session file, also its steps and replies.
    ★Work-log exception (AGENTS.md rule 1) widened to pi: click-only popup, same allow-list and redaction as
      `session_work`. ⚠Any read/parse failure returns the metadata result unchanged (no file = existing empty state)."""
    out = ext_presence.ext_work_any(plat, sid, now)
    if not out.get("ok") or out.get("plat") != plat_pi.KEY:
        return out
    fp = _pi_file(str(sid or "").strip())
    if not fp:
        return out
    try:
        cwd = out.get("cwd") or ""
        names = {}
        sc, err = _work_scan(_pi_lines(fp, cwd, names), cwd)
        if err:
            return out
        steps, says, results, _prompt, first, last, luser = sc
        for st in steps:
            r = results.get(st.get("id"))
            if r:
                r["code"], r["lang"] = _res_is_code(st.get("tool"), st.get("arg"))   # Claude names decide code
                st["res"] = r
            st["tool"] = names.get(st.get("id") or "", st["tool"])   # then pi's own tool name
            st.pop("id", None)
        cut = max(0, len(steps) - AGENT_STEPS_MAX)
        tools = {}
        for st in steps:
            tools[st["tool"]] = tools.get(st["tool"], 0) + 1
        steps = steps[-AGENT_STEPS_MAX:]
        cut_ed = _cap_edit_bodies(steps)
        log = dict(out, log=True, steps=steps, cutSteps=cut, cutEdits=cut_ed, prompt=luser,
                   says=says[-AGENT_SAYS_MAX:], cutSays=max(0, len(says) - AGENT_SAYS_MAX),
                   first=first or out.get("first") or "", last=last or out.get("last") or "",
                   tools=sorted(tools.items(), key=lambda kv: -kv[1]), size=os.path.getsize(fp), tail=SESS_TAIL)
        return redact_work(log)
    except Exception:
        return out
