"""`/api/state` (split out of chat_server.py 2026-09-24): `state()` and the short shared body cache `_state_body`."""
import json
import os
import threading
import time

from sidereus import config
from sidereus.config import CFG, MINE, ROOM_DEFAULT, VIEWER_ME, _lock, viewer_ids
from sidereus.features import snapshot as features_snapshot, state_off
from sidereus.bus import DM_MAX, _ack_cut, _load, ack_map, cursors, messages, messages_first, presence
from sidereus.cards import cards, cards_read, cards_read_ids
from sidereus.usage import quota_who, usage
from sidereus.bgtasks import _bg_lock, _bg_skipped_mb, _bg_skips
from sidereus.ext import ext_usage_today
from sidereus.sessions import sessions_cached
from sidereus.perm_marks import perm_rows
from sidereus.sessions_health import health, selfcheck
from sidereus.failures import fail1h
from sidereus.git_wt import wt_orders
from sidereus.quota import quota
from sidereus.quota_roots import quota_accounts
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.saver import _saver_state, _saver_switch, _saver_view, _saver_views
from sidereus.mail_idle import annotate as mail_idle_annotate
from sidereus.attention import attention
from sidereus.arch_map import runs as arch_runs, sec_runs
from sidereus.pl_reqs import view as pl_reqs_view
from sidereus.review import review
from sidereus.room_tags import load as room_tags_load
from sidereus.room_admin import load as room_admin_load
from sidereus.term import term_cfg
from sidereus.page import PAGE_BUILD
from sidereus.warn import warn_once
from sidereus.redact import redact_rooms
from sidereus.burn import used5_peek
from sidereus.burn_calc import _qb_forecast
from sidereus.transcript import iso_epoch
from sidereus.memo import BoundedMemo
from sidereus.ui_prefs import rev as ui_prefs_rev


STATE_FRESH_S = 1.0   # snapshot this fresh is served as-is (a second tab polling right after)
STATE_WAIT_S = 0.5    # wait for the kicked refresh; slower -> last snapshot (one poll stale)
STATE_COLD_S = 60.0   # no snapshot yet (just restarted): wait for the first one — [] would read as «no sessions»


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
    """[{label, primary, dir}] for the account colour band and tooltips; None (key dropped) with a single account."""
    a = claude_accounts()
    return [{"label": r["label"], "primary": bool(r["primary"]), "dir": r.get("dir") or ""} for r in a] if len(a) >= 2 else None


def _piece(key, fn, default, *args):
    """One optional /api/state piece: on any exception return `default` and warn (soft, key per piece).
    ★2026-09-25: an unguarded derived piece (attention · wt_orders · quota_who · ext_usage_today …) raising
      failed the whole /api/state, so every poll froze the entire screen for one side panel.
    ⚠Defaults must match what web/js/95-poll.js already tolerates (`s.x || null` / `|| {}`) — no new shapes.
    ⚠Core pieces (messages bundle · sessions · cards · cardsRead) are NOT wrapped: an empty default there
      would lie (no sessions / every card unread -> toast storm), so they keep failing loudly."""
    try:
        return fn(*args)
    except Exception as e:
        warn_once("state-" + key, "state piece {key} failed ({err}) — sent empty",
                  vars={"key": key, "err": f"{type(e).__name__}: {e}"}, soft=True)
        return default


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


def _scale_rows(rows, old_total, used):
    """Rescale OTel row tokens onto the shared headline (largest remainder, so rows + «others» sum to `used`).
    Each row's `share` is kept — it is the OTel ratio; only the token figure moves."""
    if not rows or old_total <= 0 or used is None:
        return rows
    raw = [r.get("tok") or 0 for r in rows]
    target = int(round(sum(raw) * used / float(old_total)))
    exact = [t * used / float(old_total) for t in raw]
    out = [int(x) for x in exact]
    for i in sorted(range(len(out)), key=lambda i: -(exact[i] - out[i]))[:max(0, target - sum(out))]:
        out[i] += 1
    return [dict(r, tok=t) for r, t in zip(rows, out)]


