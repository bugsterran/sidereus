"""Side token readers for platforms outside `PLAT_MODS`: hook-sent generation counts (Cursor `stop`, pi children)
from `ext_store._hooktok` and Copilot usage records (plat_copilot). Split out of sidereus/ext_store.py, bodies unchanged.
⚠`_hooktok` is imported by name: ext_store and tests only mutate it in place, never rebind it."""
from sidereus.ext_store import _ext_lock, _hooktok, _tok_sum
from sidereus import plat_copilot   # module access: tests patch `plat_copilot.root` / `msgs_since`


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
    """One session's side messages (same merge as `ext_side_msgs`); {} for anything but Copilot and pi children."""
    if plat not in (plat_copilot.PLAT, "pi"):
        return {}
    with _ext_lock:
        e = _hooktok.get(plat + "|" + str(sid))
        ms = {g: (v[0], v[1], v[2] + v[3], 0, float(v[4]), v[5], None) for g, v in ((e or {}).get("gens") or {}).items()}
    ms.update(plat_copilot.usage_msgs(sid) if plat == plat_copilot.PLAT else {})
    return ms


def ext_side_tok(plat, sid):
    """`ext_tok` shape (total + latest model) from `ext_side_sess`, or None when empty."""
    ms = ext_side_sess(plat, sid)
    if not ms:
        return None
    s = _tok_sum(ms)
    s["model"] = max(ms.values(), key=lambda v: v[4])[5]
    return s
