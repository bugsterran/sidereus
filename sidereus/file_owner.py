"""Who edited which file: Edit/Write/MultiEdit/NotebookEdit targets from session + subagent transcripts (metadata only)."""
import glob
import json
import os
import threading
import time
from sidereus.redact import redact
from sidereus.transcript import CLAUDE_PROJECTS, _line_ts, _tail_incr
from sidereus.agents import sub_globs, sub_sess_dir
from sidereus.claude_roots import projects_dirs
from sidereus.ident import _sid8
from sidereus.gitinfo import _git_root
from sidereus.steps import _edit_target
from sidereus.sessions import sessions_snapshot
from sidereus.git import wt_files

# ⛔Metadata only: path, session id, agent type, time. Edit contents (old/new strings) are never kept.
# ⚠Bash-made edits (sed -i, >, heredoc, python open(...,'w')) are invisible here: guessing targets from command
#   text (steps._wrote_files) is too loose to blame a session for a conflict, so only file-edit tool calls count.
FO_KEEP_S = 86400           # ownership kept 24 h
FO_CONFLICT_S = 1800        # two live sessions editing the same uncommitted file within 30 min = conflict risk
FO_TTL = 10                 # rescan transcripts at most every 10 s (state() polls every few seconds)
FO_FIRST_BYTES = 1_000_000  # first read of a transcript takes its last 1 MB only (then incremental); older edits are missed
FO_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
FO_MAIN = "main"            # aid of the session's own (orchestrator) transcript
FO_LAB_MAX = 24             # agent label cap in the attention row
# ★2026-09-24 (coordinator): ownership unit = (parent sid, aid) — sibling subagents of one orchestrator editing the same
#   file concurrently was today's real case; counting per parent sid hid it. A unit is live only while its session row is
#   live and (for a subagent) it is still in the row's `sub` list (bgtasks done rule: notice / end_turn + quiet / boot).
_FO = {"at": 0.0, "off": {}, "per": {}, "who": {}}   # off: fp->(start,end) · per: fp->{abs path: ts} · who: fp->_who()
_FO_LOCK = threading.Lock()      # guards _FO contents
_FO_SCAN = threading.Lock()      # one scanner at a time; others read the previous index
_FO_N = {}                       # fp -> {abs path: [edit ts, ...]} pruned to FO_KEEP_S (read with per; reset together)
FO_N_MAX = 500                   # timestamps kept per (transcript, path): a runaway loop must not grow memory unbounded
_FO_GIT = {}                     # repo root -> (at, set of abs paths uncommitted)
FO_GIT_MAX = 512
# index() memo: one /api/state poll calls index() 4x (conflicts + review._owned per item); rebuild only when a scan
# committed (gen), the stores were swapped, or the advancing cut would drop an entry (nxt) — same output as a rebuild.
_FO_IDX = {"gen": 0, "key": None, "now": 0.0, "nxt": 0.0, "out": {}}


def _edits(lines):
    """[(abs path, ts)] of file-edit tool_use calls in transcript lines."""
    out = []
    for ln in lines:
        if '"tool_use"' not in ln or ('"file_path"' not in ln and '"notebook_path"' not in ln):
            continue
        try:
            e = json.loads(ln)
        except Exception:
            continue
        c = (e.get("message") or {}).get("content") if isinstance(e, dict) else None
        if not isinstance(c, list):
            continue
        ts = _line_ts(e, 0)
        for it in c:
            if not isinstance(it, dict) or it.get("type") != "tool_use" or it.get("name") not in FO_TOOLS:
                continue
            inp = it.get("input") or {}
            p = inp.get("file_path") or inp.get("notebook_path") or ""
            if isinstance(p, str) and p.startswith("/") and ts:
                out.append((os.path.normpath(p), ts))
    return out


def _who(fp, sub, lines):
    """(parent sid, aid, agent type, description, cwd) of a transcript. aid = subagent id (file stem) or FO_MAIN."""
    cwd = ""
    for ln in lines:
        if '"cwd"' in ln:
            try:
                cwd = json.loads(ln).get("cwd") or ""
            except Exception:
                cwd = ""
            if cwd:
                break
    if not sub:
        return os.path.basename(fp)[:-6], FO_MAIN, "", "", cwd
    agent, desc = "agent", ""
    try:
        with open(fp[:-6] + ".meta.json", encoding="utf-8") as f:
            m = json.load(f)
        agent, desc = m.get("agentType") or "agent", redact(m.get("description") or "")   # reaches the git rail chip
    except (OSError, ValueError, AttributeError):
        pass                    # missing/corrupt sidecar: generic "agent" label
    aid = os.path.basename(fp)[:-6]
    aid = aid[6:] if aid.startswith("agent-") else aid
    return os.path.basename(sub_sess_dir(fp)), aid, agent, desc, cwd


