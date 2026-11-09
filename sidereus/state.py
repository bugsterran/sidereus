"""`/api/state` (split out of chat_server.py 2026-09-24): `state()` and the short shared body cache `_state_body`."""
import json
import os
import threading
import time

from sidereus import config
from sidereus.config import CFG, MINE, ROOM_DEFAULT, VIEWER_ME, _lock, viewer_ids
from sidereus.features import on as feature_on, snapshot as features_snapshot, state_off
from sidereus.bus import DM_MAX, AckMapError, _ack_cut, _load, ack_map, ack_ver, cursors, messages, messages_first, presence
from sidereus.cards import cards, cards_read, cards_read_ids
from sidereus.usage import quota_who, usage
from sidereus.ext import ext_usage_today
from sidereus.sessions import sessions_cached, snapshot_age
from sidereus.perm_marks import perm_rows
from sidereus.sessions_health import health, selfcheck
from sidereus.git_wt import wt_orders
from sidereus.quota import quota
from sidereus.quota_roots import quota_accounts, same_labels as quota_same_labels
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.saver import _saver_state, _saver_switch, _saver_view, _saver_views
from sidereus.mail_idle import annotate as mail_idle_annotate
from sidereus.attention import attention
from sidereus.arch_map import runs as arch_runs, sec_runs, brief_runs
from sidereus.pl_reqs import view as pl_reqs_view
from sidereus.review import review
from sidereus.todo import state_counts as todo_counts
from sidereus.term import term_cfg
from sidereus.page import PAGE_BUILD
from sidereus.warn import warn_once
from sidereus.redact import redact_rooms
from sidereus.burn import used5_peek
from sidereus.plat_pi import who_5h as pi_who_5h
from sidereus.ident import _sid8
from sidereus.burn_calc import _qb_forecast
from sidereus.transcript import iso_epoch
from sidereus.memo import BoundedMemo, request_path
from sidereus import proc_load
from sidereus.ui_prefs import rev as ui_prefs_rev


STATE_FRESH_S = 1.0   # snapshot this fresh is served as-is (a second tab polling right after)
STATE_WAIT_S = 0.5    # wait for the kicked refresh; slower -> last snapshot (one poll stale)
STATE_COLD_S = 60.0   # no snapshot yet (just restarted): wait for the first one — [] would read as «no sessions»
# ★2026-11-04 (load 100-190): /api/state took 30-39 s and the page showed «Disconnected» — with FRESH 1 s nearly every
#   poll kicked a refresh and waited WAIT. A snapshot this young is served at once (refresh still kicked, no wait).
STATE_SERVE_S = 5.0
SLOW_PIECE_MS = 300   # srvLoad.slow: pieces of one build at least this slow
SLOW_MAX = 5
_tick = time.monotonic       # piece timing; ⚠tests patch
_loadavg = getattr(os, "getloadavg", None)   # absent on Windows -> load1 None
_build = threading.local()   # .slow = [(piece, ms)] of the state() build running on this thread


def _with_accounts(q0):
    """Attach extra signed-in roots for the KPI popover; `q0` is returned as-is when there are none."""
    acc = _piece("quotaAccounts", quota_accounts, None)
    if acc:
        _piece("quotaAccountsOver", _accounts_over, None, acc)
    return dict(q0 or {}, accounts=acc) if acc else q0


def _accounts_over(rows):
    """5h `over_at` per extra account from its pts ring — same forecast as the primary (`_qb_forecast`), only with >=2 recent points."""
    now = time.time()
    for r in rows:
        fh = r.get("five_hour") or {}
        pts, pct = fh.get("pts"), fh.get("pct")
        if not pts or not isinstance(pct, (int, float)):
            continue
        _rate, _raw, over_at, n_obs = _qb_forecast(now, [(float(t), h) for t, h in pts], pct,
                                                   max(0.0, float(fh.get("leftSec") or 0)))
        if n_obs >= 2:
            fh["over_at"] = int(over_at) if over_at else None


