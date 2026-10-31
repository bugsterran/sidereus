"""Timeline rows for external CLI sessions (Gemini, Codex, ...): top-level sessions and children of Claude sessions.
Assembled into the Gantt by `sidereus/timeline.py` (`_plat_tl_rows`)."""
from sidereus.ident import _proj_name, _sid8
from sidereus.adapter import adapter_scan
from sidereus.ext import _ext, _ext_lock, ext_runs, PLAT_MODS, EXT_PLAT, ext_side_msgs, ext_side_sess, ext_hook_cwds
from sidereus.timeline_scan import SEG_GAP, SEG_MAX
from sidereus.ext_presence import ext_presence_rows, PRES_NAME


# ── external CLI sessions: Gemini, Codex, ... (metadata only: ids, timestamps, model, token counts) ─────
# ⚠The scan is each platform module's `scan` (shared with history and ext usage) — do not add a second reader here.


def _ext_child(sid, run, lv, pcwd, segs, tk, model, now, key, label):
    """An ext CLI run launched by a Claude session → an agent-kind row under that session's group.
    ★The JS attaches it by `parent` sid first; `cwd` is still the **parent's** as the fallback key."""
    pc = pcwd.get(run.get("parent") or "") or ()
    cwd = (pc[0] if pc else "") or run.get("cwd") or (lv or {}).get("cwd") or "?"
    proj = (pc[1] if pc else "") or _proj_name(cwd) or "?"
    st = (lv or {}).get("state") or ("" if lv else "done")
    start, end = int(segs[0][0]), int(segs[-1][1])
    return {"tid": "ext:" + key + "|" + sid, "type": label, "aid": "", "par": "",
            "desc": (label + " · " + (model or ""))[:60], "last": "",
            "segs": segs, "start": start, "end": end,
            "run": bool(lv) and st in ("tool", "think"), "state": st, "done": not lv or st == "gone",
            "proj": proj, "cwd": cwd, "depth": 1, "plat": key, "model": (model or "")[:40],
            "parent": run.get("parent") or "", "fin": 0 if lv and st != "gone" else 1,
            "tk": sum(n for _t, n in tk), "_tk": tk}


def _plat_rows(m, cut, now, pcwd=None):
    """One timeline row per record file of platform module `m` written since `cut` — same keys as a session
    row, plus `plat`. Runs launched by a Claude session (`ext.ext_runs`) become child rows under it (`_ext_child`)."""
    return _ext_tl(cut, now, pcwd, m.PLAT, m.KEY, m.CHILD_LABEL, m.NAME, lambda since: adapter_scan(m, since))


def _plat_tl_rows(cut, now, pcwd=None):
    """Timeline rows for every `ext.PLAT_MODS` platform, in registry order."""
    out = []
    for m in PLAT_MODS.values():
        out += _plat_rows(m, cut, now, pcwd)
    with _ext_lock:
        hook_only = {p for p, _sid in _ext if p not in PLAT_MODS}
    hook_only |= {p for p, _sid in ext_hook_cwds() if p not in PLAT_MODS and p in EXT_PLAT}
    for p in sorted(hook_only):
        out += _ext_tl(cut, now, pcwd, p, EXT_PLAT[p], "CLI", p.title(), _hook_scan(p))
    # ⚠Hook-less Cursor/Copilot sessions otherwise reached only the session list; hook rows win (skipped there + `_tl_dedup`).
    out += [_pres_row(r, cut, now) for r in ext_presence_rows(now)]
    return out


def _pres_row(r, cut, now):
    """Main-session row from an `ext_presence` row (metadata only): one bar from start to last activity, idle if older."""
    key, sid, cwd = r["plat"], r["sid"], r.get("cwd") or ""
    last = int(now - int(r.get("ageSec") or 0))
    start = last - int((r.get("runmin") or {}).get("run") or 0) * 60
    segs = [[int(max(start, cut)), last]] if last >= cut else []
    t0 = segs[0][0] if segs else int(cut)
    proj = _proj_name(cwd) or "?"
    ms = ext_side_sess(r.get("kind") or "", sid)          # Copilot usage records ({} for Cursor)
    tk = sorted((v[4], v[0] + v[1] + v[2] + v[3]) for v in ms.values() if v[4] >= cut)
    lm = max(ms.values(), key=lambda v: v[4], default=None)
    return {"tid": "ext:" + key + "|" + sid, "sid": sid, "type": proj,
            "desc": PRES_NAME.get(r.get("kind") or "", "CLI") + " — " + _sid8(sid),
            "segs": segs, "comp": [], "seen": t0, "start": t0, "end": max(t0, last),
            "run": False, "state": "", "idle": int(max(0, now - last)), "blocked": "",
            "proj": proj, "cwd": cwd or "?", "depth": 0, "kind": "sess",
            "plat": key, "model": (lm[5] if lm else "")[:40], "tk": sum(n for _t, n in tk), "_tk": tk, "last": ""}


