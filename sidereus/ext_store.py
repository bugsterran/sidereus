"""External CLI session store: platform registry, hook-event ingest, persistence (ext-sessions.json,
ext-runs.json, ext-hooktok.json), child runs, liveness (pid/silence) and the per-session token store.
Views over it (rows, work panel, children, today usage, hook check) live in sidereus/ext.py, which re-exports
the names other modules import from `sidereus.ext`.
⚠Owns EXT_FILE/EXT_RUNS_FILE/EXT_HOOKTOK_FILE and every writer of them - tests/_load.py redirects them on this module."""
import json
import os
import socket
import subprocess
import threading
import time
from sidereus.config import DATA_DIR, pid_alive
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus import plat_codex, plat_gemini, plat_copilot
from sidereus.adapter import adapter_register


# ── external CLI agent sessions (Gemini CLI · Codex CLI) ─────────────────────
# ★Their hooks push events into `/api/hook` — we cannot read those sessions' transcripts or processes,
#   so **the last event is the only evidence**. States use the same vocabulary as the Claude side (`rank` sorts them together).
EXT_FILE = os.path.join(DATA_DIR, "ext-sessions.json")   # ⚠`HOME` here is the data dir (`DATA_DIR`, default `~/.mailbox-mcp`, :42), not the user's home
EXT_TTL_S = 24 * 3600        # delete if no news for this long — the only exit for pid-less sessions that never sent `SessionEnd`
# ★Killed CLIs (Ctrl-C twice, closed terminal, watchdog) send no SessionEnd. Evidence, in order:
#   the CLI pid from the hook (`os.kill(pid, 0)` + start time against pid reuse), else silence while busy.
# ★EXT_SILENT_S from data (2026-09-24): Gemini busy gaps n=93 p99 152s max 152s; Claude tool calls as a
#   proxy for long tools (7 days, n=18666, no Agent) p99 326s, p99.5 984s, >1200s 0.24%. 20 min sits above both.
EXT_SILENT_S = 1200
EXT_GONE_GRACE_S = 600       # «Disconnected» shown this long, then dropped like a SessionEnd
EXT_PID_EVERY_S = 30         # liveness check interval per session
EXT_PLAT = {"gemini": "gm", "codex": "cx", "copilot": "cp", "cursor": "cu", "cline": "cl",
            "windsurf": "wf", "warp": "wp", "trae": "tr", "zed": "zd", "grok": "gk",
            "deepseek": "ds", "qwen": "qw", "kimi": "ki", "mistral": "mi", "ollama": "ol",
            "perplexity": "px", "huggingface": "hf", "meta": "ma", "openrouter": "or"}
# hook `platform` value → row `plat` key (same key as the logo `AILG`).
# ⚠Do not put Claude here - it is already loaded from transcripts, so the same `sid` would become two rows and `_sid_proj` would be overwritten.

# Platforms whose record files are read by an `sidereus/plat_<name>.py` adapter (contract: sidereus/adapter.py).
# ⚠Order is output order (timeline rows, history blocks): Gemini first, as before the split.
PLAT_MODS = {m.PLAT: m for m in (adapter_register(x, EXT_PLAT) for x in (plat_gemini, plat_codex))}
EXT_STATE = {"SessionStart": "wait", "UserPromptSubmit": "think", "PreToolUse": "tool",
             "PostToolUse": "think", "Stop": "wait", "Notification": "ask"}   # ⚠`Stop` is `wait` - with `ask` (rank 0) ended sessions occupy the top of the list for 24h
             # SessionEnd is a removal, so absent
