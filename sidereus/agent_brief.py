"""Read-only briefs for a Claude session asking Sidereus (MCP server `mcp/sidereus_mcp.py`, routes `/api/agent/*`).

A session can ASK Sidereus instead of the user watching the screen.
  Sidereus answers when asked; it never controls sessions — every function here only reads existing caches.
⛔Metadata only: ids, project/branch names, states, tool names, counts, times. Never task/reply text, tool inputs,
  subagent `now` lines or card bodies. Every output dict is built field by field here (no row passthrough).
"""
import os
import re
import time
from sidereus.ident import _sid8
from sidereus.gitinfo import _wt_of
from sidereus.sessions import sessions_rows
from sidereus.cards import cards
from sidereus.quota import quota
from sidereus.burn import quota_burn, quota_burn_acct
from sidereus.quota_roots import quota_accounts, row_usable
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.saver import SAVER_CAP, SAVER_VIEW_STALE, _saver_state, _saver_view, _saver_views
from sidereus.steps import _edit_target
from sidereus.attention import attention
from sidereus.perm_marks import perm_rows
from sidereus import file_owner as _fo

AB_SNAP_S = 60       # reuse the last state() poll's rows if this fresh; else short wait on a background refresh
AB_PEERS_MAX = 20
AB_FILE_MAX = 10
_exists = os.path.exists   # tests replace this
_now = time.time            # tests replace this
PACE_EN = {2: "way too fast", 1: "fast", 0: "on pace", -1: "slow", -2: "way too slow"}


def _rows():
    """Session rows from the poll's snapshot — ⚠MCP/request path, never a cold sessions()."""
    return sessions_rows(max_age=AB_SNAP_S) or []


def _repo_key(wt):
    """Main repo root of a worktree dict (linked worktrees group with their main checkout)."""
    return (wt or {}).get("main") or (wt or {}).get("root") or ""


def _primary_label():
    return next((r.get("label") or "" for r in claude_accounts() if r.get("primary")), "")


def brief_quota(now=None, acct=None):
    """5h / 7d usage %, measured used tokens, time to empty, pace verdict and one advice line.
    `acct` = a non-primary account label (None/primary label = the primary account).
    ⚠Advice is copied from the saver hook's own verdict (`.saver-view.json` lv / stage) — no new rule here."""
    now = time.time() if now is None else now
    prim = _primary_label()
    extra = bool(acct) and acct != prim
    if extra:
        # ⚠Never fall back to the primary's numbers: a missing row is "not measured", not someone else's quota.
        q = next((r for r in quota_accounts() if r.get("label") == acct and row_usable(r)), None) or {}
    else:
        q = quota() or {}
    q5, q7 = q.get("five_hour") or {}, q.get("seven_day") or {}
    out = {"ok": bool(q5), "acct": acct if extra else prim, "age": q.get("age"),
           "fiveHour": {"pct": q5.get("pct"), "resetsAt": q5.get("resets_at"), "leftSec": q5.get("leftSec")},
           "sevenDay": {"pct": q7.get("pct"), "resetsAt": q7.get("resets_at"), "leftSec": q7.get("leftSec")}}
    if extra and not q5:
        out["err"] = "not measured"
    try:
        b = (quota_burn_acct(acct) if extra else quota_burn()) or {}
    except Exception:
        b = {}
    # ★2026-10-02 (traps/quota.md «Token headroom»): no token headroom — tokens per 1% spread CV 0.29-0.49, so it misled agents.
    #   Only measured values: local used tokens since the 5h window start, and the projected time to 100%.
    out["used5Tok"] = (b.get("cur") or {}).get("used_local")
    out["emptyAt"] = (b.get("proj") or {}).get("over_at")
    v = (_saver_views().get(acct) if extra else _saver_view()) or {}
    fresh = bool(v) and now - (v.get("at") or 0) <= SAVER_VIEW_STALE
    st = v.get("stage")
    if extra and fresh and isinstance(st, int):
        # The account's own hook verdict; _saver_state is the primary's rule and only a fallback for a missing view.
        on = v.get("mode") != "off" and st in SAVER_CAP
        sv = {"on": on, "stage": st if on else None, "cap": SAVER_CAP.get(st) if on else None, "why": "hook"}
    else:
        sv = _saver_state(q5.get("pct"), q5.get("leftSec")) or {}
    out["saver"] = {"on": bool(sv.get("on")), "stage": sv.get("stage"), "cap": sv.get("cap"), "why": sv.get("why")}
    lv = v.get("lv") if fresh else None
    # ⚠The hook's lvNm is Korean (saver.py LV_NM); MCP output is English, so name comes from lv (page's i18n wording).
    out["pace"] = {"lv": lv, "name": (PACE_EN.get(lv) or v.get("lvNm")) if fresh else None,
                   "earlyMin": v.get("earlyMin") if fresh else None,
                   "goal": v.get("goal") if fresh else None, "mode": v.get("mode") if fresh else None,
                   "rec": v.get("rec") if fresh else None}
    if out["saver"]["on"] and out["saver"]["cap"] is not None:
        adv = "slow down — saver stage %s, max %s concurrent subagents" % (out["saver"]["stage"], out["saver"]["cap"])
    elif isinstance(lv, int) and lv >= 1:
        adv = "slow down — burning faster than the goal"
    elif isinstance(lv, int) and lv <= -1:
        adv = "ok — below the goal pace, room to spare"
    elif lv == 0:
        adv = "ok — on pace"
    else:
        # ⚠lv None (mode off, or snapshot missing/stale) is no verdict, never "on pace"; the projection still counts.
        ea, left = out["emptyAt"], q5.get("leftSec")
        if isinstance(ea, (int, float)) and isinstance(left, (int, float)) and ea < now + left:
            adv = "careful — no pace verdict, but at this pace the 5h window empties before it resets"
        elif fresh:
            adv = "no pace verdict (pace mode %s)" % (v.get("mode") or "unknown")
        elif not v:
            adv = "no pace data yet"    # normal on a fresh install: the optional saver hook has not reported
        else:
            adv = "no pace verdict (pace data is stale)"
    out["advice"] = adv
    return out


