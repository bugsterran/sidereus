"""Server self-status: health() banner data and selfcheck() against the official session list."""
import json
import os
import re
import time
from sidereus import claude_roots
from sidereus.config import CFG
from sidereus.warn import SOFT_WIN_S, WARN_TTL_S, _SOFT, _THREAD_DEAD, _WARN_LOG, _warn_lock, warn_once
from sidereus.ident import _sid8
from sidereus.live import (_STALE_LABEL, _STALE_SHOW_S, _sid_claim_stale, _stale, _stale_lock, agent_view,
                        mailbox_watches, sid_alive)
from sidereus.live_probe import agent_view_unknown
from sidereus.ext import ext_hook_check
from sidereus.sess_clear import clear_links

# Warnings the user can act on stay on the strip, with what to do; key -> action (None = the text already says it).
#   Keys ending in ':' are prefixes. ⚠Any key not listed is demoted to `diag` (logged, not drawn) — add a key here only with an action.
_DISK = "check free disk space and permissions of the data folder"
_FILE = "fix or remove that file"
BANNER_KEEP = {
    "thread:": "restart Sidereus",
    "hooks:": None,
    "agents-nobin": "install Claude Code or add it to PATH",
    "agents": "run `claude agents --json` in a terminal to see why",
    "selfcheck-dead": None, "selfcheck-live": None,
    "pref:": _FILE, "feature:": _FILE, "ui-prefs-read": _FILE,
    "prefs-write": _DISK, "card": _DISK, "cardread": _DISK, "cardread1": _DISK, "cardtrim": _DISK,
    "bgdrop": _DISK, "ext-save": _DISK, "ext-runs-save": _DISK, "winsave": _DISK, "bus": _DISK,
}


def _keep(key):
    """(kept, action) for a warning key — exact match first, then ':' prefixes."""
    key = key or ""
    if key in BANNER_KEEP and not key.endswith(":"):
        return True, BANNER_KEEP[key]
    for k, act in BANNER_KEEP.items():
        if k.endswith(":") and key.startswith(k):
            return True, act
    return False, None


def _with_action(w, act):
    """Copy of a warning with the action appended to msg/msgEn/tv (the log entry itself is not changed)."""
    w = dict(w)
    if act:
        w["msgEn"] = (w.get("msgEn") or w.get("msg") or "") + " · " + act
        w["msg"] = (w.get("msg") or "") + " · " + act
        w["tv"] = list(w.get("tv") or []) + [{"msg": act}]
    return w


PERM_HOOK_CHECK_S = 300
_perm_chk = {"at": 0.0, "mt": {}}   # throttle + per-settings-file (mtime, ok) memo


def _has_perm_hook(cfg):
    """Settings carry a Notification command naming perm_mark.py, or enable the Sidereus plugin (which ships it)."""
    if not isinstance(cfg, dict):
        return False
    plugs = cfg.get("enabledPlugins") if isinstance(cfg.get("enabledPlugins"), dict) else {}
    if any(isinstance(k, str) and k.split("@")[0] == "sidereus" and v for k, v in plugs.items()):
        return True
    hooks = cfg.get("hooks") if isinstance(cfg.get("hooks"), dict) else {}
    groups = hooks.get("Notification") if isinstance(hooks.get("Notification"), list) else []
    return any("perm_mark.py" in str(h.get("command") or "")
               for g in groups if isinstance(g, dict) and isinstance(g.get("hooks"), list)
               for h in g["hooks"] if isinstance(h, dict))


def perm_hook_check(now=None):
    """Warn per signed-in account whose settings.json lacks the perm_mark hook. Returns missing labels (tests).

    ⚠Reads hook names only, never the file's values (it may hold API keys)."""
    now = now or time.time()
    if now - _perm_chk["at"] < PERM_HOOK_CHECK_S:
        return None
    _perm_chk["at"] = now
    miss = []
    for a in claude_roots.accounts():
        path = os.path.join(a["dir"], "settings.json")
        try:
            mt = os.stat(path).st_mtime
        except OSError:
            mt = -1.0
        # An account with no settings.json and no projects/ was never used — no warning on a fresh install.
        if mt < 0 and not os.path.isdir(os.path.join(a["dir"], "projects")):
            continue
        memo = _perm_chk["mt"].get(path)
        if memo is None or memo[0] != mt:
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except (OSError, ValueError):
                cfg = None
            memo = (mt, _has_perm_hook(cfg))
            _perm_chk["mt"][path] = memo
        if not memo[1]:
            miss.append(a["label"])
            warn_once("hooks:perm_mark:" + a["label"],
                      "Account {name} settings lack the perm_mark Notification hook — «Awaiting approval» will not show"
                      " — run `python3 -m sidereus setup-claude` or install the plugin",
                      vars={"name": a["label"]})
    return miss


