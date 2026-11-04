"""Live probes: collector staleness, sid -> transcript lookups, official session list (`claude agents --json`),
the once-per-poll process snapshot, tool-busy and the blocked badge. Split out of `sidereus/live.py` (2026-09-24);
live.py re-exports these names, so importers are unchanged. Owns `_busy_cache` (rebound by `tool_busy`)."""
import glob
import json
import os
import re
import subprocess
import threading
import time
from sidereus.config import IS_MAC
from sidereus.memo import Refresher, on_request_path, serve_last
from sidereus import claude_roots
from sidereus.claude_roots import registry_sig as _av_registry_sig
from sidereus.warn import warn_once
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _slug, bin_path, bin_forget, is_claude_argv, rich_env

LIVE_STALE_S = 30      # when a query fails, **keep using the last good value this long** (reason: live_cwds in sidereus/live.py; also caps sid_alive)


def _slow_why():
    """The "why" attached to slowness warnings — 1-minute load at that moment, as warn_once `more=` parts.

    ★Evidence (measured 2026-09-09, after an unusual burst of warnings that day):
      `live-slow`·`agents-slow`·`mon-slow` fired together, but **the commands were fine** —
      measured directly at the same time: `ps` 0.03 s (cap 4 s) · `claude agents --json` 0.20 s (cap 6 s).
      40 samples over 4 min, **0** over the cap (load median 7.8 · max 9.3). Failures happened only during
      **load spikes** (load average at the 07:04~07:10 warnings was 14.77/20.58/16.53).
    ⇒ **Raising the cap is not justified by this measurement.** Normal is 1% of the cap, so exceeding 4 s means
      "100x slower at that moment", not "cap too short"; the spike size is unknown, so whether 8 s would do
      is unknown too. And every second added holds one poll that much longer.
    ⇒ So instead of a cap, attach **attribution**. A warning carrying "load 18.2" tells the user at once that
      the machine, not the viewer, is the thing to look at, and after a few the threshold load is measured too.
    ⚠Some environments lack `getloadavg` — on failure return an empty string (the warning itself is not lost)."""
    try:
        _l = os.getloadavg()[0]
        return [{"msg": "load {load} at the time", "vars": {"load": f"{_l:.1f}"}}]
    except (OSError, AttributeError):
        return []               # no getloadavg on this platform: the warning goes out without it


# ★★**"Using the last value" is surfaced on screen** (2026-09-21). The four collectors' fallbacks are right, but
#   the fact stayed only in `viewer.err`, so **the user could not tell how old the screen values were** (cumulative
#   `TimeoutExpired`: 70). ⇒ Where a fallback is taken, record the "last success time" here; `health()` puts it on the health strip.
#   ⚠Fallback rules (last value for N s) and `warn_once` texts are **not changed at all** — this dict only records.
#   ⚠Only **timestamps** go up (metadata only, never conversation text on the page).
_stale_lock = threading.Lock()
_stale = {}                 # collector key -> (last success time, last fallback time)
_STALE_LABEL = {"agents": "official sessions", "live": "processes", "mon": "watch processes", "busy": "tool runs"}
_STALE_SHOW_S = 15          # show only fallbacks taken within this window (poll 2.5 s — six polls).
#                             ⚠Without it a collector "never called again" (tool_busy is called conditionally)
#                               stays stale forever.


def _stale_mark(key, at):
    """A fallback was taken — record the last success time (`_stale_clear` removes it on success)."""
    with _stale_lock:
        _stale[key] = (at or 0.0, time.time())


def _stale_clear(key):
    with _stale_lock:
        _stale.pop(key, None)


_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_live_sids = [0.0, set()]      # (measured at, live session ids confirmed via `--resume <sid>`)
_live_pid_cwd = [0.0, {}]      # (measured at, claude pid -> cwd) — by-product of `live_cwds()` (used by the watcher check below)