def _accts():
    """[{label, primary, dir, same?}] for the account colour band and tooltips; None (key dropped) with a single account.
    `same`: signed in to the primary's account, so the page never picks it as a separate main (`mainAcctOk`)."""
    a = claude_accounts()
    if len(a) < 2:
        return None
    same = quota_same_labels(a)
    return [dict({"label": r["label"], "primary": bool(r["primary"]), "dir": r.get("dir") or ""},
                 **({"same": True} if r["label"] in same else {})) for r in a]


def _piece(key, fn, default, *args):
    """One optional /api/state piece: on any exception return `default` and warn (soft, key per piece).
    ★2026-09-25: an unguarded derived piece (attention · wt_orders · quota_who · ext_usage_today …) raising
      failed the whole /api/state, so every poll froze the entire screen for one side panel.
    ⚠Defaults must match what web/js/95-poll.js already tolerates (`s.x || null` / `|| {}`) — no new shapes.
    ⚠Core pieces (messages bundle · sessions · cards · cardsRead) are NOT wrapped: an empty default there
      would lie (no sessions / every card unread -> toast storm), so they keep failing loudly."""
    t0 = _tick()
    try:
        return fn(*args)
    except Exception as e:
        warn_once("state-" + key, "state piece {key} failed ({err}) — sent empty",
                  vars={"key": key, "err": f"{type(e).__name__}: {e}"}, soft=True)
        return default
    finally:
        _slow_note(key, t0)


def _slow_note(key, t0):
    ms = int((_tick() - t0) * 1000)
    slow = getattr(_build, "slow", None)
    if slow is not None and ms >= SLOW_PIECE_MS:
        slow.append((key, ms))


def _srv_load():
    """state().srvLoad {load1, ncpu, snapAge, slow, top} — machine load (top: heaviest session tree, proc_load) and this build's slow pieces (metadata only).
    ⚠Unknown stays None (no getloadavg / no snapshot), never 0."""
    try:
        l1 = round(float(_loadavg()[0]), 2) if _loadavg else None
    except (OSError, TypeError, ValueError, IndexError):
        l1 = None
    age = snapshot_age()
    slow = sorted(getattr(_build, "slow", None) or [], key=lambda x: -x[1])[:SLOW_MAX]
    # ncpu lets the page call load busy only relative to the core count (None = unknown).
    return {"load1": l1, "ncpu": os.cpu_count() or None, "snapAge": round(age, 1) if age is not None else None,
            "slow": [[k, ms] for k, ms in slow], "top": proc_load.top()}


PROJ_DIR_TTL_S = 30.0   # s — per-path isdir memo, so the 2.5 s poll does not stat every session folder each time
PROJ_DIR_MAX = 512
_proj_dir_memo = BoundedMemo(PROJ_DIR_MAX)   # path -> (monotonic, exists); LRU keeps the cap
_isdir = os.path.isdir  # ⚠tests patch these two
_mono = time.monotonic


def proj_gone(sessions):
    """Sorted session cwd/repos paths that no longer exist — the project chips (80 strProjList) skip them.
    ⚠Deleted worktrees leave their sessions behind; the rows stay in sessions/timeline/history, only the chip goes."""
    now, out = _mono(), set()
    for r in sessions or []:
        if not isinstance(r, dict):
            continue
        for p in [r.get("cwd")] + list(r.get("repos") or []):
            if not isinstance(p, str) or not os.path.isabs(p) or p in out:
                continue
            hit = _proj_dir_memo.get(p)
            if hit is None or now - hit[0] >= PROJ_DIR_TTL_S:
                hit = _proj_dir_memo.put(p, (now, bool(_isdir(p))))
            if not hit[1]:
                out.add(p)
    return sorted(out)


USED5_TOL = 60   # s — windows this close are the same 5h cycle


def _used5_one(usg, who, now=None):
    """Point `usage.block.tokens` and `quotaWho.total` at the status bar's 5h figure (`burn.used5_peek`).
    ⚠Only for the same window: a ccusage block opening before the official cycle is a different span — left as is."""
    p = used5_peek(now)
    if not p or p[0] is None:
        return usg, who
    start, used = p[0], p[2]
    b = (usg or {}).get("block")
    if b and abs(iso_epoch(b.get("start"), 0) - start) <= USED5_TOL:
        usg = dict(usg, block=dict(b, tokens=used))
    if who and abs((who.get("start") or 0) - start) <= USED5_TOL:
        rows = _scale_rows(who.get("rows") or [], who.get("total") or 0, used)
        # cut projects' tokens = the remainder, so rows + othersTok == used exactly
        who = dict(who, total=used, rows=rows, othersTok=max(0, used - sum(r.get("tok") or 0 for r in rows)))
    return usg, who