def health():
    """Server self-status — surfaces **silent failures up to the screen** (2026-09-07).

    ★Why needed: 26 `warn_once` sites went only to stderr and launchd piled them in `viewer.err`, but
      nobody read it. That file held 71 warning lines + 3 stack traces, one of which was
      the `TypeError` (chat_server.py:3259) that killed `_wkuse_loop` — the screen said nothing and
      the user noticing nothing changed was the detector. Ending that is this field's purpose.
    ⚠**Emit absolute time (`at`) only.** If the server computes elapsed seconds they freeze between polls (2.5s),
      and this file does that nowhere — elapsed is counted by the screen with `agoAt`."""
    try:
        ext_hook_check()         # throttled inside (HOOK_CHECK_S); must run before _WARN_LOG is read below
    except Exception as e:
        warn_once("hooks-check", "Hook settings check failed ({err})", soft=True, vars={"err": type(e).__name__})
    try:
        perm_hook_check()        # throttled inside (PERM_HOOK_CHECK_S)
    except Exception as e:      # own key: one shared key would hide which check failed
        warn_once("hooks-check-perm", "Hook settings check failed ({err})", soft=True, vars={"err": type(e).__name__})
    with _warn_lock:
        dead = sorted(_THREAD_DEAD.values(), key=lambda x: -(x.get("at") or 0))
        # ★A warning that did not recur within `WARN_TTL_S` **is treated as resolved** (see constant comment above).
        #   It is not deleted from `_WARN_LOG` — if it recurs `at` updates and it shows again as-is.
        _cut = time.time() - WARN_TTL_S
        warns, diag = [], []
        for w in _WARN_LOG:
            if (w.get("at") or 0) < _cut:
                continue
            kept, act = _keep(w.get("key"))
            if kept:
                warns.append(_with_action(w, act))
            else:
                diag.append({"key": w.get("key"), "at": w.get("at"), "msg": w.get("msg")})
        warns, diag = warns[-20:], diag[-20:]
        dead = [dict(d, act="restart Sidereus") for d in dead]
        # ★Carry the tier-1 (soft) tally **thinly** (2026-09-07) — even before promotion there must be a way to check
        #   "how many times it was slow now" (`viewer.err` has only one line per window). Key·count·last time only.
        #   ⚠**Do not draw it as a warning.** Doing so defeats the purpose of "removing unactionable warnings from the banner"
        #     — JS draws only `warns`/`dead`, so this field adds nothing to the screen (JS unchanged).
        #   Entries that left the window (`SOFT_WIN_S`) are already over, so dropped.
        _scut = time.time() - SOFT_WIN_S
        soft = sorted(({"key": k, "n": v.get("n") or 0, "last": v.get("last") or 0}
                       for k, v in _SOFT.items() if (v.get("last") or 0) >= _scut),
                      key=lambda x: -x["last"])
    # ★**Staleness**, separate from tier 2 (2026-09-21) — puts "currently using the previous value" on the banner.
    #   ⚠`at` is **the last success time (absolute)**. Elapsed seconds are counted by the screen per the ⚠ above.
    #   ⚠Only fallbacks taken within the recent `_STALE_SHOW_S` — collectors not called since are not left as stale.
    _mcut = time.time() - _STALE_SHOW_S
    with _stale_lock:
        stale = sorted(({"key": k, "label": _STALE_LABEL.get(k, k), "at": v[0]}
                        for k, v in _stale.items() if (v[1] or 0) >= _mcut),
                       key=lambda x: x["at"])
    return {"dead": dead, "warns": warns, "diag": diag, "soft": soft, "stale": stale}