def _scan(now=None):
    """Incremental pass over transcripts written in the last 24 h (per-file byte offsets)."""
    now = time.time() if now is None else now
    if now - _FO["at"] < FO_TTL or not _FO_SCAN.acquire(blocking=False):
        return
    try:
        cut = now - FO_KEEP_S
        seen, upd, drop = set(), {}, []
        pats = []
        for root in projects_dirs(CLAUDE_PROJECTS):   # ⚠extra account roots add a glob + stat pass each
            pats += [(os.path.join(root, "*", "*.jsonl"), False)] + [(p, True) for p in sub_globs(root)]
        for pat, sub in pats:
            for fp in glob.glob(pat):
                try:
                    if os.path.getmtime(fp) < cut:
                        continue
                except OSError:
                    continue
                seen.add(fp)
                with _FO_LOCK:
                    prev, per0, who0 = _FO["off"].get(fp), _FO["per"].get(fp), _FO["who"].get(fp)
                lines, s, e, reset = _tail_incr(fp, FO_FIRST_BYTES, prev)
                if s is None:
                    drop.append(fp)
                    continue
                per = {} if reset or per0 is None else dict(per0)
                cnt = {} if reset or per0 is None else {p: list(v) for p, v in (_FO_N.get(fp) or {}).items()
                                                        if isinstance(v, list)}
                for p, ts in _edits(lines):
                    if ts >= cut:
                        cnt.setdefault(p, []).append(ts)
                    if ts >= cut and ts > per.get(p, 0):
                        per[p] = ts
                who = who0 if who0 and who0[4] else _who(fp, sub, lines)
                per = {p: t for p, t in per.items() if t >= cut}
                # Per-edit timestamps, not a running total: a total never ages out, so a file touched daily read
                # as the multi-day sum. index() recounts against its own cut.
                upd[fp] = ((s, e), per, who, {p: [t for t in v if t >= cut][-FO_N_MAX:]
                                              for p, v in cnt.items() if p in per})
        with _FO_LOCK:
            for fp, (off, per, who, cnt) in upd.items():
                _FO["off"][fp], _FO["per"][fp], _FO["who"][fp] = off, per, who
                _FO_N[fp] = cnt
            for fp in [f for f in _FO["off"] if f not in seen] + drop:
                for k in ("off", "per", "who"):
                    _FO[k].pop(fp, None)
                _FO_N.pop(fp, None)
            _FO["at"] = now
            _FO_IDX["gen"] += 1
    finally:
        _FO_SCAN.release()


def index(now=None):
    """{abs path: {(parent sid, aid): {"ts": last edit, "n": edit calls, "agent", "desc", "cwd"}}} for edits in the last 24 h.
    `n` counts edit calls within the same FO_KEEP_S window as `ts`.
    ⚠It can undercount: the first read of a transcript sees only its last FO_FIRST_BYTES.
    ⚠The result is shared between callers (memo) — read it, never mutate it."""
    now = time.time() if now is None else now
    _scan(now)
    cut, out, nxt = now - FO_KEEP_S, {}, float("inf")
    with _FO_LOCK:
        key = (_FO_IDX["gen"], _FO["at"], id(_FO["per"]), id(_FO["who"]), id(_FO_N))
        m = _FO_IDX
        if m["key"] == key and m["now"] <= now and cut <= m["nxt"]:
            return m["out"]
        for fp, per in _FO["per"].items():
            sid, aid, agent, desc, cwd = _FO["who"].get(fp) or ("", "", "", "", "")
            if not sid:
                continue
            cnt = _FO_N.get(fp) or {}
            for p, ts in per.items():
                if ts < cut:
                    continue
                o = out.setdefault(p, {}).setdefault((sid, aid), {"ts": 0, "n": 0, "agent": agent, "desc": desc, "cwd": cwd})
                o["ts"] = max(o["ts"], ts)
                nxt = min(nxt, ts)
                v = cnt.get(p)
                # A plain int is accepted as an already-windowed count (tests seed _FO_N that way).
                if isinstance(v, int):
                    k = v
                else:
                    kept = [t for t in v or () if t >= cut]
                    k = len(kept)
                    nxt = min([nxt] + kept)
                o["n"] += k or 1
        m.update(key=key, now=now, nxt=nxt, out=out)
    return out


def _by_sid(units):
    """Units of one file folded per parent session for display: {sid: {"ts", "agents": set, "cwd"}}."""
    out = {}
    for (sid, _aid), o in units.items():
        s = out.setdefault(sid, {"ts": 0, "agents": set(), "cwd": o["cwd"]})
        s["ts"] = max(s["ts"], o["ts"])
        if o["agent"]:
            s["agents"].add(o["agent"])
        s["cwd"] = s["cwd"] or o["cwd"]
    return out