WHO_TOP = 6   # same cut as usage.quota_who(top=6)


def _who_pi(who, now=None):
    """Add pi rows (provider anthropic, inside who.start..now) to «Who is using the 5h» of the account QWHO shows.
    ⚠Any `acct`: QWHO shows the account in use (usage._who_window); pi's Claude login is assumed to be that one.
    ⚠`total` is a local sum (Claude transcripts via used5, else OTel), so pi is not in it: pi adds to total.
    Re-sorts, cuts at WHO_TOP and folds the overflow into others/othersTok so rows + othersTok == total."""
    if not who or not who.get("start"):
        return who
    now = time.time() if now is None else now
    pi = pi_who_5h(float(who["start"]), now)
    add = [{"name": nm, "tok": e["tok"], "n": len(e["sids"]), "plat": "pi",
            "sids": [{"sid": _sid8(s), "tok": t} for s, t in sorted(e["sids"].items(), key=lambda x: -x[1])[:5]]}
           for nm, e in pi.items() if e.get("tok")]
    if not add:
        return who
    rows = sorted(list(who.get("rows") or []) + add, key=lambda r: -(r.get("tok") or 0))
    total = (who.get("total") or 0) + sum(r["tok"] for r in add)
    keep, cut = rows[:WHO_TOP], rows[WHO_TOP:]
    keep = [dict(r, share=round((r.get("tok") or 0) * 100.0 / total, 1) if total else 0) for r in keep]
    return dict(who, rows=keep, total=total, piTok=sum(r["tok"] for r in add),
                others=(who.get("others") or 0) + len(cut),
                othersTok=total - sum(r.get("tok") or 0 for r in keep))


def _scale_rows(rows, old_total, used):
    """Rescale OTel row tokens onto the shared headline (largest remainder, so rows + «others» sum to `used`).
    Each row's `share` is kept — it is the OTel ratio; only the token figure moves."""
    if not rows or old_total <= 0 or used is None:
        return rows
    out = _lr_scale([r.get("tok") or 0 for r in rows], used, float(old_total))
    res = []
    for r, t in zip(rows, out):
        r2 = dict(r, tok=t)
        ss = [s for s in (r.get("sids") or []) if isinstance(s, dict)]
        if ss and (r.get("tok") or 0) > 0:
            # ⚠sids scale with their row, else a session shows 6.7M under a 203K project
            st = _lr_scale([s.get("tok") or 0 for s in ss], t, float(r.get("tok")))
            r2["sids"] = [dict(s, tok=v) for s, v in zip(ss, st)]
        res.append(r2)
    return res


def _lr_scale(raw, num, den):
    """`raw` * num/den in ints by largest remainder, so the parts sum to round(sum(raw) * num/den)."""
    target = int(round(sum(raw) * num / den))
    exact = [t * num / den for t in raw]
    out = [int(x) for x in exact]
    for i in sorted(range(len(out)), key=lambda i: -(exact[i] - out[i]))[:max(0, target - sum(out))]:
        out[i] += 1
    return out


def state(since=0, ncards=50, acks_v=""):
    """`_state_poll` with process probes answering from cache only — a poll never spawns or waits on probe locks."""
    with request_path():
        return _state_poll(since, ncards, acks_v)


