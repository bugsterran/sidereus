"""Work-unit layer over worktrees (Branches tab): quota/token share, health, card order. Metadata only.
Split out of sidereus/git.py; git imports the names it uses from here."""
import os
import subprocess
import threading
import time
from sidereus.git_view import flow_base
from sidereus.gitinfo import _git_run
from sidereus.sessions import sessions_rows
from sidereus.usage import WHO_KEEP, WHO_STEP, _usage, _usage_lock, quota_who
from sidereus.warn import warn_once


# ── Work-unit signals (Sidereus's own layer over the worktree list): quota share, health. Metadata only.
WT_STALE_DAYS = 7           # no live session and no change for this many days -> «stale» (client decides liveness)
WT_HEALTH_MAX = 12          # per-worktree git calls (status + rev-list) for the first N worktrees only
WT_MTIME_MAX = 60           # dirty files stat'ed for the newest-change time
WT_SNAP_S = 60              # sid->root may be this stale (a new sid only moves token attribution)
_WT_SID = {}                # sid -> worktree-matchable root, remembered past the 12h sessions() window
_WT_DAY = {"mid": 0, "bk": {}, "cov": 0, "last": 0}   # today's copies of 5-min `byc` buckets (byc keeps only ~5h)
_WT_LOCK = threading.Lock()
_WT_THR = []


def _wt_key(p):
    """Same normalisation as the client's brNorm: drop /private, trailing slashes."""
    p = str(p or "")
    if p.startswith("/private/"):
        p = p[8:]
    return p.rstrip("/")


def _wt_pick(root, keys):
    """Longest worktree path containing `root` (the main checkout contains .claude/worktrees/* too)."""
    c, best = _wt_key(root), ""
    for p in keys:
        if (c == p or c.startswith(p + "/")) and len(p) > len(best):
            best = p
    return best


def _sid_roots(rows, mem=None):
    """Session rows -> {sid: root}. Subagent tokens are already keyed by the parent sid (OTel + `_who_scan`)."""
    out = dict(mem or {})
    for r in rows or []:
        if isinstance(r, dict) and r.get("sid"):
            root = (r.get("wt") or {}).get("root") or r.get("cwd") or ""
            if root:
                out[r["sid"]] = root
    return out


def wt_tokens(paths, sid_root, cyc_bk, day_bk, start, mid):
    """Pure: per-worktree tokens -> ({path: {cyc, day}}, cycle total). Buckets are {t0: {sid: tokens}}."""
    keys = {_wt_key(p): p for p in paths}
    hit = {}
    for sid, root in sid_root.items():
        k = _wt_pick(root, keys)
        if k:
            hit[sid] = keys[k]
    out = {p: {"cyc": 0, "day": 0} for p in paths}
    total = 0
    for t0, row in cyc_bk.items():
        if t0 + WHO_STEP <= start:
            continue
        for sid, tk in row.items():
            total += tk
            if sid in hit:
                out[hit[sid]]["cyc"] += tk
    for t0, row in day_bk.items():
        if t0 < mid:
            continue
        for sid, tk in row.items():
            if sid in hit:
                out[hit[sid]]["day"] += tk
    return out, total


def _wt_fold(now=None):
    """Copy today's `byc` buckets into `_WT_DAY` (they roll off byc after ~5h). Open buckets are overwritten."""
    now = time.time() if now is None else now
    mid = time.mktime(time.localtime(now)[:3] + (0, 0, 0, 0, 0, -1))
    with _usage_lock:
        bk = {k: dict(v) for k, v in (_usage.get("byc") or {}).items() if k >= mid}
        since = _usage.get("bycSince") or now
        seed = _usage.get("bycSeed") or {}
    cov = min(since, seed["cov"]) if seed.get("done") and seed.get("cov") else since
    reach = WHO_KEEP - 2 * WHO_STEP
    with _WT_LOCK:
        d = _WT_DAY
        if d["mid"] != mid:
            d.update({"mid": mid, "bk": {}, "cov": cov, "floor": 0, "last": 0})
        if d["last"] and now - d["last"] > reach:
            d["floor"] = now - reach      # ⚠a fold gap longer than byc's reach lost buckets
        d["cov"] = min(d["cov"], cov)     # a finished seed can only widen coverage
        d["bk"].update(bk)
        d["last"] = now
        return mid, dict(d["bk"]), max(d["cov"], d.get("floor") or 0)


