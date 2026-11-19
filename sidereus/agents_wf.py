"""Workflow-tool runs and Agent-team nodes of a session (metadata only; split out of agents.py)."""
import glob
import json
import os
import re
import time
from sidereus import agents   # ⚠call agents.boot_time() through the module so a patch on agents applies
from sidereus import claude_roots
from sidereus.memo import BoundedMemo
from sidereus.redact import redact
from sidereus.wf_meta import phase_titles, script_name
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.agents import _agent_fin, _agent_meta, _stat_sig


# ── Workflow-tool runs ────────────────────────────────────────────────────────
# ★2026-09-26: the Workflow tool keeps its agents one level deeper than plain subagents —
#     <session>/subagents/workflows/wf_<id>/agent-<aid>.jsonl (+ .meta.json without toolUseId)
#     <session>/subagents/workflows/wf_<id>/journal.jsonl   {"type": launched|started|result|failed, agentId, label, phase}
#   Every `subagents/*.jsonl` glob missed them: invisible in the tree/timeline and absent from token totals.
# ⚠journal "result" lines carry the agent's report text — only type/agentId/label/phase are read (AGENTS.md rule 1).
# ⚠The two globs never overlap (`*` does not cross `/`), so adding the second one cannot double count.
WF_LIVE_S = 120        # a run whose journal or agent log moved this recently counts as running (phase gaps are seconds)
WF_KEEP_S = 300        # a finished run stays in the session tree this long, like a just-finished row
WF_HIST_S = 6 * 3600   # finished runs kept for the pipeline-tab Workflow view (`wfh`), same window as pl_runs.PLR_KEEP_S
WF_HIST_N = 10         # newest finished runs per session in `wfh` — bounds the /api/state payload


_WF_JOURNAL = BoundedMemo(400)   # journal path -> ((mtime, size), parsed)
_WF_NAME = BoundedMemo(400)      # run dir -> name, or ("", transcript size, tried at) while unresolved


def _wf_journal(fp):
    """{"order": [aid...], "ag": {aid: {lab, phase, st}}, "phase": latest started phase}; st = run|done|fail."""
    try:
        sig = _stat_sig(fp)
    except OSError:
        return {"order": [], "ag": {}, "phase": ""}
    hit = _WF_JOURNAL.get(fp, stamp=sig)
    if hit is not None:
        return hit
    out = {"order": [], "ag": {}, "phase": ""}
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(e, dict):
                    continue
                typ, aid = e.get("type"), str(e.get("agentId") or "")[:40]
                if not aid:
                    continue                  # launch bookkeeping / a failed launch with no agent
                if typ == "started":
                    if aid not in out["ag"]:
                        out["order"].append(aid)
                    out["ag"][aid] = {"lab": redact(str(e.get("label") or ""))[:60], "phase": str(e.get("phase") or "")[:40],
                                      "st": "run"}
                    out["phase"] = out["ag"][aid]["phase"]
                elif typ in ("result", "failed") and aid in out["ag"]:
                    out["ag"][aid]["st"] = "done" if typ == "result" else "fail"
    except OSError:
        return out                            # vanished mid-read — not cached, the next poll retries
    return _WF_JOURNAL.put(fp, out, stamp=sig)


_WF_SCRIPT = re.compile(rb'\\nScript file: ((?:[^"\\]|\\\\)+?)\.js')   # `\\` pair = a JSON-escaped Windows separator


def _wf_name(sess_dir, run_dir):
    """Workflow name = basename of the script file the launch result names for this run ('' if not found).
    ⚠Only the script basename is taken from the parent transcript — never args or result text."""
    hit = _WF_NAME.get(run_dir)
    if isinstance(hit, str):
        return hit
    tp = sess_dir + ".jsonl"
    try:
        sz = os.path.getsize(tp)
    except OSError:
        return ""
    if hit and (hit[1] >= sz or time.time() - hit[2] < 30):
        return ""
    rid = os.path.basename(run_dir).encode()
    keys = (b"workflows/" + rid, b"workflows\\\\" + rid)   # ⚠Windows: the JSON line holds a backslash escaped as `\\`
    name = ""
    try:
        with open(tp, "rb") as f:
            # ⚠Resume where the last miss stopped (minus one partial line) — never re-read a long transcript per poll.
            if hit and hit[1] > 65536:
                f.seek(hit[1] - 65536)
                f.readline()
            for ln in f:
                m = None
                for key in keys:
                    i = ln.find(key)
                    if i >= 0:
                        m = _WF_SCRIPT.match(ln, i + len(key))
                        break
                if m:
                    name = os.path.basename(m.group(1).replace(b"\\\\", b"/").decode("utf-8", "replace"))
                    # ⚠Saved copies are `<name>-<run_id>.js` (same as wf_meta.script_name) — drop the run-id suffix.
                    sfx = "-" + os.path.basename(run_dir)
                    name = (name[:-len(sfx)] if name.endswith(sfx) and len(name) > len(sfx) else name)[:60]
    except OSError:
        return ""
    _WF_NAME.put(run_dir, name if name else ("", sz, time.time()))
    return name