# ★The sid in `--resume <sid>` is **not trusted blindly** (measured 2026-09-07). An argv sid proves *a process exists*,
#   not *that sid's file is being written now*. If the harness forks to a new transcript midway,
#   argv keeps pointing at the old file:
#     pid 57914 `claude --resume ff66ff66…` (cwd=~/bot-A)
#       ff66ff66….jsonl : 72.7 h ago · 279MB  ← abandoned file
#       ee55ee55….jsonl : just now · 5.5MB    ← file actually in use (same slug directory)
#     ⇒ the only process is claimed by sid and dropped from path aggregation, so its cwd vanishes from live.
#       ee55ee55 has sid_alive=False (argv sid differs) + cwd not in live ⇒ a session working for 13 min shows **ended**.
# ★The test is **a relative comparison, not a time threshold**. Per this file's principle, silence never proves death
#   (see :505 — no lines are appended during a 5-minute command). "Stale after N hours" would break that principle.
#   Instead, if the same project directory has a **strictly newer .jsonl sibling**, the session moved to that file
#   and the argv sid is a stale label — same principle as the watcher-duplicate fix that day (a successor
#   displaces the old one). Control: pid 84637 `--resume b2c3d4e5` has its sid file 0.0 h old (= newest sibling),
#   so its claim stays alive, and the 2026-09-04 fix (binding --resume sessions launched from another directory
#   by sid) does not regress.
_sid_file = [0.0, {}]       # (measured at, sid -> that sid's transcript path or "")
_sid_stale = [0.0, {}]      # (measured at, sid -> is the claim stale)
SID_FILE_TTL = 60           # file locations rarely change — with a 2.5 s poll, don't scan every time
SID_STALE_TTL = 5           # the test compares sibling mtimes, so re-measure a bit more often


def _sid_transcript(sid):
    """Transcript path for sid ("" if none). ⚠Depth 1 only — `subagents/` below is out of scope."""
    now = time.time()
    if now - _sid_file[0] > SID_FILE_TTL:
        _sid_file[0], _sid_file[1] = now, {}
    c = _sid_file[1]
    if sid in c:
        return c[sid]
    hit, best = "", -1.0
    for root in claude_roots.projects_dirs(CLAUDE_PROJECTS):   # newest mtime across Claude roots
        for fp in glob.glob(os.path.join(root, "*", sid + ".jsonl")):
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            if mt > best:
                hit, best = fp, mt
    c[sid] = hit
    return hit


def _sid_claim_stale(sid, cwd=None):
    """Is the argv `--resume <sid>` claim stale? True means discard the claim.

    ★`cwd` is **the working directory of the process making the claim** (2026-09-08; a gone home session
      still showed). Sibling comparison alone misses **`/clear` after `--resume`** — the successor appears
      under **a different slug**. Measured:
        pid 41001 `claude --resume aa11aa11…` · cwd `/home/me/.mailbox-mcp`
        claimed file `-home-me/aa11aa11….jsonl` 13:32:42 (dead home session · newest in that directory)
        real successor `-home-me--mailbox-mcp/bb22bb22….jsonl` 13:37:46 (being written now)
      So the claim was judged valid and the two rows swapped places:
        ⓐ dead `aa11aa11` passed `sid_alive` and stayed "waiting for input" (even the watcher line attached to it)
        ⓑ live `bb22bb22`, written 1 s earlier, matched neither path nor sid and fell to "ended"
          (a claimed pid is removed from path aggregation, so its cwd is absent from `live`).
      ⇒ If the cwd slug has something **newer** than the claimed file, the label is stale.
    ⚠**Only "something newer" overturns a claim** (repeated failure pattern ②). The normal case at `:766`
      (`--resume` of a home session from repo-A) keeps writing on the live side, so the cwd slug has
      nothing newer — that case stays valid.
    ⚠The result depends on cwd, so **cwd is part of the cache key** (the same sid can be claimed from
      different cwds).

    ⚠On failure fall back to **False** (= trust the claim) — old behavior is the default, and the new lookup
      must not bring down all of `live_cwds()`."""
    try:
        now = time.time()
        if now - _sid_stale[0] > SID_STALE_TTL:
            _sid_stale[0], _sid_stale[1] = now, {}
        c = _sid_stale[1]
        ck = (sid, cwd or "")
        if ck in c:
            return c[ck]
        fp = _sid_transcript(sid)
        if not fp:
            c[ck] = True               # label points at a missing file — no basis to trust it
            return True
        mine = os.path.getmtime(fp)
        d = os.path.dirname(fp)
        dirs = [d]
        if cwd:
            cd = os.path.join(os.path.dirname(d), _slug(cwd))   # same Claude root as the claimed file
            if cd != d:
                dirs.append(cd)        # the process's own cwd slug — a `/clear` successor appears here
        stale = False
        for dd in dirs:
            try:
                fns = os.listdir(dd)
            except OSError:
                continue               # the cwd slug may not exist yet — absence is not evidence
            for fn in fns:
                if not fn.endswith(".jsonl") or os.path.join(dd, fn) == fp:
                    continue
                try:
                    if os.path.getmtime(os.path.join(dd, fn)) > mine:
                        stale = True   # a newer sibling exists = the session moved to that file
                        break
                except OSError:
                    continue
            if stale:
                break
        c[ck] = stale
        return stale
    except OSError:
        return False
    except Exception as e:
        warn_once("sidstale", "Session label staleness check failed ({err})", vars={"err": type(e).__name__}, soft=True)
        return False