# ── self-check ────────────────────────────────────────────────────────────────
# ★★**The detector must not be the user** (reporting each bug's symptoms by hand is too costly).
#   Almost all defects in this file were **decisions silently wrong**, and
#   the screen said nothing at the time (the health banner only surfaces exceptions·slow fetches). Measured 2026-09-08:
#   dead sessions showed as `Awaiting input` and live sessions as `Ended`, while `health` was entirely empty.
#   ⇒ **Compare the official lookup (`agent_view`) with our rows every poll** and put mismatches on the banner. The comparison is now
#     «ours vs official», not «guess vs guess», so the signal does not lie.
#   ⚠**Do not declare** — at the moment a session just launched or just ended they mismatch normally (the official lookup
#     can be stale by `AGENTS_TTL`). So alert **only when the same mismatch persists for `SELF_GRACE_S` or longer**.
#     Instead of the two extremes this file repeatedly hit (silence=death / wait for notification), **persistence** is the evidence.
#   ⚠If the official lookup is None (unknown), **make no decision at all** — do not warn on the basis of unknown.
SELF_GRACE_S = 75           # if a mismatch persists this long, treat as «the decision is wrong» (9x AGENTS_TTL of 8s)
# cwd of sessions hooks launch for their own work — outside our monitoring scope (see ★ inside `selfcheck` above).
#   ⚠Do not exclude whole temp folders (`/private/var/folders`·`/private/tmp`) — subagent
#     worktrees live in `/private/tmp/claude-501/…` and those are sessions that **must be shown**.
# Patterns are regexes from config (hook_session_patterns); empty list or a bad regex matches nothing.
try:
    _HOOK_SESS_RE = re.compile("|".join(CFG.get("hook_session_patterns") or []) or r"(?!)")
except re.error:
    _HOOK_SESS_RE = re.compile(r"(?!)")
_self_since = {}            # check key -> time first mismatched


def _self_hold(key, bad):
    """Has the mismatch persisted for `SELF_GRACE_S` or longer. Clears the memory once resolved (no list without expiry)."""
    now = time.time()
    if not bad:
        _self_since.pop(key, None)
        return False
    t0 = _self_since.setdefault(key, now)
    return now - t0 >= SELF_GRACE_S


def _pid_of(av, sid):
    """pid (str) whose official entry carries `sid`, or ""."""
    for pid, it in av.items():
        if isinstance(it, dict) and it.get("sessionId") == sid:
            return str(pid)
    return ""


def _cleared_in_cwd(off, cwd):
    """An official entry in `cwd` whose sid has a newer sibling in that cwd slug (= /clear successor exists)."""
    if not cwd:
        return False
    return any(_sid_claim_stale(s, cwd) for s, it in off.items() if (it.get("cwd") or "") == cwd)