# ⚠Platforms whose hooks run in one shared helper (Codex: every TUI's hooks run under the first TUI's `codex app-server`),
#   so the hook pid is the same for different sessions: never merge rows by it (it dropped a live second Codex session).
EXT_SHARED_PID = {"codex"}
EXT_EV_N = 20       # ring size of recent hook events kept per session (for the work panel)
_ext_lock = threading.Lock()
_ext = {}            # (platform, session_id) → cwd·model·transcript_path·state·tool·turnId·first/lastSeen
EXT_ENDED_KEEP_S = 600   # ⚠ext.ROLL_WIN_S follows this: an ended sid must outlive its rollout's freshness window
_ext_ended = {}      # (platform, session_id) → end/gone/dismiss time; hides the rollout-only row (ext_rollout_rows)


def _ended_note_locked(key, now):
    _ext_ended[key] = now
    for k in [k for k, t in _ext_ended.items() if now - t > EXT_ENDED_KEEP_S]:
        _ext_ended.pop(k, None)


def ext_ended(plat, now):
    """Sids of `plat` that ended, went gone or were dismissed within EXT_ENDED_KEEP_S."""
    with _ext_lock:
        return {k[1] for k, t in _ext_ended.items() if k[0] == plat and now - t <= EXT_ENDED_KEEP_S}
_ext_stat = {"posts": 0, "kept": 0, "drop": 0, "lastPost": 0.0, "lastKept": 0.0}
_HOST = socket.gethostname()


def _ext_save_locked():
    """tmp + `os.replace` — dying midway leaves no half-written file. ⚠Call while holding `_ext_lock`."""
    recs = []
    for (plat, sid), v in _ext.items():
        r = dict(v)
        r["platform"] = plat
        r["session_id"] = sid
        recs.append(r)
    try:
        _atomic_write(EXT_FILE, json.dumps(recs, ensure_ascii=False).encode("utf-8"),
                      tmp=EXT_FILE + ".tmp")
    except OSError as e:
        warn_once("ext-save", "Could not save the external session list ({err}) — it is lost on restart",
                  vars={"err": str(e)})


def _pending(v):
    """Row waits on the person (question / approval).
    ⚠Never pruned by age: it leaves only on the CLI's next event, SessionEnd or ext_gone_check (dead pid -> gone).
    A pid-less CLI has unknown liveness, so its request stays past EXT_TTL_S (fail toward showing)."""
    return v.get("state") == "ask" or bool(v.get("blocked"))


def _ext_aged_out(v, now):
    """Row is past EXT_TTL_S and may be dropped by age.
    ⚠A row with a pid is never aged out: ext_gone_check is its exit (live idle CLIs vanished after 24 h; gone rows keep the grace)."""
    if _pending(v) or v.get("pid"):
        return False
    try:
        last = float(v.get("lastSeen") or 0)
    except (TypeError, ValueError):
        last = 0
    return now - last > EXT_TTL_S


def _ext_prune_locked(now):
    for k, v in list(_ext.items()):
        if _ext_aged_out(v, now):
            _ext.pop(k, None)


def _ext_load():
    """Once at startup — so external sessions do not vanish from the list across restarts."""
    try:
        with open(EXT_FILE, encoding="utf-8") as f:
            recs = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(recs, list):
        return
    now = time.time()
    with _ext_lock:
        for r in recs:
            if not isinstance(r, dict):
                continue
            plat = str(r.get("platform") or "")
            sid = str(r.get("session_id") or "")
            if not sid or plat not in EXT_PLAT:
                continue
            if _ext_aged_out(r, now):
                continue
            r.pop("platform", None)
            r.pop("session_id", None)
            _ext[(plat, sid)] = r


_ext_load()


# ── runs launched by a Claude session (`gemini -p` from its Bash; see ext-hooks/ask-gemini) ──
# ★They must stay under the parent after SessionEnd (which drops `_ext`) and across restarts — so a separate,
#   bounded map. ⚠Metadata only: ids, cwd, times, model, state, token total. Never prompt or answer text.
EXT_RUNS_FILE = os.path.join(DATA_DIR, "ext-runs.json")
EXT_RUNS_MAX = 200
EXT_RUNS_TTL_S = 7 * 24 * 3600      # the timeline window goes up to a week
_runs = {}                          # sid → {plat, parent, cwd, start, end, model, state, tok}