def sid_alive(sid):
    """Is it **certainly** alive by session id? Unlike path matching, no chance of confusing sessions.

    ⚠Filled by `live_cwds()` — if that failed (unknown) or the session was started without `--resume`,
      this cannot tell and returns False. The existing path logic then answers as before (no regression).

    ★**Checks the evidence's age** (2026-09-07; audit "cause 2 — age hidden or lying").
      `_live_sids[0]` (measured-at) used to be **written in `live_cwds()` and read by no one.**
      So if `ps` kept being slow (4 s timeout) the last-seen sid set **froze in place** and a dead
      session stayed "waiting for input" forever (its old agent lines revived with it).
      Measured 2026-09-07: `_live_sids` = {b2c3d4e5}; pushing only the evidence time 3600 s back,
      `sid_alive('b2c3d4e5…')` still returned **True** ⇒ `_sess_state(no cwd, live={})` = `wait`.
      ⇒ Uses **the same cap** as its twin `live_cwds()` (`LIVE_STALE_S`=30 s) — a by-product of the same
        `ps` run, so no reason for a separate cap. The normal path refreshes every poll (2.5 s) and never
        hits 30 s (measured ps 28~31ms · lsof 18~19ms · identical over 3 runs).
      ⚠Hitting the cap does **not assert "ended"** — `sid_alive_stale()` below picks out "unknown" and
        `_sess_state` falls to `unknown`. Calling something present absent is the worse error."""
    return bool(sid) and sid in _live_sids[1] and time.time() - _live_sids[0] < LIVE_STALE_S


def sid_alive_stale(sid):
    """The id **was seen alive, but that evidence is stale** (= unknown, not dead).

    ★Separates `sid_alive()` returning False at the cap (`LIVE_STALE_S`) from `done`: True = "not measured", so
      the UI shows `unknown` and returns to the real state once `ps` succeeds on the next poll."""
    return bool(sid) and sid in _live_sids[1] and time.time() - _live_sids[0] >= LIVE_STALE_S


# ── Official session lookup ─────────────────────────────────────────────────
# ★★**Identity comes from an official lookup, not a guess** (2026-09-08; a documented way to check state).
#   `claude agents --json` gives, per pid, **the sessionId that process is writing now** (docs:
#   code.claude.com/docs/en/agent-view.md · "Print active sessions (interactive and background) as a JSON array and exit").
#   Measured 2.1.263 fields: `pid · cwd · kind · name · startedAt · sessionId · status`.
#   ⇒ Reading the argv `--resume <sid>` label and guessing whether it is stale **becomes unnecessary**:
#     pid 41001  argv `--resume aa11aa11` → official sessionId **bb22bb22** (the 2026-09-08 bug)
#     pid 57914 argv `--resume ff66ff66` → official sessionId **5c040e0b** (the documented trap)
#   ⚠**The old inference stays as the fallback** (some versions lack or fail this command); `None` = exactly as before.
#   ⚠Measured 0.16~0.43 s (`ps` 0.03 s) — cannot run every 2.5 s poll ⇒ TTL cache + dedicated lock (16 poll threads
#     must not spawn 16 processes) + last value on failure + background refresh.
#   ⚠`status` (`busy`/`idle`) is **not an activity signal** (measured: quiet 5 h, still `busy`) — only pid→sid is used.
#   ⚠`claude`'s shebang must find node ⇒ `bin_path` + `rich_env` (launchd PATH trap, 2026-08-24).
AGENTS_TTL = 8              # reuse a success — call once per three polls
AGENTS_STALE_S = 90         # on failure, keep the last success this long (same pattern as live_cwds' LIVE_STALE_S)
AGENTS_FAIL_TTL = 15        # ★failure (= unknown) cached this long: 6 calls in one poll fork once. ⚠Not the success TTL
                            #   (8 s): shorter re-incurs the 6 s timeout, longer freezes "unknown". 6x the 2.5 s poll.
