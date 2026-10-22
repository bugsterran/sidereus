"""Context-window learning (split out of sidereus/live.py for the size cap): WIN_* / _win_* state, _ctx_window, _win_loop.
Owns `_win_seen`/`_win_ev`/`_win_scanned`/`_win_lock` (mutated in place); live re-exports the names its importers use."""
import glob
import json
import os
import threading
import time
from datetime import datetime
from sidereus.config import DATA_DIR
from sidereus import boot_queue, claude_roots
from sidereus.warn import _LOOP_ERR, warn_once
from sidereus.prefs import compact_hist
from sidereus.bus import _atomic_write
from sidereus.transcript import CLAUDE_PROJECTS, _line_ts


# ★Context window — the model string cannot tell it. Transcripts say only `claude-opus-5`, with **no** `[1m]` mark
#   (measured 2026-08-19: a 1M session was taken as 200k and showed 349%). `~/.claude.json`'s `lastModelUsage` keeps
#   `[1m]`, but is written **only on clean exit** and per project, so it is useless for running sessions (measured: empty for every active project).
#
#   ⇒ So decide by **compaction events**. `compactMetadata.preTokens` of `type:"system" subtype:"compact_boundary"`
#     is **the size at the moment it hit the window and compacted** — it states the window directly.
#     ⚠Use `trigger:"auto"` only. `manual` (user ran /compact) fires at points unrelated to the window
#       (measured: sonnet-4-6 387k · opus-4-7 485k were those — mixing them learns the wrong window).
#
#   Three tiers, strongest first. Weak evidence is **shown as weak on screen** (dashed).
#     ① obs   the session proves it itself — observed >200k (=1M), or its transcript has an auto compaction
#     ② model value proven by ① in **another session** of the same model (this machine's learned value; no per-session proof yet)
#     ③ none  model never seen ⇒ return 0 so the UI shows absolute (k) instead of %
#   Learned (2026-08-19, 108 auto compactions): opus-5·opus-4-8·opus-4-7 = 1M · sonnet-4-6 = 200k.
WIN_FILE = os.path.join(DATA_DIR, "win-model.json")   # learned result — survives restarts (skip the 1.6 s first scan each time)
WIN_FMT = 3                                        # format version. On change, drop scan records and relearn from scratch
#   v3 (2026-09-28): v2 learned from compactions caused by the user's autoCompactWindow (sonnet-5 {200k:3} showed 86% of a 1M window).
WIN_STEPS = (200_000, 1_000_000)
CLAUDE_SCAN_DAYS = 30                              # older transcripts are not read (old-model evidence is worthless)
_win_seen = {}                 # session (transcript path) -> window. Proven by ①
# ★Evidence is **counted per session**. At first it was +1 per observation, but with a 2.5 s poll one session piled up
#   24 per minute (measured 2026-08-19: opus-5 went 46 → 82). Then ⓐ the tooltip's "N times" became a poll count and
#   ⓑ the 200k/1M vote went to one long-running session. So **evidence is held as a set of session keys**.
_win_ev = {}                   # model -> {window: set(session keys)}. Evidence for ②
_win_scanned = {}              # file -> scanned mtime (unchanged files are not reread)
_win_lock = threading.Lock()


