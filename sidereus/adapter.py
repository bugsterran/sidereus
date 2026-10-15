"""CLI adapter contract: one `sidereus/plat_<name>.py` module per external CLI, checked once at import.

`adapter_register(mod)` validates the module and records it in `ADAPTERS` (KEY -> module); `adapter_scan(key, since)`
wraps the runtime scan so a broken adapter yields [] + warn_once instead of a broken poll.
Contract (template: sidereus/plat_TEMPLATE.py.txt), measured against plat_gemini/plat_codex:
- required: PLAT (hook `platform` value), KEY (row key, 2 chars like the logo), NAME, CHILD_LABEL (label of a run a
  Claude session launched), SCAN_MAX (bytes, int),
  root() -> str, path_ok(path) -> bool, scan(since) -> rows, session_msgs(path) -> {id: msg} | None.
  A row: {sid, path, cwd, project, start, kind, msgs, acts} + optional `parent` (subagent chat -> parent sid)
  and `rate` ((ts, {primary/secondary: {pct, win, reset}, plan}) or None). A msg value is the 7-tuple
  (uncached in, out, cache, thought, ts, model, cost USD | None).
- optional: LANE, RULE_FILE, harness_items, hook_settings/hook_gaps/used_since/HOOK_*, cost/PRICE_VER,
  TAIL_READ, TIME_BUDGET_S (default AD_TIME_BUDGET_S).
⚠Adapters read local record files only: no network, no writes, metadata only (never message or tool text).
Owns `ADAPTERS` and `AD_*`.
"""
import time
from sidereus.warn import warn_once

AD_REQUIRED = ("PLAT", "KEY", "NAME", "CHILD_LABEL", "SCAN_MAX", "root", "path_ok", "scan", "session_msgs")
AD_STR = ("PLAT", "KEY", "NAME", "CHILD_LABEL")
AD_RESERVED = frozenset(("cc",))        # Claude is built in (transcripts), never an adapter
AD_ROW_KEYS = ("sid", "path", "cwd", "project", "start", "kind", "msgs", "acts")
AD_TIME_BUDGET_S = 1.0
ADAPTERS = {}


def adapter_register(mod, plats=None):
    """Validate `mod` against the contract and record it; returns `mod` unchanged. Bad or missing keys raise ValueError.
    `plats` = the hook platform -> row key map (ext_store.EXT_PLAT); PLAT must be in it with the same KEY."""
    nm = getattr(mod, "__name__", repr(mod))
    miss = [k for k in AD_REQUIRED if not hasattr(mod, k)]
    if miss:
        raise ValueError("adapter %s: missing %s" % (nm, ", ".join(miss)))
    for k in AD_STR:
        if not isinstance(getattr(mod, k), str) or not getattr(mod, k):
            raise ValueError("adapter %s: %s must be a non-empty str" % (nm, k))
    sm = mod.SCAN_MAX
    if not isinstance(sm, int) or isinstance(sm, bool) or sm <= 0:
        raise ValueError("adapter %s: SCAN_MAX must be a positive int" % nm)
    for k in ("root", "path_ok", "scan", "session_msgs"):
        if not callable(getattr(mod, k)):
            raise ValueError("adapter %s: %s must be callable" % (nm, k))
    if mod.KEY in AD_RESERVED:
        raise ValueError("adapter %s: KEY %r is reserved" % (nm, mod.KEY))
    if plats is not None and plats.get(mod.PLAT) != mod.KEY:
        raise ValueError("adapter %s: PLAT %r -> KEY %r not in EXT_PLAT" % (nm, mod.PLAT, mod.KEY))
    old = ADAPTERS.get(mod.KEY)
    if old is not None and old is not mod:
        raise ValueError("adapter %s: duplicate KEY %r" % (nm, mod.KEY))
    ADAPTERS[mod.KEY] = mod
    return mod


def adapter_scan(key, since=0.0):
    """mod.scan(since) for adapter `key` (or the module itself); an exception becomes warn_once + [] (never a broken poll).
    ⚠Callers pass the PLAT_MODS module, not its KEY: tests swap fake modules into PLAT_MODS only."""
    mod = ADAPTERS.get(key) if isinstance(key, str) else key
    if mod is None:
        return []
    key, name = getattr(mod, "KEY", "?"), getattr(mod, "NAME", "?")
    t0 = time.monotonic()
    try:
        rows = list(mod.scan(since))
    except Exception as e:      # ⚠any adapter bug: one warning, empty result
        warn_once("adapter-scan-%s" % key, "{name} record scan failed: {err}", vars={"name": name, "err": type(e).__name__})
        return []
    dt = time.monotonic() - t0
    if dt > getattr(mod, "TIME_BUDGET_S", AD_TIME_BUDGET_S):
        warn_once("adapter-slow-%s" % key, "{name} record scan is slow ({sec}s)", vars={"name": name, "sec": "%.1f" % dt})
    return rows