AGENTS_TIMEOUT = 6
_av_cache = [0.0, None]     # (success time, {pid(str): entry}) — primary's state; with several accounts, the merged view
_av_fail = [0.0]            # last failure time (negative cache) — 0.0 means "no recent failure"
_av_lock = threading.Lock()
_av_held = {}               # account key ("" single, else realpath) -> last successful view; never cut (live._live_held)
# Each account's CLI lists only its own sessions (CLAUDE_CONFIG_DIR) ⇒ one lookup per account, merged by pid.
_av_acct = {}               # realpath(dir) -> ([ok_at, view], [fail_at]) per account when more than one is signed in
_av_unknown = set()         # account labels whose lookup is unknown as of the last agent_view() (primary = "")
# ★Re-run the CLI only when its answer could have changed (2026-10-13: the 8 s TTL spawned `claude agents --json`
#   every 11-18 s, 120-157MB RSS per child, per account). Signature = (file, pid, sessionId, cwd, pid alive) of the
#   registry `<config dir>/sessions/<pid>.json`; AGENTS_MAX_AGE is the safety refresh. ~7.5/min → ~1/min + events.
#   ⚠Never add `status`/`updatedAt` (they change every turn). No registry dir ⇒ None ⇒ plain AGENTS_TTL.
AGENTS_MAX_AGE = 60
_av_sigs = {}               # account key ("" = single account, else realpath) -> signature at the last success
_AV_BG = Refresher()            # background `claude agents --json` refresh, keyed per account


def _av_fallback(now, cache=None):
    """Value while the negative cache is valid — **same fallback as the failure branch** (last value if still fresh, else unknown)."""
    prev_at, prev = cache if cache is not None else _av_cache
    if prev is not None and now - prev_at < AGENTS_STALE_S:
        return prev
    return None


def _av_accounts():
    """[(label, dir, primary)] deduped by realpath, primary first; just the primary when the account list fails."""
    try:
        accs = claude_roots.accounts()
    except Exception:
        accs = []
    out, seen = [], set()
    for a in accs:
        rd = os.path.realpath(a.get("dir") or "")
        if rd in seen:
            continue
        seen.add(rd)
        out.append(("" if a.get("primary") else (a.get("label") or ""), a.get("dir") or "", bool(a.get("primary"))))
    return out or [("", "", True)]


def agent_view(ttl=None):
    """`claude agents --json` per account, merged → {pid(str): entry}. **None** only when every account is unknown.

    ★None = "could not ask" — the caller falls back to the old inference. `{}` = "no sessions running".
    ⚠Single account: one call with today's env and caches, unchanged.
    `ttl=None` = registry-signature mode (above); an explicit ttl is a plain TTL as before.
    """
    accs = _av_accounts()
    if len(accs) == 1:
        _av_unknown.clear()                     # one account: unknown is the None return itself
        env = rich_env()
        d = accs[0][1] or env.get("CLAUDE_CONFIG_DIR") or os.path.join(claude_roots.SCAN_HOME, ".claude")
        return _av_one(env, _av_cache, _av_fail, ttl, "agents", d, "")
    merged, unknown, any_ok = {}, set(), False
    deflt = os.path.realpath(os.path.join(claude_roots.SCAN_HOME, ".claude"))
    for label, d, prim in accs:
        env = rich_env()                        # primary: today's env as is
        if not prim:
            # ⚠CLAUDE_CONFIG_DIR=~/.claude moves .claude.json inside it (config.claude_json) — the default dir runs unset.
            if os.path.realpath(d) == deflt:
                env.pop("CLAUDE_CONFIG_DIR", None)
            else:
                env["CLAUDE_CONFIG_DIR"] = d
        cache, fail = _av_acct.setdefault(os.path.realpath(d), ([0.0, None], [0.0]))
        v = _av_one(env, cache, fail, ttl, "agents" if prim else None, d, os.path.realpath(d))
        if v is None:
            unknown.add(label)
            continue
        any_ok = True
        for pid, it in v.items():
            merged.setdefault(pid, it)
    _av_unknown.clear()
    _av_unknown.update(unknown)
    out = merged if any_ok else None
    _av_cache[0], _av_cache[1] = time.time(), out     # term.py reads the merged view from here
    return out


def agent_view_unknown():
    """Account labels whose official lookup is unknown as of the last `agent_view()` (primary = "").

    ⚠Filled only with several accounts — with one, a failed lookup is `agent_view() is None` and the set stays empty."""
    return set(_av_unknown)