def _wt_fold_loop():
    while True:
        time.sleep(60)
        try:
            _wt_fold()
        except Exception as e:
            warn_once("wt-fold", "worktree usage fold failed ({err}) — retrying next minute",
                      vars={"err": f"{type(e).__name__}: {e}"}, soft=True)


def _wt_git(path, base, is_main, run_in):
    """One worktree's health: dirty count, newest dirty mtime, ahead/behind vs base (local refs only, no fetch)."""
    h = {"dirty": 0, "chg": 0, "ahead": None, "behind": None, "base": ""}
    # ⚠-unormal: with -uno a worktree holding only new files read clean; normal folds an untracked dir into one "dir/" entry
    r = run_in(path, ["status", "--porcelain", "-unormal", "-z", "--no-renames"])
    if r.returncode == 0:
        fs = [rec[3:] for rec in r.stdout.split("\0") if len(rec) > 3]
        h["dirty"] = len(fs)
        for f in fs[:WT_MTIME_MAX]:
            try:
                h["chg"] = max(h["chg"], int(os.path.getmtime(os.path.join(path, f))))
            except OSError:
                pass                      # deleted/renamed since `git status`: not a change time
    if base and not is_main:
        r = run_in(path, ["rev-list", "--left-right", "--count", base + "...HEAD"])
        p = r.stdout.split() if r.returncode == 0 else []
        if len(p) == 2 and p[0].isdigit() and p[1].isdigit():
            h.update({"behind": int(p[0]), "ahead": int(p[1]), "base": base})
    return h


def wt_base(branch, flow, fallback, local):
    """-> (base, prTargets) for one worktree; a git-flow base that is not a local branch falls back (no fetch)."""
    b, pr = flow_base(branch, flow, fallback)
    remote_ok = bool(flow and ((flow.get("devRemote") and b == flow.get("develop"))
                               or (flow.get("mstRemote") and b == flow.get("master"))))   # remote-tracking refs are local refs too
    if pr and b not in local and not remote_ok:
        return fallback, []
    return ("" if branch == b else b), pr


def wt_signals(wts, branches, commits, rows=None, now=None, flow=None, wait=None, miss=None):
    """-> {wtSig: {path: {cyc, day, share, dirty, chg, last, ahead, behind, base, pr}}, wtTok: {...}}."""
    now = time.time() if now is None else now
    from sidereus.quota import quota       # lazy: quota loads after git_wt (STAGE3 order)
    from sidereus.git import BRANCH_TIMEOUT   # lazy: git loads after git_wt and imports it
    with _WT_LOCK:                        # ⚠check-and-start under the lock: concurrent requests would each start one
        if not _WT_THR:
            _WT_THR.append(threading.Thread(target=_wt_fold_loop, name="wt_fold", daemon=True))
            _WT_THR[0].start()
    qw = quota_who(quota(), now)
    start = qw.get("start") or (now - 5 * 3600)
    mid, day_bk, dcov = _wt_fold(now)
    with _usage_lock:
        cyc_bk = {k: dict(v) for k, v in (_usage.get("byc") or {}).items() if k + WHO_STEP > start}
    if rows is None:                      # ⚠not _allowed_cwds(): it keeps one row per cwd and drops sibling sids
        rows = sessions_rows(max_age=WT_SNAP_S)   # ⚠request path: poll's copy, never a cold sessions() (~1-40 s)
    with _WT_LOCK:
        _WT_SID.update(_sid_roots(rows))
        if len(_WT_SID) > 500:
            for k in list(_WT_SID)[:250]:
                _WT_SID.pop(k, None)
        sid_root = dict(_WT_SID)
    paths = [w["path"] for w in wts]
    tok, total = wt_tokens(paths, sid_root, cyc_bk, day_bk, start, mid)
    bts = {b["name"]: b.get("ts") or 0 for b in branches if b.get("kind") == "local"}
    cts = {c["sha"]: c.get("ts") or 0 for c in commits}
    base = next((w.get("branch") or "" for w in wts if w.get("main")), "")

    def run_in(p, args):
        try:
            return _git_run(p, args, BRANCH_TIMEOUT, wait=wait)
        except subprocess.TimeoutExpired:
            if miss is not None:
                miss.append("wt:" + args[0])   # `_wt_git` swallows it — the caller must still know
            raise
    sig = {}
    for i, w in enumerate(wts):
        s = dict(tok.get(w["path"]) or {"cyc": 0, "day": 0})
        s["share"] = round(s["cyc"] * 100.0 / total, 1) if total else 0
        s["last"] = bts.get(w.get("branch") or "") or cts.get(w.get("head") or "") or 0
        wb, pr = wt_base(w.get("branch") or "", flow, base, bts)
        if pr and not w.get("main"):
            s["pr"] = pr
        if i < WT_HEALTH_MAX and os.path.isdir(w["path"]):
            try:
                s.update(_wt_git(w["path"], wb, w.get("main"), run_in))
            except Exception:
                pass                      # health columns are optional; the row still shows without them
        s["chg"] = max(s.get("chg") or 0, s["last"])
        sig[w["path"]] = s
    return {"wtSig": sig, "wtTok": {"total": total, "start": int(start), "partial": bool(qw.get("partial")),
                                    "mid": int(mid), "dayCov": int(dcov or 0), "dayPartial": bool(dcov and dcov > mid)}}