def _win_load():
    try:
        with open(WIN_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("v") != WIN_FMT:
            # Format changed ⇒ **drop the scan records too.** Clearing only evidence while keeping `scanned`
            #   leaves "all 88 scanned", nothing is reread, and the learned values stay empty forever (design trap).
            warn_once("winfmt", "Window-learning data format changed — relearning (v{old} → v{new})",
                      vars={"old": d.get("v"), "new": WIN_FMT})
            return
        for k, v in (d.get("evidence") or {}).items():
            _win_ev[k] = {int(w): set(keys) for w, keys in v.items()}
        _win_seen.update({k: int(v) for k, v in (d.get("sessions") or {}).items()})
        _win_scanned.update({k: float(v) for k, v in (d.get("scanned") or {}).items()})
    except FileNotFoundError:
        pass                    # first run: nothing learned yet
    except Exception as e:
        warn_once("winload", "Could not read window-learning data ({err}) — learning from scratch",
                  vars={"err": f"{type(e).__name__}: {e}"})


def _win_save():
    try:
        # ⚠Snapshot under _win_lock (request threads add keys via _win_learn); do not call _model_win here — Lock is not reentrant.
        with _win_lock:
            ev = {k: {str(w): sorted(keys) for w, keys in v.items()} for k, v in _win_ev.items()}
            seen, scanned = dict(_win_seen), dict(_win_scanned)
        _atomic_write(WIN_FILE, json.dumps(
            {"v": WIN_FMT, "evidence": ev,
             "windows": {k: int(max(v, key=lambda w: len(v[w]))) if v else 0 for k, v in ev.items()},   # human-readable summary (not used for decisions)
             "sessions": seen, "scanned": scanned,
             "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False).encode("utf-8"),
            tmp=WIN_FILE + ".tmp")
    except Exception as e:
        warn_once("winsave", "Could not save window-learning data ({err})", vars={"err": f"{type(e).__name__}: {e}"})


# ★An auto compaction fires at min(model window, autoCompactWindow) — so it proves the window only when the setting
#   was well above it (measured 2026-09-28: 200k compactions from the 09-10..09-22 setting taught sonnet-5 «200k», live 86% vs CLI 17%).
#   Known setting history (local dates, from config compact_history); None = unset (model window decides). Later changes come from compact-win.json.
#   ⚠Not settings.json itself — it has only the current value, and the setting is read at session start.
#   The table is config compact_history (built-in default empty; read once at import).
COMPACT_HIST = compact_hist()
COMPACT_STATE_FILE = os.path.join(DATA_DIR, "compact-win.json")   # read only — sidereus/burn_scan.py owns and writes it


def _compact_hist():
    """COMPACT_HIST plus a newer change recorded in compact-win.json (read only)."""
    h = list(COMPACT_HIST)
    try:
        with open(COMPACT_STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        since, val = float(st.get("since") or 0), st.get("value")
        if since > h[-1][0] and val != h[-1][1]:
            h.append((since, int(val) if val else None))
    except (OSError, ValueError, TypeError, AttributeError):
        return h                  # no/partial compact-win.json: the dated table alone
    return h


def _root_hist(root):
    """Extra Claude root: its current settings.json autoCompactWindow as the whole history (no change log there)."""
    try:
        with open(os.path.join(os.path.dirname(root), "settings.json"), encoding="utf-8") as f:
            v = json.load(f).get("autoCompactWindow")
        return [(0.0, int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v else None)]
    except (OSError, ValueError, TypeError, AttributeError):
        return [(0.0, None)]


def _compact_cap(t0, t1, hist):
    """Lowest autoCompactWindow in effect over [t0, t1] (None = unset throughout) — conservative across a mid-session change."""
    lo, t0 = None, min(t0, t1)
    for i, (since, val) in enumerate(hist):
        until = hist[i + 1][0] if i + 1 < len(hist) else float("inf")
        if since <= t1 and until > t0 and val:
            lo = val if lo is None else min(lo, val)
    return lo


def _win_clean(w, cap):
    """Compaction at ~w is window evidence only if the setting could not have caused it (cap > 1.5·w, so 300k/200k is discarded)."""
    return cap is None or cap > 1.5 * w


def _round_win(pt):
    """preTokens of an auto compaction -> window. If not near one, **discard** (forcing a fit learns the wrong window)."""
    for w in WIN_STEPS:
        if 0.75 * w <= pt <= 1.25 * w:
            return w
    return 0


def _win_learn(model, win, key):
    """Add one piece of evidence. The same (model, window, session) counts as **1** however often observed."""
    if not model or model == "<synthetic>" or win not in WIN_STEPS or not key:
        return
    with _win_lock:
        _win_ev.setdefault(model, {}).setdefault(win, set()).add(key)


def _model_win(model):
    """Per-model learned value -> (window, evidence session count). If both 200k and 1M were seen, **the one with more sessions** wins (shown as estimate)."""
    with _win_lock:   # copy counts under the lock so a concurrent _win_learn cannot resize the dict mid-max
        d = {w: len(s) for w, s in (_win_ev.get(model or "") or {}).items()}
    if not d:
        return 0, 0
    win = max(d, key=lambda w: d[w])
    return win, d[win]


def _ctx_window(model, ctx=0, key=""):
    """(window, basis) — basis is `obs` (session proved it) · `model` (same model's learned value) · `''` (unknown)."""
    if ctx > 200_000:                       # past 200k = that session has a 1M window (nothing more to check)
        if key:
            _win_seen[key] = 1_000_000
        _win_learn(model, 1_000_000, key)
        return 1_000_000, "obs"
    if key and _win_seen.get(key):
        # ⚠Why remember: after auto compaction the value drops below 200k. Without memory the same session's
        #   % disappears and reappears (flicker). A proven window stays until the session ends.
        return _win_seen[key], "obs"
    win, _n = _model_win(model)
    return (win, "model") if win else (0, "")


def _win_prune(now, days=CLAUDE_SCAN_DAYS):
    """Drop `_win_seen`/`_win_scanned` entries whose transcript is gone or older than `days` -> count dropped.
    ⚠Retention = CLAUDE_SCAN_DAYS, the longest window any reader uses: the scan skips older files anyway and the
      session list is 12 h (+ newest per live path), so recent files behave identically. A live session idle past
      `days` only falls back to the model-level estimate until its next write.
      `_win_ev` is left alone — its keys are per-model votes, not per-file state."""
    cut = now - days * 86400
    with _win_lock:
        keys = set(_win_seen) | set(_win_scanned)
    drop = []
    for fp in keys:
        try:
            if os.path.getmtime(fp) < cut:
                drop.append(fp)
        except OSError:
            drop.append(fp)
    with _win_lock:
        for fp in drop:
            _win_seen.pop(fp, None)
            _win_scanned.pop(fp, None)
    return len(drop)


def _scan_windows(days=CLAUDE_SCAN_DAYS):
    """Learn windows from auto compactions in transcripts. Measured: all 88 files, 1.2GB, in 1.6 s —
    still reads **only changed files** (mtime check). Runs in background; failure never kills the page."""
    learned = 0
    try:
        now = time.time()
        hist0 = _compact_hist()
        # ⚠an extra root has its own autoCompactWindow — judging it by the primary's history learns a wrong window
        roots = claude_roots.projects_dirs(CLAUDE_PROJECTS)
        hists = [hist0] + [_root_hist(r) for r in roots[1:]]
        files = [(fp, h) for r, h in zip(roots, hists) for fp in glob.glob(os.path.join(r, "*", "*.jsonl"))]
        for fp, hist in files:
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            if now - mt > days * 86400 or _win_scanned.get(fp) == mt:
                continue
            model, win, t0 = None, 0, None
            try:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if t0 is None and '"timestamp"' in line:
                            try:
                                t0 = _line_ts(json.loads(line), None)   # session start — the setting is read then
                            except ValueError:
                                t0 = None         # torn line: take the start from the next timestamped line
                        if '"model"' in line:
                            try:
                                m = (json.loads(line).get("message") or {}).get("model")
                            except Exception:
                                m = None
                            if m and m != "<synthetic>":
                                model = m            # model at compaction time — follows line order
                        if "compactMetadata" not in line:
                            continue
                        try:
                            d = json.loads(line)
                            cm = d.get("compactMetadata") or {}
                        except Exception:
                            continue
                        if cm.get("trigger") != "auto":
                            continue                  # ★manual fires at points unrelated to the window
                        w = _round_win(int(cm.get("preTokens") or 0))
                        tc = _line_ts(d, mt)
                        if w and not _win_clean(w, _compact_cap(t0 if t0 is not None else tc, tc, hist)):
                            w = 0                     # ⚠caused by autoCompactWindow, not the model window
                        if w:
                            win = w
                            _win_learn(model, w, fp)   # per file (session) — five compactions still count as 1
                            learned += 1
            except OSError:
                continue
            if win:
                _win_seen.setdefault(fp, win)         # the session's own proof (①) — stronger than the model estimate
            _win_scanned[fp] = mt
        pruned = _win_prune(now, days)
        if learned or pruned or _win_scanned:
            _win_save()
    except Exception as e:
        warn_once("winscan", "Window-learning scan failed ({err})", vars={"err": f"{type(e).__name__}: {e}"})
    return learned


def _win_loop():
    # ★Wrap a whole round so an exception cannot end the thread (2026-09-07) — see the comment above `warn_once`
    #   (measured: `_wkuse_loop` died silently of a TypeError and froze the screen).
    while True:
        try:
            with boot_queue.gate("win_loop"):   # ⚠first pass waits its boot turn; no-op after drain (traps/server.md)
                _scan_windows()
            _LOOP_ERR.pop("win", None)
            time.sleep(3600)
        except Exception as e:
            warn_once("loop:win", "Window-learning scan stopped refreshing — {err}",
                      vars={"err": f"{type(e).__name__}: {e}"[:118]})   # 160 chars in all, as before
            _LOOP_ERR["win"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
            time.sleep(60)          # ⚠the exception path must sleep too — otherwise it becomes a tight infinite loop
            continue