def _hook_scan(plat):
    """Scan for a platform without a record-file adapter (Cursor): activity = hook event times kept in `_ext`.
    ⚠Without this such sessions reached the session list but never the timeline."""
    def scan(cut):
        with _ext_lock:
            items = [(sid, v.get("cwd") or "", list(v.get("ev") or [])) for (p, sid), v in _ext.items() if p == plat]
        msgs = {sid: ms for (p, sid), ms in ext_side_msgs(cut).items() if p == plat}
        out = [{"sid": sid, "cwd": cwd, "msgs": msgs.get(sid) or {},
                "acts": {i: float(e.get("t") or 0) for i, e in enumerate(ev)
                         if isinstance(e, dict) and e.get("e") not in ("SessionStart", "SessionEnd")}}
               for sid, cwd, ev in items]
        # Ended sessions (gone from `_ext`) keep their row from the stored generations.
        live = {sid for sid, _c, _e in items}
        cwds = ext_hook_cwds()
        for sid, ms in msgs.items():
            # ⚠Only sessions with hook generations: a record-only Copilot sid has no cwd here (its row is `_pres_row`).
            if sid not in live and (plat, sid) in cwds:
                out.append({"sid": sid, "cwd": cwds.get((plat, sid)) or "", "msgs": ms,
                            "acts": {g: v[4] for g, v in ms.items()}})
        return out
    return scan


def _ext_tl(cut, now, pcwd, plat, key, label, name, scan):
    pcwd = pcwd or {}
    with _ext_lock:
        live = {sid: dict(v) for (p, sid), v in _ext.items() if p == plat}
    runs = {r["sid"]: r for r in ext_runs() if r.get("plat") == plat}
    for sid, v in live.items():
        if v.get("parent") and sid not in runs:
            runs[sid] = {"parent": v["parent"], "cwd": v.get("cwd") or "",
                         "start": v.get("firstSeen") or 0, "end": v.get("lastSeen") or 0}
    out, seen = [], set()
    for c in scan(cut):
        if c.get("parent") and c["sid"] not in runs:     # CLI subagent chat -> child of its CLI parent session
            runs[c["sid"]] = {"parent": c["parent"], "cwd": c.get("cwd") or "", "start": 0, "sub": True}
        if c["sid"] in runs:
            seen.add(c["sid"])
            ts = sorted(t for t in (c.get("acts") or {}).values() if t >= cut)
            if not ts:
                continue
            run = runs[c["sid"]]
            msgs = c.get("msgs") or {}
            last = max(msgs.values(), key=lambda v: v[4], default=None)
            tk = sorted((v[4], v[0] + v[1] + v[2] + v[3]) for v in msgs.values() if v[4] >= cut)
            s0, s1 = min(ts[0], float(run.get("start") or ts[0])), ts[-1]
            if s0 < cut:
                s0 = ts[0]
            lv = live.get(c["sid"])
            model = (lv or {}).get("model") or run.get("model") or (last[5] if last else "")
            out.append(_ext_child(c["sid"], run, lv, pcwd, [[int(s0), int(s1)]], tk, model, now, key,
                                  "subagent" if run.get("sub") else label))
            if run.get("sub"):                # `aid` + `desc` = the Claude-kid label path (`tlAgLab`): model, «subagent» chip
                out[-1].update(aid=c["sid"], desc=(model or "")[:60])
            continue
        seen.add(c["sid"])
        _ext_sess(c, cut, now, live, out, key, name)
    # Connected but quiet past the window: the scan's mtime cut skipped its file, yet it stays on the timeline.
    for sid, v in live.items():
        if sid not in seen and sid not in runs and not v.get("parent"):
            _ext_sess({"sid": sid, "cwd": v.get("cwd") or ""}, cut, now, live, out, key, name)
    for sid, run in runs.items():            # no chat file in the window — draw from the stored metadata
        if sid in seen or run.get("sub"):
            continue
        try:
            a, b = float(run.get("start") or 0), float(run.get("end") or 0)
        except (TypeError, ValueError):
            continue
        if not b or b < cut:
            continue
        a = max(a or b, cut)
        tok = int(run.get("tok") or 0)
        out.append(_ext_child(sid, run, live.get(sid), pcwd, [[int(a), int(b)]],
                             [(b, tok)] if tok else [], run.get("model") or "", now, key, label))
    return out


def _ext_sess(c, cut, now, live, out, key, name):
    """Top-level row for an ext CLI session without a Claude parent (interactive use)."""
    ts = sorted(t for t in (c.get("acts") or {}).values() if t >= cut)
    sid = c["sid"]
    lv = live.get(sid) or {}
    if not ts and (not lv or lv.get("state") == "gone"):
        return
    cwd = lv.get("cwd") or c.get("cwd") or c.get("project") or "?"
    proj = _proj_name(cwd) or c.get("project") or "?"
    msgs = c.get("msgs") or {}
    segs = []
    if ts:
        a = b = ts[0]
        for t in ts[1:]:
            if t - b > SEG_GAP:              # same gap rule as Claude segments
                segs.append((a, b)); a = t
            b = t
        segs.append((a, b))
        segs = segs[-SEG_MAX:]
    t0 = int(segs[0][0]) if segs else int(cut)           # idle live row: empty segs, span = window start
    t1 = int(ts[-1]) if ts else int(float(lv.get("lastSeen") or cut))
    tk = sorted((v[4], v[0] + v[1] + v[2] + v[3]) for v in msgs.values() if v[4] >= cut)
    last = max(msgs.values(), key=lambda v: v[4], default=None)
    st = lv.get("state") or ""
    out.append({"tid": "ext:" + key + "|" + sid, "sid": sid, "type": proj, "desc": name + " — " + _sid8(sid),
                "segs": [[int(x), int(y)] for x, y in segs], "comp": [],
                "seen": t0, "start": t0, "end": max(t0, t1),
                "run": st in ("tool", "think"), "state": st,
                "idle": int(max(0, now - t1)), "blocked": "",
                "proj": proj, "cwd": cwd, "depth": 0, "kind": "sess",
                "plat": key, "model": (lv.get("model") or (last[5] if last else ""))[:40],
                "tk": sum(n for _t, n in tk), "_tk": tk, "last": ""})