def selfcheck(rows):
    """Compare our decisions ↔ the official session list. Persistent mismatches go to the health banner via `warn_once`.

    ⚠Failure does not kill the poll — a self-check that prevents the screen from rendering would defeat its purpose."""
    try:
        av = agent_view()
        if av is None:
            return                    # unknown — no decision
        off = {}
        for it in av.values():
            sid = (it.get("sessionId") or "") if isinstance(it, dict) else ""
            if not sid:
                continue
            # ★**A hook's own launched session is not a comparison target** (measured 2026-09-09).
            #   A review hook launches **its own Claude session** in a temp folder (`…/T/<hook>-XXXXXX`).
            #   It shows in `claude agents --json` but is **never in** our session list —
            #   it is not a monitoring target and leaves no transcript (measured: `f6a7b8c9` had no file in any project
            #   folder). So (1) caught it every time as "official says running but not on screen", and
            #   that was the `selfcheck-dead` on today's banner (14 lines accumulated).
            #   ⚠**Do not filter `agent_view()` itself** — pid↔sid attribution (`live_cwds`) uses that list
            #     as-is, so removing it there would leak hook processes back into the path tally. Exclude here only.
            #   ⚠If the folder name changes the warning returns — that is correct behavior (unknowns are not silently passed).
            if _HOOK_SESS_RE.search((it.get("cwd") or "") if isinstance(it, dict) else ""):
                continue
            off[sid] = it
        # ⚠Claude rows only — the official list is Claude Code's registry; ext rows (gm/cx) use `ext_gone_check`.
        ours = {r.get("sid"): r for r in rows
                if r.get("sid") and r.get("plat") in (None, "", "cc")}
        # ⚠A row whose account's lookup is unknown is not compared — absence from a list that failed proves nothing.
        blind = agent_view_unknown()
        skip = {sid for sid, r in ours.items() if (r.get("acct") or "") in blind}
        # (1) official says alive but we say ended (or no row at all) — `bb22bb22` on 2026-09-08 looked like this
        # ⚠After /clear `claude agents` keeps the pre-clear sid of the same pid — those pairs are not mismatches.
        links = [ln for ln in (clear_links() or []) if isinstance(ln, dict) and str(ln.get("pid") or "") in av]
        cl_old = {(str(ln.get("pid")), ln.get("old")) for ln in links}
        cl_new = {ln.get("new") for ln in links}
        ghost = [sid for sid in off
                 if (sid not in ours or ours[sid].get("state") == "done")
                 and sid not in skip and (str(_pid_of(av, sid)), sid) not in cl_old]
        if _self_hold("sc-dead", bool(ghost)):
            warn_once("selfcheck-dead",
                      "Status uncertain for {n} sessions — running per Claude, but missing or ended here: {sids}"
                      + (" +{more} more" if len(ghost) > 4 else "") + " — check those sessions in their terminal",
                      vars={"n": len(ghost), "sids": ", ".join(_sid8(x) for x in sorted(ghost)[:4]),
                            "more": len(ghost) - 4})
        # (2) we say alive but not in the official list — ghost rows (the old home-dir looked like this)
        #   ★**Sessions we confirmed directly by sid are not ghosts** (measured 2026-09-09 · warnings kept reappearing
        #     even after being dismissed). At that moment, actually:
        #       pid 41005`claude --resume a7b8c9d0…` (cwd `~/work/proj-C/admin`) was alive for 13 min
        #       but that pid was not in `claude agents --json` ⇒ the official list was incomplete and
        #       **the screen was right.** Yet (2) caught it as a ghost and refreshed its age every poll (2.5s)
        #       — even after the user dismissed it with ✕ it came back 2.5s later, and nothing could be done.
        #   ⇒ If `sid_alive` (argv `--resume` claims filtered by `_resume_stale` — the very evidence
        #     `_sess_state` uses) is true, exclude it from the comparison. The original target (old home-dir ghost rows) matched
        #     only by path with **no** sid evidence, so it is still caught.
        zomb = [sid for sid, r in ours.items()
                if r.get("state") not in ("done", "unknown") and sid not in off and sid not in skip
                and not sid_alive(sid) and sid not in cl_new and not _cleared_in_cwd(off, r.get("cwd"))]
        if _self_hold("sc-live", bool(zomb)):
            warn_once("selfcheck-live",
                      "Status uncertain for {n} sessions — could not confirm they are running: {sids}"
                      + (" +{more} more" if len(zomb) > 4 else "") + " — check those sessions in their terminal",
                      vars={"n": len(zomb), "sids": ", ".join(_sid8(x) for x in sorted(zomb)[:4]),
                            "more": len(zomb) - 4})
        # (3) running watchers ↔ the screen's watcher rows. Measured 2026-09-08: a watcher attached to **an ended row**, and that row emptied mon,
        #    so one running watcher (Sidereus) vanished from the screen entirely — counting catches it.
        mw = mailbox_watches()
        if mw is not None:
            nproc = sum(len(v) for v in mw.values())
            nshown = sum(len(r.get("mon") or []) for r in rows)
            if _self_hold("sc-mon", nshown < nproc):
                warn_once("selfcheck-mon", "Only {shown} of {n} running mailbox watches are attached on screen"
                          " — a watch may sit on an ended row", vars={"shown": nshown, "n": nproc})
    except Exception as e:
        warn_once("selfcheck-err", "Self-check failed ({err})", vars={"err": f"{type(e).__name__}: {e}"})
