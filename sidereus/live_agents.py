"""Official session list: `claude agents --json` per account (pid -> sessionId), cached with a negative cache and
a background refresh. Split out of `sidereus/live_probe.py`; owns every `_av_*`/`AGENTS_*` name — patch them here."""
import json
import os
import subprocess
import threading
import time
from sidereus.memo import Refresher, on_request_path
from sidereus import claude_roots
from sidereus.claude_roots import registry_sig as _av_registry_sig
from sidereus.warn import warn_once
from sidereus.ident import bin_path, bin_forget, rich_env
from sidereus.live_probe import _slow_why, _stale_clear, _stale_mark


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


def _av_signed_in(d):
    return os.path.isfile(os.path.join(d, ".claude.json"))     # CLAUDE_CONFIG_DIR=d keeps .claude.json in d


def _av_accounts():
    """[(label, dir, primary)] deduped by realpath, primary first; just the primary when the account list fails."""
    try:
        accs = claude_roots.accounts()
    except Exception:
        accs = []
    out, seen = [], set()
    deflt = os.path.realpath(os.path.join(claude_roots.SCAN_HOME, ".claude"))   # runs unset: ~/.claude.json is outside
    for a in accs:
        rd = os.path.realpath(a.get("dir") or "")
        # ⚠No .claude.json = the CLI never ran there (nothing to list), and asking would create it + backups/.
        if rd in seen or (not a.get("primary") and rd != deflt and not _av_signed_in(rd)):
            continue
        seen.add(rd)
        out.append(("" if a.get("primary") else (a.get("label") or ""), a.get("dir") or "", bool(a.get("primary"))))
    return out or [("", "", True)]


def agent_view(ttl=None):
    """`claude agents --json` per account, merged → {pid(str): entry}. **None** only when every account is unknown.

    ★None = "could not ask" — the caller falls back to the old inference. `{}` = "no sessions running".
    ⚠Single account: one call with today's env and caches, unchanged. `ttl=None` = registry-signature mode (above); an explicit ttl is a plain TTL as before.
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
                               timeout=AGENTS_TIMEOUT, env=env)
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