def _state_poll(since=0, ncards=50, acks_v=""):
    """Full screen state received by polling (2.5s). `acks_v` = the page's acksV; when it matches, `acks` is omitted.

    ★2026-09-07 — **the lock is not held through slow work** (AUDIT cause 4). Previously `with _lock:` also
      called `sessions()`. `sessions()` runs `ps`·`lsof`·git·transcript parsing, so
      at worst it takes minutes, and meanwhile the viewer's write path on the same lock hung entirely.
      Measured (2026-09-07 · `sessions()` simulated at 1.0s): before = the write path waited **0.880s** on the lock
      ⇒ after = 0.000s. With no wait cap, even when the page froze `dot` did not go off and **it did not look broken.**
    ★The viewer no longer writes rooms.json (rooms are managed by sessions via the mailbox MCP); `_lock` now only keeps
      the conversation·roster bundle (presence·acks·messages·cursors·rooms·profiles) read together in **one short lock**.
      Measured, the whole bundle is 0.022s (orders of magnitude from sessions cold 0.515s).
    ⚠`sessions()`·`cards()`·`usage()` touch **nothing** `_lock` guards (each uses
      `_parse_lock`·`_bg_lock`·`_usage_lock`). That is why they moved outside, and other places
      (timeline·work history·git·leftovers·wkuse) were already calling `sessions()` without `_lock`."""
    _build.slow = []
    _q0 = _piece("quota", quota, None)   # not called twice — the saver decision below uses the same value
    _q0 = _with_accounts(_q0)
    # ── slow things run **outside** the lock into locals (even if this takes seconds, the write path is not blocked)
    # ⚠Never sessions() here: a background refresh fills the snapshot; wait ≤0.5 s, else serve the last one (2026-09-29).
    _t0 = _tick()
    _sessions = sessions_cached(wait=STATE_WAIT_S, max_age=STATE_FRESH_S, cold_wait=STATE_COLD_S, serve=STATE_SERVE_S)[0]
    _slow_note("sessions", _t0)
    _sessions = _piece("permWait", perm_rows, _sessions, _sessions)   # permission-prompt markers -> «Awaiting approval»
    _cards = cards(ncards)       # task-complete cards (automatic transitions + ones sessions left themselves)
    _usg = _piece("usage", usage, None)   # tokens·cost (local aggregate) — (⚠must not clash with the global `_usage` name)
    _piece("selfcheck", selfcheck, None, _sessions)   # ★must run **before** health() to make it into this poll
    _health = _piece("health", health, None)   # ★server self-status — pulls `viewer.err` onto the screen
    _cread, _cread_ids = cards_read(), cards_read_ids()
    # ── the lock is held only while reading «the pair that overlaps invite handling». Placed last so the conversation is freshest.
    with _lock:
        _presence = presence()   # ●online (watcher heartbeat) · ◐recent call · ○stale
        _acut = _ack_cut()
        _av = ack_ver(_acut)     # ⚠taken before the read: a write in between only causes one extra full send
        _acks = ack_map(_acut)   # same cut as _av ✔confirmed (recipient explicit) · ➡delivered (automatic) — a stronger signal than cursors
        _messages = messages(since) if since else messages_first()   # first load: older bodies stubbed (bus.MSG_FIRST)
        _cursors = cursors()     # read marks are fresh on every response — existing bubbles update in place too
        _rooms = redact_rooms(_load("rooms.json", {}))   # topic is free text that reaches the page
        _profiles = _load("profiles.json", {})
    # ── assembling the dict itself needs no lock (only consistency at the moment each piece is read mattered)
    # unread mail on a session nothing will wake -> row mailIdle; needs the cursors/acks/rooms read above (bus lines from its parse cache)
    _sessions = _piece("mailIdle", mail_idle_annotate, _sessions, _sessions, None, _cursors, _acks, _rooms)
    _attn = _piece("attention", attention, None, _sessions, _cards, _q0, _cread, _cread_ids)
    _fh = (_q0 or {}).get("five_hour") or {}
    _who = _piece("quotaWho", quota_who, None, _q0)
    _usg, _who = _piece("used5", _used5_one, (_usg, _who), _usg, _who)   # one 5h «used» figure on every surface
    _who = _piece("quotaWhoPi", _who_pi, _who, _who)   # pi's Anthropic-billed use in the same window
    _arun = _piece("archRun", arch_runs, {}, _sessions)
    _srun = _piece("secRun", sec_runs, {}, _sessions)
    _brun = _piece("briefRun", brief_runs, {}, _sessions)
    out = {
        "presence": _presence,
        "acks": _acks,
        # ★acks for messages before this time (ns) are not in the response — the basis for the screen separating "unread" from "no record"
        "acksSince": _acut,
        "acksV": _av,
        "messages": _messages,
        "cursors": _cursors,
        "rooms": _rooms,
        "profiles": _profiles,
        "sessions": _sessions,
        "projGone": _piece("projGone", proj_gone, [], _sessions),   # session folders gone from disk — dropped from project chips
        "cards": _cards,
        "attention": _attn,       # who needs me now (metadata only)
        "review": _piece("review", review, None, _sessions),   # finished sessions' unreviewed uncommitted files (metadata only)
        # ⚠gated here, not only by state_off(): an off feature must not keep lstat-ing repos or writing ledgers
        "todo": _piece("todo", todo_counts, {}, _sessions) if feature_on("todo") else {},   # {cwd: {o, w, d}} from the DATA_DIR/todo store, counts only
        "archRun": _arun,   # arch-map runs in progress per project (sidereus/arch_map.py)
        "secRun": _srun,   # security-checks runs in progress per project (same shape)
        "briefRun": _brun,   # arch-brief runs (same shape); its end re-fetches /api/arch (84m)
        "plReq": _piece("plReq", lambda: pl_reqs_view(_sessions, _arun, _srun, brief_run=_brun), {}),   # sent run requests + receiver state (sidereus/pl_reqs.py)
        "wtOrder": _piece("wtOrder", wt_orders, {}, _sessions, _attn),   # Branches tab card order per repo — server is the only sorter
        "build": PAGE_BUILD,      # ★if an open tab holds old JS the screen does not render (measured 2026-08-19)
        "usage": _usg,
        "quota": _q0,                # ★official quota (%·reset) — same value as /usage
        # Quota modal «who is using the 5h» — per-project tokens in the current cycle (metadata only, not an attention signal).
        "quotaWho": _who,
        # saver mode — uses **the same decision** as the hook (screen and model must not disagree)
        "saver": _piece("saver", _saver_state, None, _fh.get("pct"), _fh.get("leftSec")),
        # «which mode is it now» snapshot dropped by the hook (including pace). None if absent — the screen hides the chip.
        "saverView": _piece("saverView", _saver_view, None),
        "saverSwitch": _piece("saverSwitch", _saver_switch, None),   # raw /saver switch files for the settings modal (5s TTL)
        "health": _health,
        "cardsRead": _cread,         # cards after this time are unread (stored on the server, not the browser)
        "cardsReadIds": _cread_ids,  # card keys read **individually** among them (`at|kind|project`)
        # ⚠External CLI tokens today, per platform — never merged into `usage`/`quota` (those are Claude-only).
        "extUsage": _piece("extUsage", ext_usage_today, {}),
        # ⚠Includes VIEWER_ME: /api/say · /api/dm · invites write from=VIEWER_ME, and the page marks `m.mine` from this
        #   list — without it the work-log DM trail (36-wkcompose.js) and unread/no-ack filters never saw the page's own posts.
        #   ⚠Both default spellings while viewer_me is unset — the author id follows the UI language (config.viewer_me_for).
        "mine": MINE + [i for i in viewer_ids(VIEWER_ME) if i not in MINE],
        # Settings only (never conversation content): JS strips these id prefixes in nmKey.
        "cfg": {"stripPrefixes": list(CFG.get("alias_strip_prefixes") or []),
                "defaultRoom": ROOM_DEFAULT,
                "viewerMe": VIEWER_ME,       # /api/say author id — a DM reply to this page's own post goes to its `to`
                "viewerIds": viewer_ids(VIEWER_ME),   # every id the page posts as (both default spellings when unset)
                "dmMax": DM_MAX,             # /api/dm body cap — the page packs review notes under it
                "termApp": _piece("termApp", term_cfg, "auto")},   # «To terminal» app override (auto|iterm|apple|orca|off)
        "features": features_snapshot(),   # {id: on} per manifest (sidereus/features.py) — core key
        "uiRev": ui_prefs_rev(),           # UI prefs write counter (int only); other tabs refetch /api/ui-prefs when it moves
        "codeDir": os.path.realpath(config.CODE_DIR) if config.IS_CLONE else "",   # clone path ("" = pip install) for the tour's `/plugin marketplace add` — core key
    }
    _ac = _piece("accts", _accts, None)   # labels only, present only with >=2 accounts (not in state_v1)
    if _ac:
        out["accts"] = _ac
        out["saverViews"] = _piece("saverViews", _saver_views, {})   # per-account hook snapshots, by label
    for k in state_off():                  # keys claimed by switched-off features are omitted
        out.pop(k, None)
    out["srvLoad"] = _piece("srvLoad", _srv_load, None)   # last: includes every piece timed above
    _build.slow = None
    if isinstance(_acks, AckMapError):
        out["acksV"] = ""                  # ⚠an error map is never versioned, or the page would keep it
    elif acks_v and acks_v == _av:
        out.pop("acks", None)              # page already holds this exact map (95-poll keeps ACK when the key is absent)
    return out