def _av_one(env, cache, fail, ttl, skey, cfg_dir="", sig_key=None):
    """One account's lookup with its own TTL, last-good and negative cache. `skey` = stale-mark key, or None."""
    sig = _av_registry_sig(cfg_dir) if ttl is None else None

    def fresh(t):
        if cache[1] is None:
            return False
        if sig is not None:
            return _av_sigs.get(sig_key) == sig and t - cache[0] < AGENTS_MAX_AGE
        return t - cache[0] < (AGENTS_TTL if ttl is None else ttl)
    now = time.time()
    if fresh(now):
        return cache[1]
    # ★★Failures are cached too (2026-09-22): 6 callers per `state()` × 6 s timeout = 36 s cold response (measured
    #   38.5 s; 49 `TimeoutExpired` lines in `viewer.err`). ⇒ Within AGENTS_FAIL_TTL, no fork; same fallback as failure.
    if now - fail[0] < AGENTS_FAIL_TTL:
        return _av_fallback(now, cache)
    # ★At load 138-190 /api/state took 30-39 s waiting on lookups. ⇒ Serve the last value, refresh in the background.
    #   ⚠Cold start asks inline only off the request path (memo.request_path); there None (unknown) until it lands.
    if (cache[1] is not None and now - cache[0] < AGENTS_STALE_S) or on_request_path():
        _AV_BG.kick(sig_key or "", lambda: _av_fetch(env, cache, fail, skey, sig, sig_key, fresh))
        return _av_fallback(time.time(), cache)   # re-read: an inline spawn (tests) has just refreshed it
    return _av_fetch(env, cache, fail, skey, sig, sig_key, fresh)


