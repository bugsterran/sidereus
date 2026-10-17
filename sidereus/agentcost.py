"""Agent cost table."""
import json
import os
import threading
import time
from sidereus.agents import slash
from sidereus.redact import redact
from sidereus.warn import warn_once
from sidereus.usage import _cost4, _uidx, _uidx_lock, _uidx_refresh
from sidereus.ident import _proj_name
from sidereus.history import _born_end, _cwd_from_slug, _cwd_probe, _hist_cwd


# ───── agent cost table ───────────────────────────────────────────────────────
# ★Why (2026-09-21): subagents are a large share of the bill, but **there was no place showing which agent
#   spent how much.** The "running subagents" table only says current request counts,
#   not cumulative cost.
# ★Only two sources — nothing new is collected:
#     (1) `_uidx`'s per-file time×model token buckets (`…/<session>/subagents/agent-*.jsonl` are subagents)
#     (2) the adjacent `agent-*.meta.json` sidecar — `agentType` lives here (measured: present in all 2,326)
#   ⚠The type «name» is not in the logs. meta's `description` is that call's task, not an agent name,
#     so it is not a column. Model is present in only 43/2326, so it is not an axis (guessing missing values is false).
# ⚠The aggregate is **all-time**. Unrelated to the day·week·month buttons of the period aggregate above — hence the
#   "last" column alongside (it exposes old agents lingering near the top).
AGC_TTL = 120          # the screen polls every 2.5s — recompute only at this interval
AGC_TOP = 10
AGT_TOP = 5            # «Costly work today» rows per window
_agc = {"at": 0.0, "rows": [], "sub": 0.0, "subtok": 0, "all": 0.0, "alltok": 0,
        "n": 0, "types": 0, "ms": 0, "top": {}}
_agc_lock = threading.Lock()
_agc_meta = {}         # transcript path -> agentType. ⚠meta.json is written once and never changes
                       #   ⇒ permanent cache (cold 0.46s → warm 0.006s, measured 2026-09-21 · 2,326 files).


def _agc_side(fp):
    """{t: agentType, d: one-line task description, u: toolUseId} from `agent-<id>.meta.json`. t='?' if absent."""
    m = _agc_meta.get(fp)
    if m is not None:
        return m
    m = {"t": "?", "d": "", "u": ""}
    try:
        with open(fp[:-6] + ".meta.json", encoding="utf-8") as f:
            j = json.load(f) or {}
        m = {"t": str(j.get("agentType") or "?")[:60], "d": redact(str(j.get("description") or ""))[:160],
             "u": str(j.get("toolUseId") or "")[:80]}
    except (OSError, ValueError, AttributeError):
        pass               # missing or broken sidecars are grouped as '?' — only that row says unknown
    _agc_meta[fp] = m
    return m


def _agc_type(fp):
    """`agentType` from `agent-<id>.meta.json` next to `agent-<id>.jsonl`. '?' if absent."""
    return _agc_side(fp)["t"]


def _agc_snap(h):
    """Two-level copy of one file's hour buckets; call under `_uidx_lock`.
    ⚠The loops below run outside the lock while `_uidx_scan` adds hour/model keys to the live dicts —
      iterating those raised "dictionary changed size during iteration" and blanked the table for a TTL."""
    if not isinstance(h, dict):
        return {}
    return {k: (dict(mm) if isinstance(mm, dict) else mm) for k, mm in h.items()}


def _agc_top(items, since, n=AGT_TOP):
    """Top-n subagent runs by tokens in hour buckets >= `since`. items = [(fp, h)].
    Returns (rows [(tok, fp)], total tokens of every transcript in the window — the share denominator)."""
    runs, tot = [], 0
    for fp, h in items:
        tk = 0
        for k, mm in h.items():
            try:
                if int(k) < since or not isinstance(mm, dict):
                    continue
            except (TypeError, ValueError):
                continue
            for v in mm.values():
                try:
                    tk += int(v[0]) + int(v[1]) + int(v[2]) + int(v[3])
                except (TypeError, ValueError, IndexError, KeyError):
                    continue
        tot += tk
        if tk > 0 and "/subagents/" in slash(fp):   # ⚠Windows index paths may use `\` or mix both
            runs.append((tk, fp))
    runs.sort(key=lambda x: -x[0])
    return runs[:n], tot


def _day0(days, now=None):
    """Local midnight `days - 1` days before now (days=1 -> today 00:00). ⚠Hour keys are UTC on-the-hour: exact for whole-hour zones."""
    lt = time.localtime(now if now is not None else time.time())
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - (days - 1), 0, 0, 0, 0, 0, -1)))