# ★**Short shared cache** for the `/api/state` body (2026-09-21). Not reducing the value, but «not building the same response
#   many times».
#   Measured: the `since=0` response is **3.7MB** (messages 1.7MB + acks 0.5MB · the rest is Korean text carried as-is).
#   The hook (`pct()` in `~/.claude/hooks/saver.py`) hits this **without `since`** on every prompt with
#   a 3s timeout. Firing 8 concurrently, **all 8 were cut off at 3s** (single shots 0.13~0.51s) ⇒ the hook
#   could not read the quota and dropped a `{"pct": null, "head": "Limit unknown"}` snapshot. The server knew
#   pct 56 at that very moment — to the user it looked like saver mode kicking in for no reason.
# ⚠Do not raise the TTL above the polling period (2.5s) — the screen lags noticeably.
# ⚠**Do not hold the lock through the build.** At first the build was put inside the lock as "serialization is the cure", and
#   it was reverted on the spot (2026-09-21): `state()` does not just serialize; it calls `claude agents --json`
#   ·`ps`·`pmset`. Under load that takes tens of seconds, so **every request hung on one lock**
#   (measured: right after restart `/api/state` hit the 90s timeout · at the same time `/api/quota/burn` returned 200 in 6.1s).
#   The key is `(since, nc)`, so the hook (since=0) and the browser (since=large) **could not share the cache yet
#   shared the lock** — one hook request stalled all screen polling.
# ⇒ Use the lock only to protect the dict and build the slow part outside. If the same key is already being built,
#   **do not wait**; serve a slightly stale body (stale-while-revalidate).
_STATE_TTL = 1.0
_STATE_STALE = 20.0   # while a build runs long, hold on the old body this long (better than a frozen screen)
_state_cache = {}
_state_building = set()
_state_cache_lock = threading.Lock()   # ⚠for protecting the dict·set only. Do not call `state()` inside this.