def _wf_dirs(sess_dir):
    d = os.path.join(sess_dir, "subagents", "workflows")
    try:
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.startswith("wf_"))
    except OSError:
        return []


def _wf_meta(fp):
    """The agent's .meta.json (label/phase fallback before its journal line lands); {} if unreadable."""
    try:
        with open(fp[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return {}
    return m if isinstance(m, dict) else {}


def wf_agent_files(sess_dir):
    """Every workflow agent transcript of a session (for token scans that walk `_agent_meta`)."""
    out = []
    for rd in _wf_dirs(sess_dir):
        out += sorted(glob.glob(os.path.join(rd, "agent-*.jsonl")))
    return out


def wf_runs(sess_dir, now=None, tokf=None, since=0.0):
    """Workflow runs of one session, oldest first. Metadata only: name, phase, counts, times, tokens, labels.
    `tokf(path)` -> tokens of one agent transcript (the caller's index); runs quiet since `since` are skipped.
    Each agent carries a private `_file` — strip it (`wf_public`) before it reaches a payload."""
    now = time.time() if now is None else now
    out = []
    for rd in _wf_dirs(sess_dir):
        jp = os.path.join(rd, "journal.jsonl")
        files = {os.path.basename(p)[len("agent-"):-len(".jsonl")]: p
                 for p in glob.glob(os.path.join(rd, "agent-*.jsonl"))}
        stamps = []
        for p in [jp] + list(files.values()):
            try:
                st = os.stat(p)
                stamps.append((getattr(st, "st_birthtime", st.st_ctime), st.st_mtime))
            except OSError:
                continue
        if not stamps:
            continue
        start, end = min(s[0] for s in stamps), max(s[1] for s in stamps)
        if end < since:
            continue
        j = _wf_journal(jp)
        order = list(j["order"]) + sorted(a for a in files if a not in j["ag"])
        ags, boot = [], agents.boot_time()
        for aid in order:
            fp = files.get(aid, "")
            ja = j["ag"].get(aid) or {}
            a = {"aid": aid, "lab": ja.get("lab") or "", "phase": ja.get("phase") or "", "st": ja.get("st") or "run",
                 "start": int(start), "end": int(start), "tok": 0, "_file": fp}
            if fp:
                try:
                    st = os.stat(fp)
                    a["start"], a["end"] = int(getattr(st, "st_birthtime", st.st_ctime)), int(st.st_mtime)
                except OSError:
                    a["end"] = int(end)
                if not a["lab"] or not a["phase"]:
                    m = _wf_meta(fp)
                    a["lab"] = a["lab"] or redact(str(m.get("description") or ""))[:60]
                    a["phase"] = a["phase"] or str(m.get("workflowPhase") or "")[:40]
                a["tok"] = int(tokf(fp) or 0) if tokf else 0
            if a["st"] == "run" and (now - a["end"] > WF_LIVE_S * 5 or (boot and a["end"] < boot)):
                a["st"] = "cut"               # no result line and a long-quiet log — ended without a report
            ags.append(a)
        done = sum(1 for a in ags if a["st"] == "done")
        live = any(a["st"] == "run" for a in ags) or now - end < WF_LIVE_S
        rid = os.path.basename(rd)
        phases = phase_titles(sess_dir, rid)   # declared order first, then journal phases not declared
        phases += [p for p in dict.fromkeys(ja["phase"] for ja in j["ag"].values() if ja["phase"]) if p not in phases]
        out.append({"id": rid, "name": _wf_name(sess_dir, rd) or script_name(sess_dir, rid), "phase": j["phase"],
                    "phases": phases,
                    "done": done, "fail": sum(1 for a in ags if a["st"] in ("fail", "cut")), "total": len(ags),
                    "start": int(start), "end": int(end), "run": bool(live and not (boot and end < boot)),
                    "tok": sum(a["tok"] for a in ags), "agents": ags})
    return out


def wf_public(runs):
    """Payload copy of `wf_runs` output — drops the private `_file` paths."""
    return [dict(r, agents=[{k: v for k, v in a.items() if not k.startswith("_")} for a in r["agents"]])
            for r in runs]


# ── Agent teams ───────────────────────────────────────────────────────────────
# ★2026-09-26: a team leader session keeps its task list and member inboxes outside the projects dir —
#     ~/.claude/tasks/<leader sid>/<N>.json            {id, subject, description, status, blocks, blockedBy, owner}
#     ~/.claude/teams/<leader sid>/inboxes/<member>.json [{from, text, timestamp, read, msg_id, ...}]
#   Teammates are the leader's subagents; their .meta.json carries `name` (= task owner = inbox file stem).
# ⚠Metadata only: task `description` and inbox `text` are never read into a row — subject, owner, status, counts.
TEAM_ROOT = os.path.dirname(CLAUDE_PROJECTS)   # ~/.claude (same base as the projects dir)
TEAM_KEEP_S = 1800     # a team with nothing open stays visible this long after its last write
_TEAM_ST = ("pending", "in_progress", "completed")


def _team_json(fp):
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def team_info(sess_dir, now=None):
    """Team node for a leader session, or None when it has no team files (or the team went quiet)."""
    now = time.time() if now is None else now
    sid = os.path.basename(sess_dir)
    base = claude_roots.root_of(sess_dir)[1] or TEAM_ROOT   # team files live in the transcript's own Claude root
    td, ib = os.path.join(base, "tasks", sid), os.path.join(base, "teams", sid, "inboxes")
    tfs, ifs = glob.glob(os.path.join(td, "*.json")), glob.glob(os.path.join(ib, "*.json"))
    if not tfs and not ifs:
        return None
    last, counts, cur = 0.0, dict.fromkeys(_TEAM_ST, 0), {}
    for fp in sorted(tfs):
        t = _team_json(fp)
        if not isinstance(t, dict):
            continue
        try:
            last = max(last, os.path.getmtime(fp))
        except OSError:
            continue
        st = t.get("status") if t.get("status") in _TEAM_ST else "pending"
        counts[st] += 1
        own = str(t.get("owner") or "")[:60]
        # current task per owner: in_progress wins over pending; completed tasks are not "current"
        if own and st != "completed" and (st == "in_progress" or own not in cur):
            cur[own] = str(t.get("subject") or "")[:80]
    unread = {}
    for fp in ifs:
        box = _team_json(fp)
        name = os.path.basename(fp)[:-len(".json")][:60]
        unread[name] = sum(1 for m in box if isinstance(m, dict) and not m.get("read")) if isinstance(box, list) else 0
        try:
            last = max(last, os.path.getmtime(fp))
        except OSError:
            continue
    members = {}
    for m in _agent_meta(sess_dir).values():
        name = str(m.get("name") or "")[:60]
        fp = m.get("_file") or ""
        if not name or not fp:
            continue
        try:
            mt = os.path.getmtime(fp)
        except OSError:
            continue
        last = max(last, mt)
        st = "done" if _agent_fin(fp) else ("run" if now - mt < WF_LIVE_S else "idle")
        members[name] = {"name": name, "st": st, "model": str(m.get("model") or "")[:40]}
    for name in (set(unread) | set(cur)) - {"team-lead"}:   # the leader's own inbox is the session, not a member
        members.setdefault(name, {"name": name, "st": "idle", "model": ""})
    # `tsub` (task subject, a one-line label) — not `task`, which the metadata-only arch rule reserves for bodies.
    rows = [dict(v, tsub=cur.get(k, ""), unread=unread.get(k, 0)) for k, v in sorted(members.items())]
    live = counts["pending"] or counts["in_progress"] or any(r["st"] == "run" for r in rows)
    if not live and now - last > TEAM_KEEP_S:
        return None
    return {"members": rows, "tasks": counts, "done": counts["completed"], "total": sum(counts.values()),
            "run": bool(live)}
