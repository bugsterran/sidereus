"""Saver mode: switch files, stages and the view snapshot."""
import contextlib
import hashlib
import json
import os
import re
import threading
import time
import shutil
from sidereus.config import CFG, DATA_DIR, file_lock
from sidereus.bus import _atomic_write
from sidereus.quota import quota
from sidereus.prefs import effective as _pref
from sidereus.claude_roots import accounts as claude_accounts


# ★Saver-mode status (2026-09-04, shown in Sidereus).
#   The inputs are **identical** to the hook (`~/.claude/hooks/saver.py`) — the screen and the model must not disagree.
#   (1) the manual switch a person set (`.saver-force.json`) (2) 5-hour quota % at or above threshold.
# ★Stages (2026-09-10) — the hook gives different caps by %. The screen must state **the same boundaries**.
#   ⚠The source of truth is `STAGES`·`CAP` in `~/.claude/hooks/saver.py`. Change them there too if you change these —
#     fixing only one side makes the screen and model disagree (a pitfall this file already hit at the `pct()` guard).
SAVER_STAGES = ((100, 4), (85, 3), (75, 2), (50, 1))
SAVER_CAP = {1: 2, 2: 1, 3: 0, 4: 0}      # max concurrent subagents per stage
SAVER_MIN = SAVER_STAGES[-1][0]           # saver mode (stage 1) from this %
_SAVER_HOOK_DIR = os.path.expanduser(_pref("saver_hook_dir"))   # config saver_hook_dir, default ~/.claude/hooks
SAVER_FORCE = os.path.join(_SAVER_HOOK_DIR, ".saver-force.json")
# ★The manual switch reads **the same file** as the hook. ⚠Not opened on every poll (2.5s) — TTL cache.
#   But when a person types `/saver` the screen must follow within this TTL (hence seconds, not minutes).
_SAVER_FORCE_TTL = 5.0
_saver_force_cache = {"at": 0.0, "v": ("", 0)}


def _saver_force():
    """`.saver-force.json` → `(mode, mstage)`. `("", 0)` if unreadable (=auto, the behavior so far).

    ⚠Not obtained by importing `saver.py` — importing that module runs the hook body (reads stdin and
      injects). That is why the file is read directly (same reason as the `_saver_view` comment).
    """
    now = time.monotonic()
    c = _saver_force_cache
    if c["at"] and (now - c["at"]) < _SAVER_FORCE_TTL:
        return c["v"]
    mode, mstage = "", 0
    try:
        with open(SAVER_FORCE, encoding="utf-8") as f:
            _f = json.load(f)
        mode = (_f.get("mode") or "").lower()
        try:
            mstage = int(_f.get("stage") or 0)
        except Exception:
            mstage = 0
    except Exception:
        mode, mstage = "", 0
    c["at"], c["v"] = now, (mode, mstage)
    return mode, mstage


# ★Settings-modal saver switch (2026-09-23). Writes **the same files, same bytes** as `/saver`
#   (`~/.claude/hooks/saver-mode.sh`), so the CLI and the screen can alternate freely.
#   ⚠goal lives in its own file — `pace_of` in saver.py uses the FORCE file's mtime as the pace anchor.
SAVER_GOAL = os.path.join(_SAVER_HOOK_DIR, ".saver-goal.json")
_SAVER_HHMM = re.compile(r"^(?:[0-9]|[01][0-9]|2[0-3]):[0-5][0-9]$")   # same pattern as saver-mode.sh `pace`
_saver_sw_cache = {"at": 0.0, "v": None}
# ★Action when the goal quota is reached («Notify only / Warn, then allow / Block»). Read by `~/.claude/hooks/saver_limit.py`
#   (UserPromptSubmit via saver.py + PreToolUse). advise = today's behaviour and the default when the file is missing.
# ⚠Own file: the CLI rewrites `.saver-goal.json` wholesale (`/saver goal`), and FORCE's mtime is the pace anchor.
SAVER_LIMIT = os.path.join(_SAVER_HOOK_DIR, ".saver-limit.json")
SAVER_LIMITS = ("advise", "warn", "block")
SAVER_TRASH = None          # None = DATA_DIR/tool-trash; ⚠tests set a tmp dir


