"""Live session detection: live_cwds, mailbox watchers, parse cache.
Probes (staleness, sid lookups, official session list, ps snapshot, tool-busy) live in `sidereus/live_probe.py`;
context-window learning in `sidereus/live_win.py`."""
import os
import re
import subprocess
import threading
import time
from sidereus.config import IS_MAC
from sidereus import claude_roots
from sidereus.warn import warn_once
from sidereus.memo import BoundedMemo
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _slug
# ⚠Probes (staleness, sid lookups, agent_view, _ps_snap, tool_busy/_blocked) live in sidereus/live_probe.py; re-exported here
#   for importers (sessions, cards, notes, work, history) and for live_cwds/watchers. Patch probe internals on live_probe.
from sidereus.live_probe import (LIVE_STALE_S, _STALE_LABEL, _STALE_SHOW_S, _UUID_RE, _blocked, _live_pid_cwd,
    _live_sids, _ps_snap, _sid_claim_stale, _sid_transcript, _slow_why, _stale, _stale_clear, _stale_lock,
    _stale_mark, agent_view, sid_alive, sid_alive_stale)
# ⚠Window learning lives in sidereus/live_win.py (re-exported for chat_server/sessions/recent). Patch its state there.
from sidereus.live_win import _ctx_window, _model_win, _win_ev, _win_load, _win_loop  # noqa: F401


# ★Liveness is decided by **process** — mtime does not work (2026-08-18).
#   Why: while a session runs a 5-minute command no lines are appended ⇒ it shows **grey while working**.
#   Conversely a session that just replied and waits for input shows **green** because of the fresh write.
#   ⇒ Alive = cwd of a `claude` process; "running right now" = shape of the last event.
_live_cache = (0.0, set())


def live_cwds(ttl=2):
    """Working directories of running claude processes -> **process count per path**. None if unreadable (unknown vs none).

    ★Why a count, not a set (measured 2026-08-24): with two or more transcripts in one path, the set test
      treated **all of them as alive** if the path had any process. So a dead shell (a one-line
      `bridge-session`) stayed listed as "waiting for input" instead of "ended". With a count,
      `sessions()` can mark only the newest N alive, and multiple sessions in one path don't break.
      `in` on a dict behaves like a set, so existing callers such as `_sess_state` work unchanged.

    ★Measured 2026-08-19: on a busy machine `ps` exceeded 2 s with `TimeoutExpired`. By the original design that
      falls to None (unknown), which makes **every session "unknown" at once** — the whole screen turns grey and
      reads as "did all sessions die". The processes had not gone; **the lookup was just slow**.
      ⇒ On failure, first reuse **the last good value** for up to 30 s; only older than that go to unknown.
      The timeout was also widened 2 s → 4 s (normal path measured ~100ms, so no impact)."""
    global _live_cache
    if time.time() - _live_cache[0] < ttl:
        return _live_cache[1]
    prev_at, prev = _live_cache
    out = {}
    try:
        snap = _ps_snap()
        pids = _live_claude_pids(snap)
        if not pids:
            _live_sids[0], _live_sids[1] = time.time(), set()
            _live_cache = (time.time(), out)
            _stale_clear("live")
            return out
        pmap = _live_pid_cwds(pids)
        sids, claimed = set(), set()
        av = _live_official(sids, claimed)
        _live_argv_claims(snap, pids, av, pmap, sids, claimed)
        _live_sids[0], _live_sids[1] = time.time(), sids
        _live_count_paths(pmap, claimed, out)
    except Exception as e:
        return _live_fail(e, prev_at, prev)
    _live_cache = (time.time(), out)
    _stale_clear("live")
    return out


def _live_claude_pids(snap):
    # ★Uses the once-per-poll full list (`_ps_snap` comment above). The test is still "is argv[0]'s basename
    #   claude" — measured 0 difference from the old `comm` test (2026-09-21).
    return [pid for pid, _pp, cmd in snap
            if cmd.split() and os.path.basename(cmd.split()[0]) == "claude"]