def _sub_types(r):
    """Subagent type + short id per running subagent (label before ':' only — never the `now` line)."""
    out = []
    for s in r.get("sub") or ():
        if isinstance(s, dict) and s.get("aid"):
            out.append({"aid8": str(s["aid"])[:8], "type": (str(s.get("lab") or "agent").split(":")[0])[:40],
                        "idle": bool(s.get("idle"))})
    return out


def _peer(r, here_root):
    win, ctx = r.get("win") or 0, r.get("ctx") or 0
    wt = r.get("wt") or {}
    return {"sid8": _sid8(r.get("sid")), "project": r.get("project") or "", "branch": r.get("branch") or "",
            "worktree": wt.get("name") or "", "sameWorktree": bool(here_root) and wt.get("root") == here_root,
            "state": r.get("state") or "", "tool": r.get("tool") or "",
            "ctxPct": int(round(100.0 * ctx / win)) if win and ctx else None,
            "ageSec": r.get("ageSec"), "model": r.get("model") or "", "subagents": _sub_types(r)}


def brief_peers(cwd, rows=None):
    """Live sessions in the same repo as `cwd` (any worktree of it), with their running subagents."""
    cwd = os.path.normpath(cwd) if cwd else ""
    wt = _wt_of(cwd) if cwd else None
    if not wt:
        # Peers are grouped by repo; a folder without .git (e.g. a zip copy) just has none — not an error.
        return {"ok": True, "repo": "", "worktree": "", "peers": [], "n": 0,
                "note": "not a git repo (%s) — peers are grouped by git repo, so none are listed" % (cwd or "no cwd")}
    key, root = _repo_key(wt), wt.get("root") or ""
    rows = _rows() if rows is None else rows
    out = [_peer(r, root) for r in rows
           if isinstance(r, dict) and r.get("state") != "done" and _repo_key(r.get("wt")) == key]
    out.sort(key=lambda p: (not p["sameWorktree"], p["ageSec"] or 0))
    return {"ok": True, "repo": key, "worktree": root, "peers": out[:AB_PEERS_MAX], "n": len(out)}