def _av_fetch(env, cache, fail, skey, sig, sig_key, fresh):
    """Run `claude agents --json` once under `_av_lock` and store the result in `cache`/`fail` (see `_av_one`)."""
    with _av_lock:
        now = time.time()
        if fresh(now):
            return cache[1]              # another thread just filled it — don't spawn again
        if now - fail[0] < AGENTS_FAIL_TTL:
            return _av_fallback(now, cache)     # another thread just failed — don't spawn again
        prev_at, prev = cache
        try:
            r = subprocess.run([bin_path("claude"), "agents", "--json"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=AGENTS_TIMEOUT,
                               env=env)
            # ⚠rc != 0 with empty stdout would parse as [] = «no sessions» and end every open row; it is unknown.
            if r.returncode != 0:
                raise RuntimeError("exit %s" % r.returncode)
            arr = json.loads(r.stdout or "[]")
            if not isinstance(arr, list):
                raise ValueError("not an array")
            out = {}
            for it in arr:
                if isinstance(it, dict) and it.get("pid") is not None:
                    out[str(it["pid"])] = it
            cache[0], cache[1] = time.time(), out
            _av_sigs[sig_key] = sig      # taken before the spawn, so a change during it refreshes again
            fail[0] = 0.0                # recovered — lift the negative cache
            _av_held[sig_key or ""] = out
            if skey:
                _stale_clear(skey)
            return out
        except Exception as e:
            fail[0] = time.time()        # ★**both** failure branches pass here (negative-cache comment above)
            if isinstance(e, FileNotFoundError):
                # ⚠A missing binary is not slowness (it was logged as «slow (FileNotFoundError)»).
                #   Drop the cached path so the next call re-resolves it (a CLI update swaps the binary).
                bin_forget("claude")
                warn_once("agents-nobin", "claude executable not found — re-resolving its path")
                if prev is not None and time.time() - prev_at < AGENTS_STALE_S:
                    if skey:
                        _stale_mark(skey, prev_at)
                    return prev
                if skey:
                    _stale_clear(skey)
                cache[0], cache[1] = 0.0, None
                return None
            if prev is not None and time.time() - prev_at < AGENTS_STALE_S:
                if skey:
                    _stale_mark(skey, prev_at)     # ★surface staleness on screen (health strip) — fallback unchanged
                # just slow — use the last value and **do not refresh its time** (it expires if failures continue).
                # ★tier 1 (soft) — covered, so the screen was right and the user has no action.
                warn_once("agents-slow", "Official session lookup is slow ({err}) — using the last value for up to {n}s",
                          soft=True, vars={"err": type(e).__name__, "n": AGENTS_STALE_S}, more=_slow_why())
                return prev
            warn_once("agents", "Could not query official sessions (claude agents --json, {err})"
                      " — identity falls back to the old argv-label guess", vars={"err": type(e).__name__}, more=_slow_why())
            if skey:
                _stale_clear(skey)                 # no longer "last value" — it is unknown (a separate warning fires)
            cache[0], cache[1] = 0.0, None
            return None


# ★★**The full process list is taken once per poll** (2026-09-21). Each collector used to run its own `ps`,
#   up to 5 `ps` per poll — that is where the cumulative **70** `TimeoutExpired` in `viewer.err` came from, and
#   under high load (load 70.3 in the last warning) the 4 s-capped calls queued up, leaving screen values stale for up to 28 s.
#   ⇒ Only same-list calls are merged (`live_cwds` ×2 · `mailbox_watches` · `tool_busy`); parsing stays per collector.
#   ⚠Not merged: ① `ps -Ewwo …` (env `-E`) — a different command used for a few watcher processes only;
#     on the full list it would drag every environment along (see the ⚠ comment there). ② the 2 `lsof` calls — different pid sets and purposes.
#   ⚠Fields = the union the collectors use (`pid,ppid,pcpu,rss,command`; `command` last — it holds spaces). `comm=` dropped: the claude test gives the same answer
#     on argv[0] — measured 2026-09-21: of 626 processes, 4 by comm · 4 by argv[0], **0 difference**; `comm` values
#     contain spaces (measured `/Applications/…/Google Chrome Helper`), so one line with `command` breaks parsing.
PS_SNAP_TTL = 2.0              # shorter than the poll (2.5 s) — reused within a poll, retaken on the next
PS_SNAP_FAIL_TTL = 4.0         # ★failures cached this long — equal to the `ps` timeout (4 s). The 3 calls within
                               # a poll fork only once. ⚠Do not make it equal to the success TTL (2 s):
                               # then one poll could incur another 4 s call.
_ps_snap_cache = [0.0, None]   # (success time, [(pid, ppid, command), ...])
_ps_res = [0.0, {}]            # (success time, {pid: (pcpu, rss_kb)}) — raw strings for proc_load, same stamp as the cache
_ps_snap_fail = [0.0, None]    # (failure time, its exception) — the contract is "raise", so the exception is cached, not a value
_ps_snap_lock = threading.Lock()


def _ps_snap(ttl=PS_SNAP_TTL):
    """Full process list -> [(pid, ppid, command), ...].

    ⚠**On failure the exception is re-raised as is.** The "use the last value for N s" rule has a different
      cap per collector (LIVE_STALE_S 30 · MON_STALE_S 60 · BUSY_STALE_S 30), so it is not decided here —
      each caller's `except` takes its own fallback as before.

    ★**Failures are cached too** (2026-09-22). Previously failures were not cached, so the three callers (live_cwds ·
      mailbox_watches · tool_busy) each waited 4 s — the 47 `process lookup is slow (TimeoutExpired)`
      lines in `viewer.err` are exactly that (4 s × 3 = 12 s).
      ⇒ For PS_SNAP_FAIL_TTL, don't fork again; re-raise **the same exception immediately** (contract kept)."""
    if not IS_MAC:
        return []       # ⚠non-Mac — no `ps -Ao`. Empty list ⇒ callers go to "none" without exceptions
    if _ps_snap_cache[1] is not None and time.time() - _ps_snap_cache[0] < ttl:
        return _ps_snap_cache[1]
    if _ps_snap_fail[1] is not None and time.time() - _ps_snap_fail[0] < PS_SNAP_FAIL_TTL:
        raise _ps_snap_fail[1].with_traceback(None)   # clear the traceback (the same object keeps growing)
    if on_request_path():
        rows = serve_last("ps", lambda: _ps_snap(ttl), lambda: tuple(_ps_snap_cache), LIVE_STALE_S, time.time, warn_once)
        if rows is None:
            raise RuntimeError("process list not collected yet")   # unknown — each caller takes its own fallback
        return rows
    with _ps_snap_lock:
        if _ps_snap_cache[1] is not None and time.time() - _ps_snap_cache[0] < ttl:
            return _ps_snap_cache[1]      # another thread just took it — don't run again
        if _ps_snap_fail[1] is not None and time.time() - _ps_snap_fail[0] < PS_SNAP_FAIL_TTL:
            raise _ps_snap_fail[1].with_traceback(None)   # another thread just failed — don't run again
        try:
            # ⚠`errors="replace"` is required — encoding alone means strict, and one bad byte kills session detection entirely.
            txt = subprocess.run(["ps", "-Ao", "pid=,ppid=,pcpu=,rss=,command="],  # nosec B607 -- PATH lookup on purpose: the tool's location differs per OS
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=4).stdout
        except Exception as e:
            _ps_snap_fail[0], _ps_snap_fail[1] = time.time(), e
            raise
        _ps_snap_fail[0], _ps_snap_fail[1] = 0.0, None    # recovered — lift the negative cache
        rows, res = [], {}
        for ln in txt.splitlines():
            parts = ln.split(None, 4)
            if len(parts) < 5:
                continue
            rows.append((parts[0], parts[1], parts[4]))   # ⚠rows stay 3-tuples — ~10 callers unpack (pid, ppid, cmd)
            res[parts[0]] = (parts[2], parts[3])
        _ps_snap_cache[0], _ps_snap_cache[1] = time.time(), rows
        _ps_res[0], _ps_res[1] = _ps_snap_cache[0], res
        return rows


_busy_cache = (0.0, {})
_busy_shells = {}          # cwd -> shell-snapshot child pids seen by the last tool_busy probe (None = unknown)
_starts_cache = (0.0, (), None)
BLOCK_GRACE_S = 8          # no execution trace after this long ⇒ treat as "blocked" (to separate from just started)
BUSY_STALE_S = 30          # on lookup failure use the last success only this long (same value and reason as live_cwds' LIVE_STALE_S)


def tool_busy(ttl=2):
    """Session paths where **a Bash tool is actually running** now.

    ★Signal: Claude Code runs the Bash tool as a **child process** `zsh -c source ~/.claude/shell-snapshot…`.
      MCP servers are children too, but their command lines differ (measured 2026-08-26: claude 4665 →
      shell-snapshot 11583, claude 5006 → none).
    ★Why look at processes: the transcript **writes nothing while a permission prompt is showing.**
      Only after a denial does "The user doesn't want to proceed…" appear (measured 60 cases). So "tool running" and
      "awaiting approval" cannot be told apart from the transcript; **the existence of an executing process** does.
    ★When unknown, use the last value — asserting "nothing running" when the lookup was merely slow makes every
      healthy session look blocked (live_cwds hit the same trap).
    ★⚠**But that last value had no age cap** (2026-09-07; audit "cause 2": the old value was returned indefinitely on
      failure, while the twin `live_cwds()` caps at `LIVE_STALE_S`=30 and falls to unknown, and `_busy_cache[0]` held
      the measured-at time unused). If `ps` keeps failing, **the path set running at that moment stays "tool running"
      forever** — finished tools linger as ghosts, and conversely `_blocked()` **wrongly asserts** "awaiting approval"
      for sessions not in that set.
      Measured 2026-09-07: blocking `subprocess.run` with TimeoutExpired and aging `_busy_cache` 7200 s made
      `tool_busy()` return that 7200 s-old value (`{'/home/me/GHOST': True}`) as is.
      ⇒ Use the last value only up to `BUSY_STALE_S` (30 s); beyond that go to **None (unknown)**, not `{}`
        (nothing running). `_blocked()` reads None as "cannot tell" and adds no badge —
        the side that never calls present absent. Normal path measured ps 28ms · lsof 18ms, never hits it."""
    global _busy_cache, _busy_shells
    if not IS_MAC:
        return None     # ⚠no ps/lsof probe here — unknown, never {} (_blocked reads {} as «nothing running»)
    if time.time() - _busy_cache[0] < ttl:
        return _busy_cache[1]
    if on_request_path():
        return serve_last("busy", lambda: tool_busy(ttl), lambda: _busy_cache, BUSY_STALE_S, time.time, warn_once)
    out = {}
    try:
        claude, shells = set(), {}
        for pid, ppid, cmd in _ps_snap():   # ★once-per-poll full list (`_ps_snap` comment above)
            if is_claude_argv(cmd):
                claude.add(pid)
            elif "shell-snapshot" in cmd:
                shells.setdefault(ppid, []).append(pid)
        busy = [p for p in claude if p in shells]
        by_cwd = {}
        if not busy:
            _busy_cache, _busy_shells = (time.time(), {}), {}
            _stale_clear("busy")
            return {}
        r = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fpn", "-p", ",".join(busy[:64])],  # nosec B607 -- PATH lookup on purpose: the tool's location differs per OS
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=4).stdout
        cur = None
        for ln in r.splitlines():
            if ln.startswith("p"):
                cur = ln[1:].strip()
            elif ln.startswith("n") and cur:
                out[ln[1:].strip()] = True
                by_cwd.setdefault(ln[1:].strip(), []).extend(shells.get(cur, []))
        if not out:
            # ⚠Busy pids exist but lsof gave no cwd: a failed probe, not «nothing running» ({} would flag every Bash).
            raise RuntimeError("lsof returned no cwd")
    except Exception as e:
        prev_at, prev = _busy_cache
        if prev is not None and time.time() - prev_at < BUSY_STALE_S:
            # just slow — use the last value and **do not refresh its time** (it expires if failures continue)
            # ★tier 1 — `soft=True` for the same reason as `live-slow` above (covered ⇒ nothing to act on)
            warn_once("busy-slow", "Tool process lookup is slow ({err}) — using the last value for up to {n}s",
                      soft=True, vars={"err": type(e).__name__, "n": BUSY_STALE_S}, more=_slow_why())
            _stale_mark("busy", prev_at)       # ★surface staleness on screen (health strip) — fallback rule unchanged
            return prev
        warn_once("busy", "Could not read tool processes ({err}) — 'running a tool' falls back to 'unknown'",
                  vars={"err": type(e).__name__})
        _stale_clear("busy")                   # no longer "last value" — it is unknown
        _busy_cache, _busy_shells = (time.time(), None), None
        return None
    _busy_cache, _busy_shells = (time.time(), out), by_cwd
    _stale_clear("busy")
    return out


