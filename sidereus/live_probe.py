"""Live probes: collector staleness, sid -> transcript lookups, the once-per-poll process snapshot, tool-busy and
the blocked badge. Split out of `sidereus/live.py` (2026-09-24); live.py re-exports these names, so importers are
unchanged. The official session list (`claude agents --json`) is `sidereus/live_agents.py`. Owns `_busy_cache`."""
import glob
import os
import re
import subprocess
import threading
import time
from sidereus.config import IS_MAC
from sidereus.memo import on_request_path, serve_last
from sidereus import claude_roots
from sidereus.warn import warn_once
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _slug, is_claude_argv

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
#                             ⚠Without it a collector "never called again" (tool_busy is called conditionally) stays stale forever.


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
PS_SNAP_FAIL_TTL = 4.0         # ★failures cached this long — equal to the `ps` timeout (4 s). The 3 calls within a poll
                               # fork only once. ⚠Do not make it equal to the success TTL (2 s): then one poll could incur another 4 s call.
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