def _state_body(since, nc, acks_v=""):
    """Serialized `/api/state` body — reused for `_STATE_TTL` for the same arguments.

    ★Carries the compressed copy (`gzbox`) too — so 3.7MB is not recompressed on every poll.
    """
    key = (since, nc, acks_v)   # ⚠acks_v in the key: a body without `acks` must never reach a caller lacking that version
    with _state_cache_lock:
        hit = _state_cache.get(key)
        now = time.monotonic()
        if hit and (now - hit[0]) < _STATE_TTL:
            return hit[1], hit[2]
        if key in _state_building and hit and (now - hit[0]) < _STATE_STALE:
            return hit[1], hit[2]         # someone else is building — hand out the stale value and step aside
        _state_building.add(key)
    try:
        body = json.dumps(state(since, nc, acks_v) if acks_v else state(since, nc), ensure_ascii=False)
    finally:
        with _state_cache_lock:
            _state_building.discard(key)
    gzbox = [None]                        # ⚠must be a list so `_send` fills that very object inside the cache
    with _state_cache_lock:
        _state_cache[key] = (time.monotonic(), body, gzbox)
        if len(_state_cache) > 32:        # ⚠do not create a dict without expiry
            for k, v in list(_state_cache.items()):
                if (time.monotonic() - v[0]) >= _STATE_STALE:
                    _state_cache.pop(k, None)
    return body, gzbox


def state_cache_clear():
    """Drop cached `/api/state` bodies so the next poll reflects a just-saved switch (no 1 s stale undo)."""
    with _state_cache_lock:
        _state_cache.clear()