def _etime_s(v):
    """ps `etime` ([[dd-]hh:]mm:ss) -> seconds, or None."""
    d, _, hms = v.strip().rpartition("-")
    try:
        h, m, s = ([0, 0] + [int(x) for x in hms.split(":")])[-3:] if hms.count(":") <= 2 else (None,) * 3
        return int(d or 0) * 86400 + h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return None


def shell_starts(ttl=2):
    """{cwd: [start epoch of each shell-snapshot child]} from the last tool_busy probe via one `ps -o etime`, or None = unknown."""
    global _starts_cache
    shells = _busy_shells
    if not IS_MAC or not isinstance(shells, dict):
        return None
    pids = tuple(sorted({p for v in shells.values() for p in v}))
    at, key, res = _starts_cache
    if key == pids and time.time() - at < ttl:
        return res
    if on_request_path():
        return serve_last("starts", lambda: shell_starts(ttl),
                          lambda: (_starts_cache[0], _starts_cache[2]) if _starts_cache[1] == pids else (0.0, None),
                          BUSY_STALE_S, time.time, warn_once)
    try:
        txt = subprocess.run(["ps", "-o", "pid=,etime=", "-p", ",".join(pids[:64])],  # nosec B607 -- PATH lookup on purpose: the tool's location differs per OS
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=4).stdout
        now, rows = time.time(), [ln.split() for ln in txt.splitlines()]
        start = {r[0]: now - _etime_s(r[1]) for r in rows if len(r) == 2 and _etime_s(r[1]) is not None}
        res = {cwd: [start[p] for p in v if p in start] for cwd, v in shells.items()}
    except Exception:
        res = None
    _starts_cache = (time.time(), pids, res)
    return res