def _sid_ok(s):
    return 0 < len(s) <= 64 and all(c.isalnum() or c in "-_" for c in s)


def _runs_save_locked():
    try:
        _atomic_write(EXT_RUNS_FILE, json.dumps(_runs, ensure_ascii=False).encode("utf-8"),
                      tmp=EXT_RUNS_FILE + ".tmp")
    except OSError as e:
        warn_once("ext-runs-save", "Could not save the child-run list ({err})", vars={"err": str(e)})


def _runs_prune_locked(now):
    for k in [k for k, v in _runs.items() if now - float(v.get("end") or 0) > EXT_RUNS_TTL_S]:
        _runs.pop(k, None)
    if len(_runs) > EXT_RUNS_MAX:
        for k in sorted(_runs, key=lambda k: float(_runs[k].get("end") or 0))[:len(_runs) - EXT_RUNS_MAX]:
            _runs.pop(k, None)


def _runs_load():
    try:
        with open(EXT_RUNS_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(d, dict):
        return
    keep = ("plat", "parent", "cwd", "start", "end", "model", "state", "tok")
    with _ext_lock:
        for sid, v in d.items():
            if isinstance(v, dict) and _sid_ok(str(sid)) and _sid_ok(str(v.get("parent") or "")) \
                    and v.get("plat") in EXT_PLAT:
                _runs[str(sid)] = {k: v[k] for k in keep if k in v}
        _runs_prune_locked(time.time())


_runs_load()


# ── per-generation token counts sent by hooks (Cursor `stop`; no record file to read) ──
# ★Must outlive SessionEnd and restarts, like `_runs`. ⚠Metadata only: ints, generation id, cwd, model.
EXT_HOOKTOK_FILE = os.path.join(DATA_DIR, "ext-hooktok.json")
EXT_HOOKTOK_TTL_S = 7 * 24 * 3600
EXT_HOOKTOK_MAX = 5000              # generations kept across all sessions
_hooktok = {}                       # "plat|sid" → {"cwd", "gens": {gen_id: [in, out, cr, cw, ts, model]}}


def _hooktok_save_locked():
    try:
        _atomic_write(EXT_HOOKTOK_FILE, json.dumps(_hooktok, ensure_ascii=False).encode("utf-8"),
                      tmp=EXT_HOOKTOK_FILE + ".tmp")
    except OSError as e:
        # Reuses the ext-save template so no new I18N.ko entry is needed.
        warn_once("ext-hooktok-save", "Could not save the external session list ({err}) — it is lost on restart",
                  vars={"err": str(e)})


def _hooktok_prune_locked(now):
    allg = []
    for k, e in list(_hooktok.items()):
        gens = e.get("gens") or {}
        for g in [g for g, v in gens.items() if now - float(v[4]) > EXT_HOOKTOK_TTL_S]:
            gens.pop(g, None)
        if not gens:
            _hooktok.pop(k, None)
            continue
        allg += [(float(v[4]), k, g) for g, v in gens.items()]
    if len(allg) > EXT_HOOKTOK_MAX:
        for _t, k, g in sorted(allg)[:len(allg) - EXT_HOOKTOK_MAX]:
            _hooktok[k]["gens"].pop(g, None)
            if not _hooktok[k]["gens"]:
                _hooktok.pop(k, None)


def _usage_ok(n):
    return isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 10 ** 9


def _hooktok_load():
    try:
        with open(EXT_HOOKTOK_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(d, dict):
        return
    with _ext_lock:
        for k, e in d.items():
            plat, _s, sid = str(k).partition("|")
            if plat not in EXT_PLAT or not _sid_ok(sid) or not isinstance(e, dict) \
                    or not isinstance(e.get("gens"), dict):
                continue
            gens = {}
            for g, v in e["gens"].items():
                if _sid_ok(str(g)) and isinstance(v, list) and len(v) == 6 and all(_usage_ok(x) for x in v[:4]) \
                        and isinstance(v[4], (int, float)) and isinstance(v[5], str):
                    gens[str(g)] = [v[0], v[1], v[2], v[3], float(v[4]), v[5][:40]]
            if gens:
                _hooktok[plat + "|" + sid] = {"cwd": str(e.get("cwd") or ""), "gens": gens}
        _hooktok_prune_locked(time.time())


_hooktok_load()


def _hooktok_note_locked(plat, sid, req, cwd, ts):
    """Record one Stop's usage under its generation id. Returns True when stored (caller saves).
    ⚠Keyed by generation id: a repeated Stop for the same turn overwrites, so it counts once."""
    u = req.get("usage")
    gen = str(req.get("gen_id") or "")
    if not isinstance(u, dict) or not _sid_ok(gen):
        return False
    vals = [u.get(k) for k in ("in", "out", "cr", "cw")]
    vals = [v if _usage_ok(v) else 0 for v in vals]
    model = str(req.get("model") or "")[:40]
    e = _hooktok.setdefault(plat + "|" + sid, {"cwd": "", "gens": {}})
    if cwd:
        e["cwd"] = cwd
    now = time.time()
    # ⚠Prune by receive time and clamp ts: a far-future `ts` would otherwise expire every stored generation.
    e["gens"][gen] = vals + [min(ts, now), "" if model == "default" else model]
    _hooktok_prune_locked(now)
    return True


def ext_hook_msgs(since=0.0):
    """{(plat, sid): {gen_id: (in, out, cache, 0, ts, model, None)}} for generations at or after `since` —
    the `_tok_sum` message shape (cache = read + write; cost unknown)."""
    out = {}
    with _ext_lock:
        items = [(k, dict(e.get("gens") or {})) for k, e in _hooktok.items()]
    for k, gens in items:
        plat, _s, sid = k.partition("|")
        ms = {g: (v[0], v[1], v[2] + v[3], 0, float(v[4]), v[5], None) for g, v in gens.items()
              if float(v[4]) >= since}
        if ms:
            out[(plat, sid)] = ms
    return out


def ext_hook_cwds():
    """{(plat, sid): cwd} for every session with stored hook tokens."""
    with _ext_lock:
        return {tuple(k.partition("|")[::2]): str(e.get("cwd") or "") for k, e in _hooktok.items()}


def ext_side_msgs(since=0.0):
    """`ext_hook_msgs` plus Copilot usage records (plat_copilot) — tokens of platforms outside `PLAT_MODS`.
    ⚠A record replaces a hook entry with the same key, never adds to it."""
    out = ext_hook_msgs(since)
    for sid, ms in plat_copilot.msgs_since(since).items():
        out.setdefault((plat_copilot.PLAT, sid), {}).update(ms)
    return out


def ext_side_sess(plat, sid):
    """One session's side messages (same merge as `ext_side_msgs`); {} for anything but Copilot."""
    if plat != plat_copilot.PLAT:
        return {}
    with _ext_lock:
        e = _hooktok.get(plat + "|" + str(sid))
        ms = {g: (v[0], v[1], v[2] + v[3], 0, float(v[4]), v[5], None) for g, v in ((e or {}).get("gens") or {}).items()}
    ms.update(plat_copilot.usage_msgs(sid))
    return ms


def ext_side_tok(plat, sid):
    """`ext_tok` shape (total + latest model) from `ext_side_sess`, or None when empty."""
    ms = ext_side_sess(plat, sid)
    if not ms:
        return None
    s = _tok_sum(ms)
    s["model"] = max(ms.values(), key=lambda v: v[4])[5]
    return s


def _run_note_locked(plat, sid, v, ev, ts):
    """Mirror one parented session's metadata into `_runs`. Returns True when the file should be written."""
    par = v.get("parent") or ""
    if not par:
        return False
    r = _runs.get(sid)
    new = r is None
    if new:
        r = {"plat": plat, "parent": par, "start": float(v.get("firstSeen") or ts)}
        _runs[sid] = r
    r["end"] = ts
    r["cwd"] = v.get("cwd") or r.get("cwd") or ""
    if v.get("model"):
        r["model"] = str(v["model"])[:40]
    r["state"] = "done" if ev == "SessionEnd" else (v.get("state") or "wait")
    if ev == "SessionEnd":
        ext_tok_refresh(plat, sid, v.get("transcript_path") or "")
        tk = ext_tok(plat, sid) or {}
        if tk.get("tok"):
            r["tok"] = int(tk["tok"])
        if not r.get("model") and tk.get("model"):
            r["model"] = tk["model"]
    if new:
        _runs_prune_locked(ts)
    return new or ev in ("SessionEnd", "Stop")


def ext_runs(parent=None):
    """[{sid, plat, parent, cwd, start, end, model, state, tok}] — all, or those under one Claude session."""
    with _ext_lock:
        items = [(k, dict(v)) for k, v in _runs.items()]
    out = []
    for sid, v in items:
        if parent is None or v.get("parent") == parent:
            v["sid"] = sid
            out.append(v)
    out.sort(key=lambda r: float(r.get("start") or 0))
    return out


def ext_ingest(req):
    """Apply one `/api/hook` event to the registry — unknown keys ignored. Returns `(ok, reason)`."""
    plat = str(req.get("platform") or "").strip().lower()
    sid = str(req.get("session_id") or "").strip()
    ev = str(req.get("event") or "").strip()
    if not sid:
        return False, "session_id required"
    if plat not in EXT_PLAT:
        return False, "unknown platform"
    now = time.time()
    try:
        ts = float(req.get("ts") or 0) or now
    except (TypeError, ValueError):
        ts = now                                  # ★if `ts` is missing or broken, it is **the receive time**
    key = (plat, sid)
    with _ext_lock:
        _ext_prune_locked(now)
        if ev == "SessionEnd":
            _ended_note_locked(key, now)
            gone = _ext.pop(key, None)
            if gone is not None:
                if _run_note_locked(plat, sid, gone, ev, ts):
                    _runs_save_locked()
                _ext_save_locked()
            return True, "end"
        v = _ext.get(key) or {"firstSeen": ts}
        par = str(req.get("parent") or "").strip()
        if par and _sid_ok(par) and par != sid:
            v["parent"] = par
        for src, dst in (("cwd", "cwd"), ("model", "model"),
                         ("transcript_path", "transcript_path"), ("turn_id", "turnId")):
            if req.get(src):
                v[dst] = str(req.get(src))
        pid = req.get("pid")
        # ⚠A pid is only meaningful on this machine (SIDEREUS_HOOK_URL may point here from elsewhere).
        if isinstance(pid, int) and not isinstance(pid, bool) and 1 < pid < (1 << 22) \
                and str(req.get("host") or "") == _HOST:
            if v.get("pid") != pid:
                v.pop("pidAt", None)
            v["pid"] = pid
            v["pstart"] = str(req.get("pstart") or "")[:40]
        if v.get("state") == "gone":              # any event proves it is alive again
            v["state"] = v.get("goneFrom") or "wait"
        for k in ("gone", "goneWhy", "goneFrom"):
            v.pop(k, None)
        st = EXT_STATE.get(ev)
        if st:
            v["state"] = st
        if ev == "PreToolUse":
            v["tool"] = str(req.get("tool_name") or "")
        elif ev in ("PostToolUse", "Stop", "UserPromptSubmit", "SessionStart"):
            v["tool"] = ""                        # the tool ended, so «current task» ended too
        v["blocked"] = (ev == "Notification")     # ★notification = a person must press for it to move (same meaning as blocked on Claude rows)
        # ⚠Metadata only (event name, tool name, time) — never prompt or tool input text.
        evs = v.get("ev") if isinstance(v.get("ev"), list) else []
        evs.append({"e": ev[:40], "tool": str(req.get("tool_name") or "")[:60], "t": ts})
        v["ev"] = evs[-EXT_EV_N:]
        v["lastSeen"] = ts
        if not v.get("firstSeen"):
            v["firstSeen"] = ts
        _ext[key] = v
        if _run_note_locked(plat, sid, v, ev, ts):
            _runs_save_locked()
        # Adapter platforms read tokens from their record files; hook usage would double them.
        if ev == "Stop" and plat not in PLAT_MODS and _hooktok_note_locked(plat, sid, req, v.get("cwd") or "", ts):
            _hooktok_save_locked()
        _ext_dedupe_locked()
        _ext_save_locked()
    return True, "ok"


def _ext_dedupe_locked():
    """One row per live CLI process. ★Gemini `--resume` (2026-09-24) fires SessionStart under a fresh sid
    (its chat file gets one entry), then every later hook carries the resumed sid — same pid+pstart, two rows.
    Keep the row with the latest activity, fold the other's firstSeen into it. ⚠Stored pids are local only
    (host checked at ingest), so (plat, pid, pstart) implies the host. Returns True when a row was dropped."""
    best = {}
    for k, v in _ext.items():
        if not v.get("pid") or not v.get("pstart") or k[0] in EXT_SHARED_PID:
            continue
        g = (k[0], v["pid"], v["pstart"])
        best.setdefault(g, []).append(k)
    dropped = False
    for ks in best.values():
        if len(ks) < 2:
            continue
        ks.sort(key=lambda k: float(_ext[k].get("lastSeen") or 0))
        keep = _ext[ks[-1]]
        for k in ks[:-1]:
            v = _ext.pop(k)
            try:
                fs = [float(x) for x in (keep.get("firstSeen"), v.get("firstSeen")) if x]
            except (TypeError, ValueError):
                fs = []
            if fs:
                keep["firstSeen"] = min(fs)
            if _run_note_locked(k[0], k[1], v, "SessionEnd", float(v.get("lastSeen") or 0)):
                _runs_save_locked()
            dropped = True
    return dropped


def _pid_start(pid):
    """`ps` start time of `pid` ("" when gone, None when ps failed). ⚠LC_ALL=C like the hook — lstart is localized."""
    try:
        out = subprocess.run(["/bin/ps", "-o", "lstart=", "-p", str(pid)], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=2,
                             env={"LC_ALL": "C", "PATH": "/bin:/usr/bin"}).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return " ".join(out.decode("utf-8", "replace").split())


def _pid_gone(pid, pstart):
    """True only when the CLI process is certainly gone (or its pid was reused). ⚠Signal 0 only — never a real signal."""
    alive = pid_alive(pid)
    if alive is False:
        return True
    if alive is None:
        return False
    if pstart:
        now_start = _pid_start(pid)
        if now_start is not None and now_start != pstart:
            return True
    return False


def ext_gone_check(now=None):
    """Mark sessions whose CLI died (pid) or fell silent while busy (no pid) as «Disconnected»; drop them after
    `EXT_GONE_GRACE_S` like a SessionEnd. History/timeline data stays (runs end at the last event)."""
    now = now or time.time()
    with _ext_lock:
        if _ext_dedupe_locked():                  # rows saved before the dedupe existed
            _ext_save_locked()
        due = [(k, v["pid"], v.get("pstart") or "") for k, v in _ext.items()
               if v.get("pid") and not v.get("gone")
               and now - float(v.get("pidAt") or 0) >= EXT_PID_EVERY_S]
        for k, _p, _s in due:
            _ext[k]["pidAt"] = now
    dead = {k: pid for k, pid, ps in due if _pid_gone(pid, ps)}   # outside the lock: may run `ps`
    changed = runs = False
    with _ext_lock:
        for k, v in list(_ext.items()):
            try:
                last = float(v.get("lastSeen") or 0)
            except (TypeError, ValueError):
                last = 0.0
            if not v.get("gone"):
                why = ""
                if k in dead and v.get("pid") == dead[k] and last <= now:
                    why = "pid"
                elif not v.get("pid") and v.get("state") in ("think", "tool") and now - last > EXT_SILENT_S:
                    why = "silent"
                if why:
                    v.update(goneFrom=v.get("state") or "", state="gone", goneWhy=why, blocked=False, tool="",
                             gone=now if why == "pid" else last + EXT_SILENT_S)
                    changed = True
                    if v.get("parent"):
                        _run_note_locked(k[0], k[1], v, "Gone", last)
                        runs = True
            if v.get("gone") and now - float(v["gone"]) > EXT_GONE_GRACE_S:
                _ext.pop(k, None)
                _ended_note_locked(k, now)
                _run_note_locked(k[0], k[1], v, "SessionEnd", last)
                changed = True
                runs = runs or bool(v.get("parent"))
        if runs:
            _runs_save_locked()
        if changed:
            _ext_save_locked()


def ext_dismiss(sid):
    """Person dismissed a pid-less pending row (liveness unknown, never pruned): drop it from the store like a SessionEnd.
    ⚠pid rows are refused — ext_gone_check owns their exit. A live CLI's next event re-creates the row. -> rows removed."""
    if not isinstance(sid, str) or not _sid_ok(sid):
        return 0
    n = 0
    with _ext_lock:
        now = time.time()
        if not any(k[1] == sid for k in _ext):   # a record-file-only row (Codex rollout, Cursor/Copilot folder): hide it for its window
            for p in ("codex", "cursor", "copilot"):
                _ended_note_locked((p, sid), now)
            n += 1
        for k, v in list(_ext.items()):
            if k[1] == sid and not v.get("pid") and _pending(v):
                _ext.pop(k, None)
                _ended_note_locked(k, now)
                if _run_note_locked(k[0], k[1], v, "SessionEnd", float(v.get("lastSeen") or 0)):
                    _runs_save_locked()
                n += 1
        if n:
            _ext_save_locked()
    return n


# ── per-session token totals from the CLI's own record file ───────────────────
# ⚠Separate store — this must never feed Claude's quota/usage paths (`_usage_add`, burn, 5h/7d KPIs).
# ⚠Only ids, token counts, model and timestamps are kept; message text is parsed per line and dropped.
EXT_RATE_WIN = 600           # «Live · 10 min» window, same span as Claude's live card
_tok_lock = threading.Lock()
_tok = {}    # (platform, sid) → {"path", "size", "off", "pv", "msgs": {id: (in, out, cache, thought, ts, model, cost)}}


def ext_tok_refresh(plat, sid, path):
    """Re-read one live session's record file through its platform module (each caches by path)."""
    mod = PLAT_MODS.get(plat)
    if mod is None:
        return
    msgs = mod.session_msgs(path)
    if msgs is not None:
        with _tok_lock:
            _tok[(plat, sid)] = {"path": path, "size": 0, "off": 0, "pv": "", "msgs": msgs}


def _tok_sum(msgs, since=0.0):
    s = {"tok": 0, "in": 0, "out": 0, "cache": 0, "thought": 0, "cost": None, "costMiss": 0}
    for i, o, c, t, ts, _m, usd in msgs.values():
        if ts >= since:
            s["in"] += i; s["out"] += o; s["cache"] += c; s["thought"] += t
            if usd is None:
                s["costMiss"] += 1
            else:
                s["cost"] = (s["cost"] or 0.0) + usd
    s["tok"] = s["in"] + s["out"] + s["cache"] + s["thought"]
    return s


def ext_tok(plat, sid):
    """Session total + latest model, or None when nothing was read."""
    with _tok_lock:
        e = _tok.get((plat, sid))
        msgs = dict(e["msgs"]) if e else {}
    if not msgs:
        return None
    s = _tok_sum(msgs)
    best = None
    for v in msgs.values():                     # latest timestamp; ties → the later line
        if best is None or v[4] >= best[4]:
            best = v
    s["model"] = best[5]
    return s
