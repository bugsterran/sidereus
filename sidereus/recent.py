"""Recently ended sessions for «Continue a recent session» (GET /api/sessions/recent?days=7)."""
import json
import os
import threading
import time
from sidereus import claude_roots
from sidereus.agents import slash
from sidereus.memo import BoundedMemo
from sidereus.redact import redact
from sidereus.transcript import _model_label
from sidereus.ident import _cwd_from_slug, _proj_name
from sidereus.usage_index import _uidx, _uidx_lock, _uidx_refresh
from sidereus.live import _ctx_window, sid_alive
from sidereus.gitinfo import _wt_of
from sidereus.sessions import sessions_rows
from sidereus.work import _SID_SAFE


# ★2026-09-27: terminal users resume old sessions with `claude --resume`; the 12 h session list drops them.
# ⚠Metadata only (AGENTS.md rule 1): sid, cwd, branch, model, times, ctx, tokens, last Agent `description`
#   — never a title, prompt, reply or any other tool input.
#   The list comes from the usage index (no scan); only the top `RECENT_CAP` files get a bounded tail probe that
#   reads top-level keys and the last `usage` block.
RECENT_TTL_S = 30
RECENT_CAP = 50
RECENT_MAX_DAYS = 30
RECENT_TAIL = 262_144
_recent_lock = threading.Lock()
_recent_cache = {}                 # days -> (measured at, result)
_probe_memo = BoundedMemo(256)     # path -> ((mtime, size), meta); ended files do not change


TASK_MAX = 80


def _agent_desc(content):
    """Last Agent/Task tool `description` in one assistant message — the one-line task label rule 1 allows; nothing else."""
    if not isinstance(content, list):
        return ""
    for c in reversed(content):
        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"):
            s = (c.get("input") or {}).get("description") if isinstance(c.get("input"), dict) else None
            if isinstance(s, str) and s.strip():
                return redact(" ".join(s.split()))[:TASK_MAX]   # ⚠redact before the cut (a cut `u:pw@` escapes the mask)
    return ""


def _probe(fp, mt, sz):
    """{cwd, branch, sid, model, ctx} from the transcript tail. ⚠Message content is never kept."""
    key = (mt, sz)
    hit = _probe_memo.get(fp)
    if hit and hit[0] == key:
        return hit[1]
    out = {"cwd": "", "branch": "", "sid": "", "model": "", "ctx": 0, "agentDesc": ""}
    try:
        with open(fp, "rb") as f:
            if sz > RECENT_TAIL:
                f.seek(sz - RECENT_TAIL)
                f.readline()
            raw = f.read()
    except OSError:
        raw = b""
    for line in reversed(raw.splitlines()):
        if not line.startswith(b"{"):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        out["cwd"] = out["cwd"] or d.get("cwd") or ""
        b = d.get("gitBranch") or ""
        out["branch"] = out["branch"] or ("" if b == "HEAD" else b)
        out["sid"] = out["sid"] or d.get("sessionId") or ""
        if not out["ctx"] and d.get("type") == "assistant":
            m = d.get("message") or {}
            u = m.get("usage") or {}
            if u:
                out["ctx"] = int(u.get("cache_read_input_tokens") or 0) + \
                    int(u.get("cache_creation_input_tokens") or 0) + int(u.get("input_tokens") or 0)
                out["model"] = m.get("model") or ""
        if not out["agentDesc"] and d.get("type") == "assistant":
            out["agentDesc"] = _agent_desc((d.get("message") or {}).get("content"))
        if out["cwd"] and out["sid"] and out["ctx"] and out["branch"] and out["agentDesc"]:
            break
    _probe_memo.put(fp, (key, out))
    return out


def _acct(sid, fp):
    """acct·acctDir for a non-primary account only (rule 1: label + dir); absent for the primary."""
    lab, d = claude_roots.acct_of(sid, fp)
    return {"acct": lab, "acctDir": d} if lab else {}


def _live_set():
    """Sids that are live now: confirmed by id, or a non-`done` row of the last session poll."""
    snap = sessions_rows(max_age=120)   # ⚠request path: snapshot (short wait on a kicked refresh), never a cold sessions()
    return {r.get("sid") for r in snap if r.get("sid") and r.get("state") != "done" and r.get("plat") == "cc"}


def recent_sessions(days=7):
    """Body of `GET /api/sessions/recent?days=N` — ended Claude sessions, newest first, capped."""
    try:
        days = int(days or 7)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, RECENT_MAX_DAYS))
    now = time.time()
    with _recent_lock:
        c = _recent_cache.get(days)
        if c and now - c[0] < RECENT_TTL_S:
            return c[1]
    t0 = time.time()
    _uidx_refresh()
    with _uidx_lock:
        ents = [(fp, e.get("sl") or "", float(e.get("mt") or 0), int(e.get("sz") or 0), e.get("br") or "")
                for fp, e in _uidx["files"].items()]
    live = _live_set()
    cut = now - days * 86400
    cand = []
    for fp, sl, mt, sz, br in ents:
        if "/subagents/" in slash(fp) or not fp.endswith(".jsonl") or mt < cut:   # ⚠Windows: `\` separators
            continue
        sid = os.path.basename(fp)[:-6]
        if not _SID_SAFE.match(sid) or sid in live or sid_alive(sid):
            continue
        cand.append((mt, fp, sid, sl, sz, br))
    cand.sort(key=lambda x: -x[0])
    rows = []
    # Only the keys 41b-sesrecent.js reads (name · branch · model · pct · age · gone · cwd/sid for the command).
    for mt, fp, sid, sl, sz, br in cand[:RECENT_CAP]:
        p = _probe(fp, mt, sz)
        cwd = p["cwd"] or _cwd_from_slug(sl) or ""
        wt = _wt_of(cwd) if cwd and os.path.isdir(cwd) else None
        proj = _proj_name(cwd) or sl.lstrip("-") or "?"
        win = _ctx_window(p["model"], p["ctx"])[0] if p["ctx"] else 0
        rows.append({
            "sid": sid, "cwd": cwd,
            # same name as the board card (88b brBdName): wt.main == "" (main checkout) -> wt.name; linked worktree -> project
            "name": wt["name"] if (wt and not wt.get("main") and wt.get("name")) else proj,
            "branch": p["branch"] or br, "model": _model_label(p["model"]) if p["model"] else "",
            "endedAt": int(mt), "pct": round(p["ctx"] * 100 / win) if win else None,
            "agentDesc": p.get("agentDesc") or "",   # last Agent description (rule 1 one-line label) — tells same-repo rows apart
            "gone": not (cwd and os.path.isdir(cwd)),
            **_acct(sid, fp)})
    out = {"ok": True, "days": days, "at": time.time(), "n": len(rows), "total": len(cand), "cap": RECENT_CAP,
           "rows": rows, "ms": int((time.time() - t0) * 1000)}
    with _recent_lock:
        _recent_cache[days] = (time.time(), out)
    return out