def state(since=0, ncards=50):
    """Full screen state received by polling (2.5s).

    ★2026-09-07 — **the lock is not held through slow work** (AUDIT cause 4). Previously `with _lock:` also
      called `sessions()`. `sessions()` runs `ps`·`lsof`·git·transcript parsing, so
      at worst it takes minutes, and meanwhile **invite handling (writes)** using the same lock hung entirely.
      Measured (2026-09-07 · `sessions()` simulated at 1.0s): before = the write path waited **0.880s** on the lock
      ⇒ after = 0.000s. With no wait cap, even when the page froze `dot` did not go off and **it did not look broken.**
    ★What `_lock` actually guards is only **the pair invite handling touches**:
      `rooms.json` (read-modify-write) and the invite message then appended to `bus.jsonl`. So only that pair —
      the conversation·roster bundle (presence·acks·messages·cursors·rooms·profiles) — is read together in **one short lock**.
      Measured, the whole bundle is 0.022s (orders of magnitude from sessions cold 0.515s).
      ⚠Why it must not be split: if the invite message is visible but not in the roster, or vice versa, the screen lies.
    ⚠`sessions()`·`cards()`·`usage()` touch **nothing** `_lock` guards (each uses
      `_parse_lock`·`_bg_lock`·`_usage_lock`). That is why they moved outside, and 6 other places
      (timeline·work history·git·leftovers·wkuse·invites) were already calling `sessions()` without `_lock`."""
    _q0 = _piece("quota", quota, None)   # not called twice — the saver decision below uses the same value
    _q0 = _with_accounts(_q0)
    # ── slow things run **outside** the lock into locals (even if this takes seconds, the write path is not blocked)
    # ⚠Never sessions() here: a background refresh fills the snapshot; wait ≤0.5 s, else serve the last one (2026-09-29).
    _sessions = sessions_cached(wait=STATE_WAIT_S, max_age=STATE_FRESH_S, cold_wait=STATE_COLD_S)[0]
    _sessions = _piece("permWait", perm_rows, _sessions, _sessions)   # permission-prompt markers -> «Awaiting approval»
    _cards = cards(ncards)       # task-complete cards (automatic transitions + ones sessions left themselves)
    _usg = _piece("usage", usage, None)   # tokens·cost (local aggregate) — (⚠must not clash with the global `_usage` name)
    _piece("selfcheck", selfcheck, None, _sessions)   # ★must run **before** health() to make it into this poll
    _health = _piece("health", health, None)   # ★server self-status — pulls `viewer.err` onto the screen
    _cread, _cread_ids = cards_read(), cards_read_ids()
    # ★`_bg_skips`·`_bg_skipped_mb` are mutated by `_running_bg_locked` inside `_bg_lock`.
    #   ⚠Previously `_lock` serializing polls kept this from blowing up; with that removed, **read under the owner lock**.
    #     `sum(d.values())` raises `RuntimeError: dictionary changed size during
    #     iteration` the moment someone inserts a key, and then that poll's state vanishes entirely.
    with _bg_lock:
        _bgskip = {"n": sum(_bg_skips.values()),
                   "mb": round(sum(_bg_skipped_mb.values()), 1)}
    # ── the lock is held only while reading «the pair that overlaps invite handling». Placed last so the conversation is freshest.
    with _lock:
        _presence = presence()   # ●online (watcher heartbeat) · ◐recent call · ○stale
        _acks = ack_map()        # ✔confirmed (recipient explicit) · ➡delivered (automatic) — a stronger signal than cursors
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
    _arun = _piece("archRun", arch_runs, {}, _sessions)
    _srun = _piece("secRun", sec_runs, {}, _sessions)
    out = {
        "presence": _presence,
        "acks": _acks,
        # ★acks for messages before this time (ns) are not in the response — the basis for the screen separating "unread" from "no record"
        "acksSince": _ack_cut(),
        "messages": _messages,
        "cursors": _cursors,
        "rooms": _rooms,
        "roomTags": _piece("roomTags", room_tags_load, {}),   # Sidereus-owned hashtags (sidereus/room_tags.py)
        "roomAdmin": _piece("roomAdmin", room_admin_load, {"hidden": {}, "pending": {}}),   # hide/pending overlay (sidereus/room_admin.py)
        "profiles": _profiles,
        "sessions": _sessions,
        "projGone": _piece("projGone", proj_gone, [], _sessions),   # session folders gone from disk — dropped from project chips
        "cards": _cards,
        "attention": _attn,       # who needs me now (metadata only)
        "review": _piece("review", review, None, _sessions),   # finished sessions' unreviewed uncommitted files (metadata only)
        "archRun": _arun,   # arch-map runs in progress per project (sidereus/arch_map.py)
        "secRun": _srun,   # security-checks runs in progress per project (same shape)
        "plReq": _piece("plReq", pl_reqs_view, {}, _sessions, _arun, _srun),   # sent run requests + receiver state (sidereus/pl_reqs.py)
        "wtOrder": _piece("wtOrder", wt_orders, {}, _sessions, _attn),   # Branches tab card order per repo — server is the only sorter
        "build": PAGE_BUILD,      # ★if an open tab holds old JS the screen does not render (measured 2026-08-19)
        "usage": _usg,
        # ★Diagnostic: spans skipped in background decisions (when a session writes too fast). Nonzero means
        #   notifications were scanned separately that many times — the root spot of finished agents lingering.
        "bgskip": _bgskip,
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
        "fail1h": _piece("fail1h", fail1h, None),        # header «Failures (1h)» card — cache from _fail_loop (60s), no scan here
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


def _state_body(since, nc):
    """Serialized `/api/state` body — reused for `_STATE_TTL` for the same arguments.

    ★Carries the compressed copy (`gzbox`) too — so 3.7MB is not recompressed on every poll.
    """
    key = (since, nc)
    with _state_cache_lock:
        hit = _state_cache.get(key)
        now = time.monotonic()
        if hit and (now - hit[0]) < _STATE_TTL:
            return hit[1], hit[2]
        if key in _state_building and hit and (now - hit[0]) < _STATE_STALE:
            return hit[1], hit[2]         # someone else is building — hand out the stale value and step aside
        _state_building.add(key)
    try:
        body = json.dumps(state(since, nc), ensure_ascii=False)
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