# ── Worktree card order (Branches tab). ★Single source since 2026-09-24: the screen no longer sorts (brWtOrder removed).
WT_ATTN_LIST_ONLY = frozenset(("done", "bgdone", "gone"))   # ⚠mirror of ATTN_LIST_ONLY (17-attention.js)
_WT_LAST = {"sess": [], "attn": []}   # last poll's sessions + attention rows, for the /api/branches fallback order


def wt_sort_key(i, sc, live, act):
    """Attention score desc, then has live sessions, then latest activity desc, then input order."""
    return (-sc, 0 if live else 1, -act, i)


def wt_order(wts, wt_sig, sess, attn_rows, now=None):
    """Pure: worktree paths in card order. Session -> worktree = longest path containing (wt.root or cwd).
    Live = state != done; activity = max(sig.chg, now - ageSec of live sessions); score = best attention row
    of any of its sessions that carries a non-list-only signal."""
    now = time.time() if now is None else now
    keys = {_wt_key(w.get("path")) for w in wts}
    sids, live = {}, {}
    for x in sess or []:
        if not isinstance(x, dict):
            continue
        k = _wt_pick((x.get("wt") or {}).get("root") or x.get("cwd"), keys)
        if not k:
            continue
        if x.get("sid"):
            sids.setdefault(k, set()).add(x["sid"])
        if x.get("state") != "done" and x.get("cwd"):
            live.setdefault(k, []).append(x)
    score = {}
    for r in attn_rows or []:
        if any(s.get("k") not in WT_ATTN_LIST_ONLY for s in r.get("sigs") or []):
            sid = r.get("sid")
            score[sid] = max(score.get(sid, 0), r.get("score") or 0)
    ks = []
    for i, w in enumerate(wts):
        k = _wt_key(w.get("path"))
        ss = live.get(k, [])
        sc = max([score.get(s, 0) for s in sids.get(k, ())] or [0])
        act = max([(wt_sig.get(w.get("path")) or {}).get("chg") or 0] + [now - (x.get("ageSec") or 0) for x in ss])
        ks.append((wt_sort_key(i, sc, bool(ss), act), w.get("path")))
    return [p for _, p in sorted(ks)]


def wt_orders(sess, attention, now=None):
    """Poll side (state()): live card order for each repo whose branch graph the server holds -> {cwd: [paths]}.
    ⚠The screen keeps the fetched graph but re-orders on every poll as attention/sessions change — so the order rides the poll."""
    from sidereus.git import _branch_cache   # lazy: git loads after git_wt and imports it
    rows = (attention or {}).get("rows") or []
    _WT_LAST.update(sess=sess or [], attn=rows)
    newest = {}
    try:
        for (cwd, _n), (at, out) in list(_branch_cache.items()):
            if cwd not in newest or at > newest[cwd][0]:
                newest[cwd] = (at, out)
    except RuntimeError:                  # cache cleared mid-copy by a request thread — skip this poll
        return {}
    return {cwd: wt_order(out.get("worktrees") or [], out.get("wtSig") or {}, sess, rows, now)
            for cwd, (_at, out) in newest.items() if len(out.get("worktrees") or []) > 1}