def _live_units(rows):
    """{(sid, aid)} still running: main of every non-done row, plus each subagent still in that row's `sub`."""
    out = set()
    for r in rows or ():
        if not isinstance(r, dict) or not r.get("sid") or r.get("state") == "done":
            continue
        out.add((r["sid"], FO_MAIN))
        for s in r.get("sub") or ():
            if isinstance(s, dict) and s.get("aid"):
                out.add((r["sid"], s["aid"]))
    return out


def _hot(units, live, now):
    """Live (sid, aid) units that edited within FO_CONFLICT_S, sorted."""
    return sorted(u for u, o in units.items() if u in live and now - o["ts"] <= FO_CONFLICT_S)


def unit_label(u, o):
    """Short metadata label of a unit: subagent type, capped; the orchestrator is «main».
    ⚠Never the description: it is task text and this label reaches MCP callers via the attention `why`."""
    if u[1] == FO_MAIN:
        return "메인"
    lab = (o.get("agent") or "agent").strip()
    return lab if len(lab) <= FO_LAB_MAX else lab[:FO_LAB_MAX - 1] + "…"


def _dirty(root, now):
    """Abs paths of tracked uncommitted files in a repo (wt_files, cached FO_TTL); None if git refused."""
    hit = _FO_GIT.get(root)
    if hit and now - hit[0] < FO_TTL:
        return hit[1]
    code, out = wt_files(root)
    # ⚠wt_files lists untracked ("??") too; conflicts stay tracked-only to match git_rail._status_tracked
    val = {os.path.normpath(os.path.join(root, f["path"])) for f in out.get("files") or []
           if f.get("st") != "??"} if code == 200 else None
    if len(_FO_GIT) >= FO_GIT_MAX:          # API routes add arbitrary roots — drop the oldest half
        for k in list(_FO_GIT)[:FO_GIT_MAX // 2]:
            _FO_GIT.pop(k, None)
    _FO_GIT[root] = (now, val)
    return val


def conflicts(rows, now=None):
    """[{units, sids, labs, files, since, last, by (latest editor sid)}] — uncommitted files edited within FO_CONFLICT_S
    by >= 2 distinct live (sid, aid) units, grouped per unit set (one entry per set, not per file)."""
    now = time.time() if now is None else now
    live = _live_units(rows)
    if len(live) < 2:
        return []
    grp = {}
    for p, own in index(now).items():
        hs = _hot(own, live, now)
        if len(hs) < 2:
            continue
        t = _edit_target(p)
        d = _dirty(t["cwd"], now) if t else None
        if not d or p not in d:
            continue
        g = grp.setdefault(tuple(hs), {"units": list(hs), "sids": sorted({u[0] for u in hs}),
                                       "labs": [unit_label(u, own[u]) for u in hs],
                                       "files": [], "since": now, "last": 0, "by": ""})
        g["files"].append(p)
        g["since"] = min(g["since"], min(own[u]["ts"] for u in hs))
        t1, u1 = max((own[u]["ts"], u) for u in hs)
        if t1 > g["last"]:
            g["last"], g["by"] = t1, u1[0]
    return sorted(grp.values(), key=lambda g: -g["last"])


def wt_owners(cwd, rows=None, now=None):
    """(code, {ok, cwd, owners: {rel path: [{sid8, proj, agent, ago, live}]}, warn: [rel path]}) for one worktree's
    uncommitted files. Git status comes from wt_files() (same call as /api/git/wtfiles)."""
    code, out = wt_files(cwd)
    if code != 200:
        return code, out
    now = time.time() if now is None else now
    rows = (sessions_snapshot(60) or []) if rows is None else rows
    proj = {r.get("sid"): r.get("project") or "" for r in rows if isinstance(r, dict) and r.get("sid")}
    live = {r.get("sid") for r in rows if isinstance(r, dict) and r.get("sid") and r.get("state") != "done"}
    lu = _live_units(rows)
    root, idx, own_out, warn = _git_root(cwd) or cwd, index(now), {}, []
    for f in out.get("files") or []:
        units = idx.get(os.path.normpath(os.path.join(root, f["path"])))
        if not units:
            continue
        own_out[f["path"]] = [{"sid8": _sid8(s), "proj": proj.get(s) or os.path.basename(o["cwd"] or ""),
                               "agent": ",".join(sorted(o["agents"])), "ago": int(now - o["ts"]), "live": s in live}
                              for s, o in sorted(_by_sid(units).items(), key=lambda kv: -kv[1]["ts"])]
        if len(_hot(units, lu, now)) >= 2:
            warn.append(f["path"])
    return 200, {"ok": True, "cwd": cwd, "owners": own_out, "warn": warn, "conflictMin": FO_CONFLICT_S // 60}