# ⚠A claude CLI's cwd is fixed at launch, so cwd is cached per pid and lsof runs only for new pids
#   (a 2 s TTL under the 2.5 s poll re-ran lsof every poll, 17-21ms each). The 60 s full re-check only guards pid reuse.
PID_CWD_TTL = 60.0


def _live_pid_cwds(pids):
    """One lsof call -> {pid: cwd}; also publishes it as `_live_pid_cwd`."""
    # ★★**Bind directly by session id** (2026-09-04; a repo-A session running a shell script was not detected).
    #   Path-only matching broke on `--resume`:
    #     measured PID 41002 `claude --resume aa11aa11…` has cwd `~/work/repo-A`, but
    #     its transcript lives under the slug at start time, `-Users-me`. So
    #       ⓐ that process's slot went to repo-A's **newest transcript (already dead d0e1f2a3)**,
    #         leaving a dead session "waiting for input", and
    #       ⓑ the session actually alive and running Bash had no process under `~` and was headed for "ended".
    #   The session id is right there in argv; using it removes both symptoms.
    #   ⚠**Processes bound by id are removed from path aggregation** — otherwise their path slot remains and a dead
    #     shell takes it again (ⓐ recurs as is).
    # ★lsof is called **once** (it used to be per PID — N times as sessions grow).
    #   Measured 2026-08-18: 100ms at 5 sessions → would be 800ms at 40. The poll is 2.5 s.
    # ★★Called **before the sid check** (2026-09-08). Whether an argv label is stale needs that process's **cwd**
    #   (the 41001 case in the `_sid_claim_stale` comment) ⇒ build pid→cwd first.
    #   ⚠Still one call (measured lsof 18~19ms). It used to pass only non-claimed pids,
    #     so the cwd was missing exactly for the pids that needed it (= those claiming a label).
    #   ⇒ The by-product `_live_pid_cwd` now holds **all** claude processes (`mailbox_watches()` learns
    #     the cwd of `--resume` sessions too, not just bare `claude` — nothing gets worse).
    # ⚠live_cwds' TTL only caches successes — a later step raising re-ran lsof every call; reuse a fresh covering map.
    want, m = pids[:64], _live_pid_cwd[1]
    missing = [p for p in want if p not in m]
    if not missing:
        if time.time() - _live_pid_cwd[0] < PID_CWD_TTL:
            return {p: m[p] for p in pids if p in m}   # ⚠only the requested pids — callers aggregate every key
        missing = want                                 # safety re-check of every pid
    elif len(missing) < len(want) and time.time() - _live_pid_cwd[0] >= PID_CWD_TTL:
        missing = want
    r = subprocess.run(["lsof", "-a", "-d", "cwd", "-Fpn", "-p", ",".join(missing)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=4).stdout if IS_MAC else ""   # ⚠non-Mac — cwd unavailable (empty result)
    pmap, cur = {}, None
    for ln in r.splitlines():
        if ln.startswith("p"):
            cur = ln[1:].strip()
        elif ln.startswith("n"):
            if cur:
                pmap[cur] = ln[1:].strip()
    if len(missing) < len(want):       # partial lookup: keep cached live pids (dead ones drop), keep the re-check clock
        keep = {p: m[p] for p in want if p in m}
        keep.update(pmap)
        _live_pid_cwd[1] = keep
        return {p: keep[p] for p in pids if p in keep}
    _live_pid_cwd[0], _live_pid_cwd[1] = time.time(), pmap
    return pmap


def _live_official(sids, claimed):
    """Official pid -> sessionId lookup; fills sids/claimed in place and returns the raw view."""
    # ★★**The official lookup comes first** (`agent_view` comment above). The harness states pid → "sessionId
    #   in use now", so there is no need to read argv labels and guess staleness.
    #   ⚠A sid with no transcript yet is **not added to claimed** — removing that pid from path aggregation
    #     leaves no row to attach to and a just-started session vanishes (calling present absent is worse).
    av = agent_view()
    for _pid, _it in (av or {}).items():
        _sid = (_it.get("sessionId") or "") if isinstance(_it, dict) else ""
        if not _sid:
            continue
        sids.add(_sid)
        if _sid_transcript(_sid):
            claimed.add(_pid)
    return av


def _live_argv_claims(snap, pids, av, pmap, sids, claimed):
    """argv `--resume <sid>` labels for pids without an official answer; fills sids/claimed in place."""
    try:
        # ★This used to run `ps -o pid=,command= -p …` once more — it fetched the same list again,
        #   so now **only that pid set is filtered from the snapshot above** (cap of 64 unchanged).
        _want = set(pids[:64])
        # ★Official processes' argv (2026-09-24, repo-S): backgrounding a session forks it —
        #   official pid 41003 runs `--session-id dd44dd44 --fork-session --resume …/cc33cc33….jsonl` while the
        #   original terminal pid 41004`claude --resume cc33cc33` stays alive but is **not** in the official list.
        #   Its stale label left it in path aggregation, so the old transcript took the path slot and showed
        #   «Awaiting input» next to its successor (selfcheck: «alive on screen but not in the official list: cc33cc33»).
        #   ⇒ If an official session's argv names this label sid, that session **is** its successor: claim the pid
        #     (no path slot, no sid). ⚠Only argv lineage, not «same cwd» — an unlisted real session in the same
        #     path (the 41005 case below) must keep its slot.
        _off_cmd = [(_c, av[_p].get("sessionId") or "")
                    for _p, _pp, _c in snap if av and isinstance(av.get(_p), dict)]   # junk entries skipped
        for parts in ((_p, _cmd) for _p, _pp, _cmd in snap if _p in _want):
            if av is not None and parts[0] in av:
                continue           # pid with an official answer — no argv guess on top
            m = _UUID_RE.search(parts[1])
            if m:
                sid = m.group(0)
                if any(sid in _c and _s and _s != sid for _c, _s in _off_cmd):
                    claimed.add(parts[0])     # superseded by an official fork (comment above)
                    continue
                if _sid_claim_stale(sid, pmap.get(parts[0])):
                    # ★stale label (the ff66ff66 · 41001 cases in the _sid_claim_stale comment above).
                    #   Put in neither sids nor claimed ⇒ the pid stays in path aggregation,
                    #   its cwd comes alive in live, and the transcript actually in use does not go to ended.
                    continue
                sids.add(sid)
                claimed.add(parts[0])
    except Exception as e:         # if this fails, judge by the old path method only — nothing gets worse
        warn_once("argvclaim", "argv session label parse failed ({err})", vars={"err": type(e).__name__}, soft=True)


def _live_count_paths(pmap, claimed, out):
    # ★pids bound by id are removed from path aggregation (⚠ above). Several sessions can share a path, so count.
    for pid, cwd in pmap.items():
        if pid in claimed:
            continue
        out[cwd] = out.get(cwd, 0) + 1


def _live_fail(e, prev_at, prev):
    """Lookup failed: reuse a fresh last value, else publish None (unknown)."""
    global _live_cache
    if prev is not None and time.time() - prev_at < LIVE_STALE_S:
        # just slow — reuse the last value and **do not refresh its time** (it expires if failures continue)
        # ★tier 1 — covered, so the screen was right and the user has no action. `soft=True` only counts;
        #   it reaches the strip only after `SOFT_PROMOTE_N` repeats (rationale in the constants comment above `warn_once`).
        warn_once("live-slow", "Process lookup is slow ({err}) — using the last value for up to {n}s",
                  soft=True, vars={"err": type(e).__name__, "n": LIVE_STALE_S}, more=_slow_why())
        _stale_mark("live", prev_at)       # ★surface staleness on screen (health strip) — fallback rule unchanged
        return prev
    warn_once("live", "Could not read process state ({err}) — activity falls back to 'unknown'",
              vars={"err": type(e).__name__}, more=_slow_why())
    _stale_clear("live")                   # no longer "last value" — it is unknown
    _live_cache = (time.time(), None)
    return None


# ★★**Mailbox watchers are judged by process, not heartbeat** (measured 2026-09-07).
#   Why: the screen's watcher lines were built from transcript `<task-notification>` heartbeats (the `alive`
#   branch of `_running_bg_locked`), and **that evidence source died.** All 7 watchers the screen received were silent 70~73 h:
#     ee55ee55 72.8h/71.3h/70.6h/70.6h · aa11aa11 71.3h · a1b2c3d4 70.7h · b2c3d4e5 71.1h
#   Yet **3** watcher processes were actually running. Since watch.sh was consolidated, harness Monitor events
#   never arrive ⇒ **live and dead are equally silent.** Heartbeats cannot support any judgment
#   (time expiry, relative comparison, same-label displacement are all powerless — all three fixes failed).
#   ⇒ The usable evidence is **the process chain**, which links cleanly in measurement:
#     monitor_stream 55298 <- zsh 55295 <- claude 84637 (--resume b2c3d4e5)
#     monitor_stream 80771 <- zsh 80767 <- claude 64859 (bare claude · cwd=~/work/repo-A)
#     monitor_stream 86650 <- zsh 86647 <- claude 57914 (--resume ff66ff66, but the real file is ee55ee55)
#   `watch.sh` is a child of the session shell (Bash tool), so two `ppid` hops up give the session process.
#   Identity is read from env `MAILBOX_ME` (measured: advocate · repo-A · agent-A).
#   ⚠No `pgrep -x` and the like — this file's history has missed processes that way. Use the full `ps` list.
WATCH_PROC = "monitor_stream.py"   # watcher process marker (last line of watch.sh: `exec python3 …/monitor_stream.py`)
MON_TTL = 5                        # reuse a success this long (poll is 2.5 s — don't run the full ps every poll)
MON_STALE_S = 60                   # on failure, use the last success this long (same pattern as live_cwds' LIVE_STALE_S)
_mon_cache = [0.0, None]           # (success time, {transcript path: [[label, start time, "proc"], ...]})
_MBOX_ME_RE = re.compile(r"MAILBOX_ME=(\S+)")
# marker to pick **mailbox watchers** out of old heartbeat entries (only those are discarded as fossils)
_MBOX_LAB_RE = re.compile(r"mailbox|메일박스|watch\.sh", re.I)


def _is_watch_cmd(cmd):
    """Is this command line **a real watcher process**?

    ⚠Substring match is not enough (measured 2026-09-07 · hit during this very fix): the moment a shell ran
      `pgrep -f monitor_stream`, that `zsh -c …` process was taken as a watcher and
      **a nonexistent watcher appeared on its own session row** (no MAILBOX_ME · uptime 0 min).
      ⇒ A watcher needs argv[0] to be python and one argument ending in `monitor_stream.py`.
        Shell wrappers have argv[0] `/bin/zsh` and are filtered here."""
    parts = (cmd or "").split()
    if not parts:
        return False
    if not os.path.basename(parts[0]).lower().startswith("python"):
        return False
    return any(x.endswith(WATCH_PROC) for x in parts[1:])


def _etime_ts(et, now):
    """`ps -o etime=` value (`02-23:20:52` · `23:20:52` · `20:52` · `52`) -> **start time**.
    0 if unreadable — the caller falls back to now (never invent an unknown value)."""
    try:
        et = (et or "").strip()
        if not et:
            return 0
        days = 0
        if "-" in et:
            d0, et = et.split("-", 1)
            days = int(d0)
        parts = [int(x) for x in et.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        return now - (days * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2])
    except (TypeError, ValueError, AttributeError):
        return 0                # unparsable etime: caller falls back to now


def _newest_jsonl(d):
    """**Newest .jsonl** in that project directory ("" if none). ⚠Depth 1 only (`subagents/` is out of scope)."""
    best, best_mt = "", 0
    try:
        for fn in os.listdir(d):
            if not fn.endswith(".jsonl"):
                continue
            fp = os.path.join(d, fn)
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            if mt > best_mt:
                best, best_mt = fp, mt
    except OSError:
        return ""
    return best


def _newest_slug(cwd):
    """Newest .jsonl of cwd's slug across every Claude root ("" if none). ⚠Same cwd in two roots: newest wins."""
    best, best_mt = "", -1.0
    for root in claude_roots.projects_dirs(CLAUDE_PROJECTS):
        f = _newest_jsonl(os.path.join(root, _slug(cwd)))
        try:
            mt = os.path.getmtime(f) if f else -1.0
        except OSError:
            continue
        if mt > best_mt:
            best, best_mt = f, mt
    return best


def _watch_transcript(cmd, pid):
    """The watcher's ancestor `claude` process -> that session's **transcript path** ("" if not found).

    ★A `--resume <sid>` claim can be stale — judged by the existing `_sid_claim_stale()` (rationale there);
      if stale, resolve to **the newest .jsonl in the directory** of that sid file (measured: pid 57914 is
      `--resume ff66ff66`, but the file in use is ee55ee55 in the same directory).
    ★Without a sid in argv (bare `claude`) go by **cwd**. cwd comes from the by-product `live_cwds()` left
      from its single lsof — no new lsof here.
    ★★**A stale label's successor may live in another directory** (2026-09-08 · the 41001 case in `_sid_claim_stale`).
      After `/clear` following `--resume` the successor appears under **the cwd slug**, so looking only at the
      sid's directory **attaches the watcher to a dead session** — that row is "ended", `_session_row` clears
      mon, and **the running watcher vanishes from the screen** (measured: one Sidereus watcher was on no row).
      ⇒ Use **the newer of the two directories** (the ff66ff66 case has both in one directory and still matches)."""
    cwd = _live_pid_cwd[1].get(pid) or ""
    # ★If the official lookup knows this pid's sessionId, that is authoritative (ahead of argv label guesses).
    _it = (agent_view() or {}).get(str(pid)) or {}
    _sid0 = _it.get("sessionId") or ""
    if _sid0:
        _fp0 = _sid_transcript(_sid0)
        if _fp0:
            return _fp0
    m = _UUID_RE.search(cmd or "")
    if m:
        sid = m.group(0)
        fp = _sid_transcript(sid)
        if fp and not _sid_claim_stale(sid, cwd):
            return fp
        if fp:
            cands = [_newest_jsonl(os.path.dirname(fp))]
            if cwd:
                cands.append(_newest_jsonl(os.path.join(os.path.dirname(os.path.dirname(fp)), _slug(cwd))))
            best, best_mt = "", -1.0
            for f in cands:
                if not f:
                    continue
                try:
                    mt = os.path.getmtime(f)
                except OSError:
                    continue
                if mt > best_mt:
                    best, best_mt = f, mt
            if best:
                return best
    if cwd:
        return _newest_slug(cwd)
    return ""


def mailbox_watches():
    """Currently running **mailbox watchers** -> {transcript path: [[label, start time, "proc"], ...]}.
    None if lookups keep failing — the caller falls back to the old heartbeat list.

    ★Principle unchanged: **calling present absent is the worse error.** So a failure does not drop to 0 entries;
      the last success is used up to MON_STALE_S, and only longer failures return None with a warning."""
    now = time.time()
    if _mon_cache[1] is not None and now - _mon_cache[0] < MON_TTL:
        return _mon_cache[1]
    try:
        live_cwds()          # fills the pid -> cwd by-product (its own 2 s TTL cache, so not an extra call)
        par, cmdl, watch = {}, {}, []
        for pid, ppid, cmd in _ps_snap():   # ★once-per-poll full list (`_ps_snap` comment above)
            par[pid] = ppid
            cmdl[pid] = cmd
            if _is_watch_cmd(cmd):
                watch.append(pid)
        out = {}
        if not watch:
            _mon_cache[0], _mon_cache[1] = time.time(), out
            _stale_clear("mon")
            return out
        # Read identity (MAILBOX_ME) and uptime **in one go** — `-E` appends env vars after the command line.
        # ⚠Only for the watcher processes (measured 3). The whole environment comes along, so never use it for the full list.
        who = {}
        try:
            env = subprocess.run(["ps", "-Ewwo", "pid=,etime=,command=", "-p", ",".join(watch[:32])],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace",
                                 timeout=4).stdout if IS_MAC else ""   # ⚠non-Mac — identity/uptime left empty
            cur, buf = None, []
            def _flush(cur, buf):
                if not cur:
                    return
                txt = " ".join(buf)
                mm = _MBOX_ME_RE.search(txt)
                who[cur] = (mm.group(1) if mm else "", _etime_ts(txt.split(None, 1)[0] if txt else "", now))
            for ln in env.splitlines():
                p0 = ln.split(None, 1)
                if p0 and p0[0] in par and p0[0] in watch:
                    _flush(cur, buf)
                    cur, buf = p0[0], [p0[1] if len(p0) > 1 else ""]
                elif cur:
                    buf.append(ln)
            _flush(cur, buf)
        except Exception:
            pass                 # even without identity/uptime the watcher itself is shown (nothing gets worse)
        for wp in watch:
            # walk up the parent chain to the session process (max 5 hops — no infinite loop)
            cp, p = "", wp
            for _ in range(5):
                p = par.get(p) or ""
                if not p or p in ("0", "1"):
                    break
                c0 = cmdl.get(p) or ""
                if c0 and os.path.basename(c0.split()[0]) == "claude":
                    cp = p
                    break
            if not cp:
                continue
            fp = _watch_transcript(cmdl.get(cp) or "", cp)
            if not fp:
                continue
            me, at = who.get(wp) or ("", 0)
            lab = "Mailbox watch · " + me if me else "Mailbox watch"
            out.setdefault(fp, []).append([lab, at or now, "proc"])
        _mon_cache[0], _mon_cache[1] = time.time(), out
        _stale_clear("mon")
        return out
    except Exception as e:
        if _mon_cache[1] is not None and now - _mon_cache[0] < MON_STALE_S:
            # just slow — use the last value and **do not refresh its time** (it expires if failures continue)
            # ★tier 1 — `soft=True` for the same reason as `live-slow` above (covered ⇒ nothing to act on)
            warn_once("mon-slow", "Watch process lookup is slow ({err}) — using the last value for up to {n}s",
                      soft=True, vars={"err": type(e).__name__, "n": MON_STALE_S}, more=_slow_why())
            _stale_mark("mon", _mon_cache[0])   # ★surface staleness on screen (health strip) — fallback rule unchanged
            return _mon_cache[1]
        warn_once("mon", "Could not read watch processes ({err}) — watch rows fall back to old heartbeats",
                  vars={"err": type(e).__name__})
        _stale_clear("mon")                     # no longer "last value" — it is unknown
        return None


# ★Parse cache — key is (path, mtime). An idle session's file does not change, so it is **not reread.**
#   Previously each poll tailed 200KB per session (14 sessions = 2.8MB / 2.5 s). That hurts first as sessions grow.
_parse_cache = BoundedMemo(200)
# ★Dedicated lock. If cap trimming overlaps another request thread's lookup, `dict changed size during iteration`
#   empties that poll's whole session list — preventing that is this lock's only job.
#   ⚠Correction 2026-09-07: this used to say "`state()` calls `sessions()` holding `_lock`, so sharing that lock
#     would deadlock". `state()` now calls `sessions()` **outside the lock** (AUDIT cause 4). It still must be
#     a dedicated lock — `_lock` guards the invite (write) path, and pulling it in here would hang parsing on the write path again.
_parse_lock = threading.Lock()
