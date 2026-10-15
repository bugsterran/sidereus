"""Per-project cost from the local usage index."""
import json
import os
import subprocess
import threading
import time
from sidereus.warn import _LOOP_ERR, warn_once
from sidereus.ident import _slug, bin_path, rich_env
from sidereus.usage import USAGE_LOCAL, _ccusage_lock, _cost4, _uidx, _uidx_lock, _uidx_refresh
from sidereus.usage_index import _uidx_snap


# ★Per-project cumulative cost. `sessionId` in `ccusage session --json` is not the real session UUID but
#   **the project slug** (measured 2026-08-24: `-Users-me-Infra-repo-A` form + a `subagents` bucket).
#   So it is a per-project total, not "per session", and the screen label says so — labeling it per-session
#   would be false as two sessions of the same project would show the same value.
#   ccusage is slow (seconds), so it is never called on the polling path; refreshed in the background only.
_projcost = {"at": 0, "by": {}, "subagents": 0.0}
_projcost_lock = threading.Lock()


def _projcost_local():
    """Build all-time per-project cost from a **local index** (2026-09-11 · `ccusage session` 46s → 0.05s).
    ★The subagent split criterion differs: ccusage uses the `sessionId == "subagents"` bucket,
      here it is the **path** (`…/<session>/subagents/*.jsonl`) — same file set, so the totals match.
    ⚠Models with unknown pricing cost 0 (`_price` does `warn_once`) — tokens are still counted."""
    _uidx_refresh()
    with _uidx_lock:
        items = [(fp, e.get("sl") or "?", _uidx_snap(e.get("h"))) for fp, e in _uidx["files"].items()]
    by, sub = {}, 0.0
    sep = os.sep + "subagents" + os.sep
    for fp, slug, h in items:
        c = 0.0
        for mm in h.values():
            for mdl, v in mm.items():
                c += _cost4(mdl, v)
        if not c:
            continue
        if sep in fp:
            sub += c
        else:
            by[slug] = by.get(slug, 0.0) + c
    with _projcost_lock:
        _projcost.update({"at": time.time(), "by": by, "subagents": sub})


def _projcost_fetch():
    """Default is the local version above. The ccusage path below runs only when `USAGE_LOCAL = False`, **for cross-checking**."""
    if USAGE_LOCAL:
        return _projcost_local()
    try:
        with _ccusage_lock:      # overlapping with another ccusage makes both exceed the timeout
            r = subprocess.run([bin_path("ccusage"), "session", "--json"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=180, env=rich_env())
        # ★Do not swallow failures — without rc·stderr the cause is mashed into JSONDecodeError.
        #   Measured 2026-08-24: the shebang's `node` was not found; the reason was only in stderr and stdout was empty.
        if r.returncode != 0 or not (r.stdout or "").strip():
            warn_once("projcost-rc", "ccusage session failed (rc={rc}): {err}",
                      vars={"rc": r.returncode, "err": (r.stderr or "")[:160]})
            return
        rows = (json.loads(r.stdout) or {}).get("sessions") or []
    except Exception as e:
        warn_once("projcost", "Could not read per-project cost ({err}) — cost display is empty",
                  vars={"err": type(e).__name__})
        return
    # ⚠This aggregation loop is **outside** the try above — if ccusage changes element shape (string·None), `.get`/`float`
    #   blows up, and even with the loop guard it blows up at the same spot every cycle, freezing cost display forever.
    #   ⇒ Skip only the odd **elements**. If the wrapper is not a list, leave it «unknown» and do not preserve the old value.
    if not isinstance(rows, list):
        warn_once("projcost-rows", "ccusage session 'sessions' is not a list ({err}) — cost display is empty",
                  vars={"err": type(rows).__name__})
        return
    by, sub = {}, 0.0
    for r in rows:
        if not isinstance(r, dict):
            warn_once("projcost-row", "A ccusage session row is not an object ({err}) — skipping that row",
                      vars={"err": type(r).__name__})
            continue
        sid = str(r.get("sessionId") or "")
        try:
            c = float(r.get("totalCost") or 0)
        except (TypeError, ValueError):
            warn_once("projcost-cost", "A ccusage session cost is not a number — skipping that row")
            continue
        if sid == "subagents":
            sub += c
        elif sid:
            by[sid] = by.get(sid, 0.0) + c
    with _projcost_lock:
        _projcost.update({"at": time.time(), "by": by, "subagents": sub})


def _projcost_loop():
    while True:
        try:
            _projcost_fetch()
            _LOOP_ERR.pop("projcost", None)
            time.sleep(120)      # ★local index, so cheap (0.05s) — was 10 min when ccusage took 46s
        except Exception as e:
            warn_once("loop:projcost", "Per-project cumulative cost stopped refreshing — {err}",
                      vars={"err": f"{type(e).__name__}: {e}"[:111]})
            _LOOP_ERR["projcost"] = {"at": time.time(), "err": f"{type(e).__name__}: {e}"[:160]}
            time.sleep(60)          # ⚠the exception path must sleep too — otherwise it becomes a tight infinite loop
            continue


def _projcost_of(cwd):
    """Cumulative cost (USD) for this path. 0 if unknown."""
    if not cwd:
        return 0.0
    with _projcost_lock:
        return _projcost["by"].get(_slug(cwd), 0.0)