def _agc_cwd(slug):
    cwd = _hist_cwd.get(slug) or _cwd_from_slug(slug) or _cwd_probe(slug)
    if cwd:
        _hist_cwd[slug] = cwd
    return cwd


def _agc_rows(runs, tot):
    """Decorate (tok, fp) with sidecar metadata only — description, type, project, duration, share. Never message text."""
    out = []
    for tk, fp in runs:
        m = _agc_side(fp)
        sub = os.path.dirname(os.path.dirname(fp))            # …/<slug>/<sid>
        sid, slug = os.path.basename(sub), os.path.basename(os.path.dirname(sub))
        cwd = _agc_cwd(slug)
        try:
            b, e = _born_end(fp)
            dur = max(0, e - b)
        except OSError:
            dur, e = None, 0
        out.append({"tok": tk, "desc": m["d"], "type": m["t"], "proj": _proj_name(cwd) if cwd else slug,
                    "cwd": cwd, "tid": (m["u"] + "|" + sid) if m["u"] else "", "dur": dur, "end": e,
                    "share": round(tk / tot * 100, 1) if tot else 0.0})
    return out


def _agc_fetch():
    """Cumulative cost per type. (calls · tokens · $ · average · last). ⚠Models with unknown pricing are $0."""
    t0 = time.time()
    _uidx_refresh()
    with _uidx_lock:
        # ⚠Do not coerce `mt` to float here — one bad row would blank **the whole table**.
        #   The loop below guards per row (measured 2026-09-21: planting a string mt in the index raised ValueError,
        #   killed the whole aggregate, and froze the screen on the old value).
        items = [(fp, _agc_snap(e.get("h")), e.get("mt") or 0) for fp, e in _uidx["files"].items()]
    agg, all_c, all_t = {}, 0.0, 0
    for fp, h, mt in items:
        c, tk = 0.0, 0
        for mm in h.values():
            if not isinstance(mm, dict):
                continue                    # skip only the rows where the index is broken
            for mdl, v in mm.items():
                try:
                    c += _cost4(mdl, v)
                    tk += int(v[0]) + int(v[1]) + int(v[2]) + int(v[3])
                except (TypeError, ValueError, IndexError, KeyError):
                    continue
        all_c += c
        all_t += tk
        if "/subagents/" not in slash(fp):
            continue
        a = agg.setdefault(_agc_type(fp), [0, 0, 0.0, 0.0])
        a[0] += 1
        a[1] += tk
        a[2] += c
        try:
            if float(mt) > a[3]:
                a[3] = float(mt)
        except (TypeError, ValueError):
            pass                            # only the last time is unknown — keep that row's cost
    live = {fp for fp, _h, _mt in items}    # ⚠do not re-read `_uidx["files"]` outside the lock
    for fp in [k for k in _agc_meta if k not in live]:
        _agc_meta.pop(fp, None)             # drop deleted transcripts from the cache too
    rows = [{"type": k, "n": v[0], "tok": v[1], "cost": round(v[2], 2),
             "avg": round(v[2] / max(1, v[0]), 2), "last": int(v[3])}
            for k, v in agg.items()]
    rows.sort(key=lambda x: -x["cost"])
    hs = [(fp, h) for fp, h, _mt in items]
    top = {}
    for nd in (1, 7):
        try:
            top[str(nd)] = _agc_rows(*_agc_top(hs, _day0(nd)))
        except Exception:
            top[str(nd)] = []               # a broken window must not blank the cost table above
    sub_c = sum(v[2] for v in agg.values())
    sub_t = sum(v[1] for v in agg.values())
    with _agc_lock:
        _agc.update({"at": time.time(), "rows": rows[:AGC_TOP],
                     "sub": round(sub_c, 2), "subtok": sub_t,
                     "all": round(all_c, 2), "alltok": all_t,
                     "n": sum(v[0] for v in agg.values()), "types": len(agg), "top": top,
                     "ms": int((time.time() - t0) * 1000)})


def agentcost():
    """Lookup with a TTL cache. The polling path (`wkuse`) calls only this."""
    with _agc_lock:
        fresh = _agc["at"] and time.time() - _agc["at"] < AGC_TTL
        if fresh:
            return dict(_agc)
    try:
        _agc_fetch()
    except Exception as e:
        warn_once("agcost", "Could not build the agent cost table ({err}) — the table is empty",
                  vars={"err": type(e).__name__})
    with _agc_lock:
        return dict(_agc)