def shell_after(cwd, t):
    """False only when every shell in cwd provably started before t (shells predating a tool call are not that call)."""
    starts = shell_starts()
    return not isinstance(starts, dict) or cwd not in starts or any(s >= t - 2 for s in starts[cwd])


# ★Instant tools — once approved they finish within 1 s. So if one hangs long, it is **waiting**.
#   MCP tools can legitimately take long (browser actions etc.), so they are excluded — when unsure, don't assert.
_FAST_TOOLS = {"Edit", "Write", "NotebookEdit", "Read", "Glob", "Grep", "TodoWrite"}


# The «Attention» check follows the permission mode: transcripts carry `permissionMode` on user entries (measured: 67 in one live transcript; latest wins).
#   These modes never show a human prompt (auto/dontAsk may deny, but never wait) ⇒ no «Awaiting approval».
_NO_PROMPT_MODES = {"bypassPermissions", "auto", "dontAsk"}
# ⚠A missing `permissionMode` ("") is read as prompting on purpose: an unproven mode keeps a possible approval request visible.
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}     # acceptEdits auto-approves these only


def _blocked(state, tool, age, cwd, nbg, pmode=""):
    """Blocked? -> reason string, else "" (rationale in the row comment above)."""
    if state != "tool" or age < BLOCK_GRACE_S or not tool or pmode in _NO_PROMPT_MODES:
        return ""
    base = tool.split("__")[-1] if tool.startswith("mcp__") else tool
    if tool.startswith("mcp__"):
        return ""                       # taking long may be normal — don't assert
    if pmode == "acceptEdits" and base in _EDIT_TOOLS:
        return ""
    if base in _FAST_TOOLS:
        return f"{base} waiting for approval"
    if base == "Bash":
        if nbg:
            return ""                   # a background command holds a process, so it cannot be told apart
        busy = tool_busy()
        # ⚠A shell older than the tool call (Monitor loop, dev server) is not the pending Bash; 2 s = etime rounding.
        if busy is not None and (cwd not in busy or not shell_after(cwd, time.time() - age)):   # {} = nothing running; None = unknown
            return "Bash waiting for approval"
    return ""