def brief_file(path, cwd="", rows=None, now=None):
    """Sessions/subagents that edited `path` in the last FO_CONFLICT_S, live flag, and whether it is uncommitted."""
    now = time.time() if now is None else now
    if not path:
        return {"ok": False, "err": "path required"}
    if not os.path.isabs(path):                  # isabs: Windows `C:\...` is absolute too
        if not cwd:
            return {"ok": False, "err": "relative path needs cwd"}
        path = os.path.join(cwd, path)
    path = os.path.normpath(path)
    rows = _rows() if rows is None else rows
    proj = {r.get("sid"): r.get("project") or "" for r in rows if isinstance(r, dict) and r.get("sid")}
    live = _fo._live_units(rows)
    units = _fo.index(now).get(path) or {}
    eds = []
    for u, o in sorted(units.items(), key=lambda kv: -kv[1]["ts"]):
        if now - o["ts"] > _fo.FO_CONFLICT_S:
            continue
        eds.append({"sid8": _sid8(u[0]), "unit": "main" if u[1] == _fo.FO_MAIN else u[1][:8],
                    "agent": o.get("agent") or ("main" if u[1] == _fo.FO_MAIN else "agent"),
                    "project": proj.get(u[0]) or os.path.basename(o.get("cwd") or ""),
                    "agoSec": int(now - o["ts"]), "live": u in live})
    t = _edit_target(path)
    dirty = None
    if t:
        d = _fo._dirty(t["cwd"], now)
        dirty = None if d is None else path in d
    # exists lets the MCP say "no such file" instead of "clean" (git status is silent for unknown paths).
    return {"ok": True, "path": path, "exists": _exists(path), "windowMin": _fo.FO_CONFLICT_S // 60,
            "uncommitted": dirty,
            "editors": eds[:AB_FILE_MAX], "n": len(eds), "liveN": sum(1 for e in eds if e["live"]),
            # liveN counts (sid, aid) units, so a session + its own subagent is 2; the rail's conflict needs 2+
            # distinct sessions (git_rail), so callers warn on liveSids, not liveN.
            "liveSids": sorted({e["sid8"] for e in eds if e["live"]})}


def _num(w, pat, g=1):
    m = re.search(pat, w)
    return m.group(g) if m else ""


def _why_en(s):
    """English label for one attention signal. ⚠attention.py builds `why` in Korean for the page; this mirrors the
    page's English rebuild (web/js/17-attention.js attnWhy) — per k, pulling only numbers/tool names out of it."""
    k, w = s.get("k") or "", s.get("why") or ""
    n = _num(w, r"(\d+)")
    if k == "blocked":
        return "Waiting for permission"
    if k == "ask":
        return "Asked a question"
    if k == "abort":
        return "Interrupted — needs a new instruction"
    if k == "ctx95":
        return "Context %s%% — auto-compact soon" % n
    if k == "ctx85":
        return "Context %s%%" % n
    if k == "wreck":
        return "Leftover edits" + (" in %s files" % n if n else "")
    if k == "stall":
        return "Subagent silent %s min · parent waiting" % n
    if k == "loop":
        m = re.match(r"^(.*?) 같은 호출 (\d+)회", w)
        return "Same call repeated " + ("%s× · %s" % (m.group(2), m.group(1)) if m else "%s×" % n)
    if k == "toolfail":
        m = re.search(r"(\d+)회 반복 · (.*)$", w)
        return "Same error repeated " + ("%s× · %s" % (m.group(1), m.group(2)) if m else "%s×" % n)
    if k == "fail":
        c = _num(w, r"등 (\d+)건")
        return "Failure alert" + (" (%s)" % c if c else "")
    if k == "done":
        return "Done · waiting for input %s min" % n
    if k == "bgdone":
        return "%s agent completion(s) unread" % n
    if k == "gone":
        return "Disconnected?" if w.endswith("?") else "Disconnected"
    if k == "conflict":
        m = re.search(r"파일 (\d+) · (세션|서브에이전트|에이전트) (.*)$", w)
        return "Conflict risk" + (" · %s file(s) · %s %s" % (m.group(1), "sessions" if m.group(2) == "세션" else "subagents",
                                                           re.sub(r"(^|, )메인(?=,|$)", r"\1main", m.group(3)))
                                  if m else "")
    return k or "needs attention"


def brief_attention(rows=None):
    """Sessions currently needing the user — labels only (project, branch, why, score). `why` is English (MCP output)."""
    rows = _rows() if rows is None else rows
    # ⚠The snapshot lacks permission-marker «blocked» rows; apply them as state() does, or approvals never reach MCP attention.
    rows = perm_rows(rows, _now())   # unguarded: a failure must surface, not silently drop blocked rows
    a = attention(rows, cards(50), quota()) or {}
    out = []
    for x in a.get("rows") or []:
        sg = [s for s in x.get("sigs") or () if isinstance(s, dict)]
        why = (_why_en(sg[0]) + (" +%d more" % (len(sg) - 1) if len(sg) > 1 else "")) if sg else "needs attention"
        out.append({"sid8": _sid8(x.get("sid")), "project": x.get("project") or "", "branch": x.get("branch") or "",
                    "why": why, "score": x.get("score")})
    return {"ok": True, "rows": out}