def _saver_read(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None      # hook file missing or mid-write: treated as unset


def _saver_switch():
    """Raw switch files → `{mode, stage, until, goal, goalSet}` for the modal (TTL-cached like `_saver_force`).
    ⚠goal mirrors saver.py `goal_of`: no file = 100 (default), `{"goal":null}` = off (None)."""
    now = time.monotonic()
    c = _saver_sw_cache
    if c["at"] and (now - c["at"]) < _SAVER_FORCE_TTL:
        return c["v"]
    f = _saver_read(SAVER_FORCE) or {}
    mode = f.get("mode").lower() if isinstance(f.get("mode"), str) else ""
    mode = mode if mode in ("on", "off", "pace") else "auto"
    try:
        stage = int(f.get("stage") or 0)
    except Exception:
        stage = 0
    if mode == "on" and stage not in SAVER_CAP:
        stage = 3                                   # hook default for a bare `on`
    g = _saver_read(SAVER_GOAL)
    goal, gset = 100, False
    if g is not None and "goal" in g:
        gv = g.get("goal")
        if gv is None:
            goal, gset = None, True
        elif isinstance(gv, (int, float)) and not isinstance(gv, bool):
            goal, gset = int(max(0, min(100, gv))), True
    la = (_saver_read(SAVER_LIMIT) or {}).get("action")
    v = {"mode": mode, "stage": stage if mode == "on" else 0,
         "until": f.get("until") if mode == "pace" else None, "goal": goal, "goalSet": gset,
         "limit": la if la in SAVER_LIMITS else "advise"}
    c["at"], c["v"] = now, v
    return v


def _saver_write(path, obj):
    # Compact JSON + newline = byte-identical to the skill's `printf '{"mode":"on","stage":2}\n'`.
    # ⚠Keep the explicit tmp name (same dir, pid+thread suffix): hooks/skill only ever see `path` or this sidecar.
    _atomic_write(path, (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
                  tmp=f"{path}.tmp.{os.getpid()}.{threading.get_ident()}")


def _saver_backup(path):
    # Copy before write into DATA_DIR/tool-trash/<ts>/ (same folder as the other settings writes); None if nothing to copy.
    if not os.path.exists(path):
        return None
    base = os.path.join(SAVER_TRASH or os.path.join(DATA_DIR, "tool-trash"), time.strftime("%Y%m%d-%H%M%S"))
    d, n = base, 1
    while os.path.exists(d):
        n += 1
        d = "%s-%d" % (base, n)
    os.makedirs(d)
    dst = os.path.join(d, os.path.basename(path))
    shutil.copy2(path, dst)
    return dst


@contextlib.contextmanager
def _saver_lock(path):
    # Exclusive flock on a sidecar `<path>.lock` so concurrent read-merge-write callers serialize.
    # ⚠Lock a separate file, not `path` itself: os.replace swaps the inode, which would orphan a lock held on it.
    with file_lock(path + ".lock"):
        yield


def _saver_int(v, lo, hi):
    # The skill accepts digits only — no floats, no bools.
    if isinstance(v, bool):
        return None
    if isinstance(v, str) and v.isascii() and v.isdigit():   # ⚠bare isdigit() accepts '²' -> int() raises
        v = int(v)
    return v if isinstance(v, int) and lo <= v <= hi else None


def saver_set(req):
    """`POST /api/saver/set` body `{mode?, stage?, until?, goal?}` — validates all, then writes.
    mode: auto (deletes FORCE, like `/saver auto`) · off · on (+stage 1-4, default 3) · pace (+until HH:MM).
    goal: 0-100 int, or null/"off". Unknown keys already in a file are kept (merge)."""
    if not isinstance(req, dict):
        return {"ok": False, "err": "body must be a JSON object"}
    mode, has_goal, lim = req.get("mode"), "goal" in req, req.get("limit")
    if mode is None and not has_goal and lim is None:
        return {"ok": False, "err": "nothing to set (mode, goal or limit)"}
    if lim is not None and lim not in SAVER_LIMITS:
        return {"ok": False, "err": "limit must be advise|warn|block"}
    fobj = gobj = None
    if mode is not None:
        if mode not in ("auto", "off", "on", "pace"):
            return {"ok": False, "err": "mode must be auto|off|on|pace"}
        if mode == "on":
            st = _saver_int(req.get("stage", 3), 1, 4)
            if st is None:
                return {"ok": False, "err": "stage must be 1-4"}
            fobj = {"mode": "on", "stage": st}
        elif mode == "pace":
            u = req.get("until")
            if not isinstance(u, str) or not _SAVER_HHMM.fullmatch(u):   # ⚠`$` in match() admits a trailing "\n"
                return {"ok": False, "err": "until must be HH:MM (00:00-23:59)"}
            fobj = {"mode": "pace", "until": u}
        elif mode == "off":
            fobj = {"mode": "off"}
    if has_goal:
        gv = req.get("goal")
        if gv is None or gv == "off":
            gobj = {"goal": None}
        else:
            gi = _saver_int(gv, 0, 100)
            if gi is None:
                return {"ok": False, "err": "goal must be an integer 0-100 or off"}
            gobj = {"goal": gi}
    if mode == "auto":
        with _saver_lock(SAVER_FORCE):
            try:
                os.remove(SAVER_FORCE)
            except FileNotFoundError:
                pass            # already auto
    elif fobj is not None:
        # ⚠mode-specific keys are replaced, not merged — a stale `until` beside `on` would mislead `/saver status`.
        with _saver_lock(SAVER_FORCE):
            keep = {k: v for k, v in (_saver_read(SAVER_FORCE) or {}).items() if k not in ("mode", "stage", "until")}
            fobj.update(keep)
            _saver_write(SAVER_FORCE, fobj)
    bak = None
    if lim is not None:
        # ⚠The route requires the viewer Origin for `limit` (it can block every CLI session).
        with _saver_lock(SAVER_LIMIT):
            bak = _saver_backup(SAVER_LIMIT)
            lobj = {k: v for k, v in (_saver_read(SAVER_LIMIT) or {}).items() if k != "action"}
            lobj["action"] = lim
            _saver_write(SAVER_LIMIT, lobj)
    if gobj is not None:
        with _saver_lock(SAVER_GOAL):
            gobj.update({k: v for k, v in (_saver_read(SAVER_GOAL) or {}).items() if k != "goal"})
            _saver_write(SAVER_GOAL, gobj)
    _saver_force_cache["at"] = 0.0
    _saver_sw_cache["at"] = 0.0
    out = {"ok": True, "switch": _saver_switch()}
    if bak:
        out["backup"] = bak
    try:
        _q5 = (quota() or {}).get("five_hour") or {}
        out["saver"] = _saver_state(_q5.get("pct"), _q5.get("leftSec"))
    except Exception:
        out["saver"] = None
    return out


def _saver_stage(p):
    for th, st in SAVER_STAGES:
        if isinstance(p, (int, float)) and p >= th:
            return st
    return 0


def _saver_state(pct, left=None):
    mode, mstage = _saver_force()
    # ★★**Do not turn on from a % of an already-ended window** (measured 2026-09-08). `quota()` is a cache (`age`),
    #   so right after reset it returns **the pre-reset %** for a while. Meanwhile the hook newly injected saver mode
    #   into session `c9d0e1f2` — at 16:00, one minute after reset, when the real pct was 0.
    #   ⇒ Do not cut by an age threshold (even 60s was already wrong). Check **whether the window that value
    #     describes has ended**: if `leftSec <= 0` it is a past window's %, so treat as unknown.
    #   ⚠`pct()` in `~/.claude/hooks/saver.py` has **the same guard** — fixing only one side makes
    #     the screen and model disagree (the principle in the `buildSaver` comment above this function).
    if isinstance(left, (int, float)) and left <= 0:
        pct = None
    if mode == "off":
        return {"on": False, "why": "off", "th": SAVER_MIN}
    if mode == "on":
        # manual can also pick a stage (`/saver on 2`). Default stage 3 — same as the hook's default.
        st = mstage if mstage in SAVER_CAP else 3
        return {"on": True, "why": "manual", "th": SAVER_MIN,
                "stage": st, "cap": SAVER_CAP[st]}
    if mode == "pace":
        # ★Goal-burn mode (`{"mode":"pace","until":"19:00"}`) is an instruction to «use it all by that time».
        #   ⚠Turning saver on here by quota % alone makes the screen say the **opposite** of the model — measured 2026-09-21:
        #     the hook was pace·stage 0 while the server saw 56% > 50% and turned on "saver stage 1".
        #     It broke because the inputs differed — the server was not reading this file.
        # ⚠But do not turn it off unconditionally either. The hook swaps the denominator from «until reset» to «until goal» and
        #   **re-derives** the stage (`stage_of(p, pace_min, floor=False)` in `saver.py`) — burning faster than the goal
        #   raises a stage even in pace. The hook is the source of truth for that decision. Do not recompute here
        #   (the denominator `pace_min` does not exist in this file — computing it would disagree again).
        # ⚠If the snapshot is missing or stale, do not turn on — **unknown does not block** (same rule as the `pct` guard above).
        st = _saver_hook_stage("pace") or 0
        out = {"on": st in SAVER_CAP, "why": "pace", "th": SAVER_MIN,
               "pct": int(pct) if isinstance(pct, (int, float)) else None}
        if st in SAVER_CAP:
            out["stage"], out["cap"] = st, SAVER_CAP[st]
        return out
    # ⚠auto: the hook stages by goal pace (`auto_of`), not by the % table — the table alone said stage 2 while the
    #   hook injected stage 1, so the settings line and the status bar disagreed. Fresh hook verdict wins; the table
    #   is only the fallback when the snapshot is missing or stale.
    hs = _saver_hook_stage("auto")
    st = _saver_stage(pct) if hs is None else (hs if hs in SAVER_CAP and pct is not None else 0)
    if st:
        return {"on": True, "why": "quota", "pct": int(pct), "th": SAVER_MIN,
                "stage": st, "cap": SAVER_CAP[st]}
    return {"on": False, "why": "auto", "th": SAVER_MIN,
            "pct": int(pct) if isinstance(pct, (int, float)) else None}


# ★«Which mode is it now» snapshot (2026-09-21, show the mode on screen too).
#   The hook drops this file on every decision. Read separately because some states `_saver_state` cannot express —
#   `pace` (even burn until the goal time) is a mode only the hook knows.
#   ⚠**Do not import** the hook — `saver.py` runs the hook body at module level (reads stdin and injects).
#     Hence the "read a file snapshot" design.
#   ⚠Path comes from config `saver_view_path`, expanded against the user's home (expanduser) —
#     never join it with `HOME`: that is `~/.mailbox-mcp`, while the hook lives in the user's home.
SAVER_VIEW = os.path.expanduser(CFG.get("saver_view_path") or "~/.claude/hooks/.saver-view.json")
# ⚠Must be **the same value** as the screen's (`SV_STALE` in `PAGE`) — fixing only one side splits the badge from the server decision.
SAVER_VIEW_STALE = 120


def _saver_view():
    """Saver-mode snapshot dropped by the hook (`{at,mode,stage,pct,leftMin,until,paceMin,need,rec,head}`).

    `None` if missing or broken — the screen **just hides** the chip (drawing "headroom" from an empty value would be a lie).
    ⚠Polling (2.5s) calls this every time. One small file, so no cache, but **failures pass silently** —
      an exception leaking here kills the whole `/api/state`."""
    try:
        with open(SAVER_VIEW, encoding="utf-8") as f:
            d = json.load(f)
        return _saver_levels_clean(d) if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None      # missing or mid-write snapshot: the chip just hides


def _saver_strs(v, n, ln):
    """List of at most n non-empty strings of at most ln chars, or None."""
    if not isinstance(v, list) or not 0 < len(v) <= n:
        return None
    if not all(isinstance(x, str) and 0 < len(x) <= ln for x in v):
        return None
    return list(v)


def _saver_levels_clean(d):
    """Keep the hook's `levels` / `how` (static level table) only when well-formed; drop each key otherwise.

    ⚠The snapshot is a file another program writes — sizes are capped so a bad file cannot bloat /api/state."""
    lv = d.get("levels")
    out = None
    if isinstance(lv, list) and 0 < len(lv) <= 8:
        out = []
        for e in lv:
            if not isinstance(e, dict):
                out = None
                break
            n, cap, rs = e.get("lv"), e.get("cap"), _saver_strs(e.get("rules"), 12, 120)
            if not (isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 9) or rs is None \
               or not (cap is None or (isinstance(cap, int) and not isinstance(cap, bool) and 0 <= cap <= 99)):
                out = None
                break
            out.append({"lv": n, "cap": cap, "rules": rs})
    if out:
        d["levels"] = out
    else:
        d.pop("levels", None)
    how = _saver_strs(d.get("how"), 8, 240)
    if how:
        d["how"] = how
    else:
        d.pop("how", None)
    return d


def _saver_view_tag(d):
    """File tag for an account's snapshot. ⚠The hook computes the same formula — change both or neither."""
    return hashlib.sha1(os.path.realpath(d).encode(), usedforsecurity=False).hexdigest()[:10]


def _saver_views():
    """{label: view} — `.saver-view-<tag>.json` next to SAVER_VIEW per non-primary account; missing/broken skipped."""
    out = {}
    for r in claude_accounts():
        if r.get("primary") or not r.get("dir"):
            continue
        p = os.path.join(os.path.dirname(SAVER_VIEW), ".saver-view-%s.json" % _saver_view_tag(r["dir"]))
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(d, dict):
            out[r["label"]] = _saver_levels_clean(d)
    return out


def _saver_hook_stage(mode):
    """Stage the hook last decided for `mode`, or None if the snapshot is missing, stale or for another mode."""
    v = _saver_view() or {}
    if v.get("mode") != mode or (time.time() - (v.get("at") or 0)) > SAVER_VIEW_STALE:
        return None
    try:
        return int(v.get("stage") or 0)
    except (TypeError, ValueError):
        return None
