"""«sidereus-state v1» — the public, versioned projection behind `GET /api/v1/state` (schema `docs/schema/sidereus-state.v1.json`).

Built straight from `sessions_cached` + `quota` + `_saver_state` + rooms.json — never from the full `state()` (3 MB).
⚠Metadata only: every field is copied through an allow-list below, never by spreading a row — a key added to
  `sessions._session_row` (e.g. `targ`, `blocked`) must not reach this API by accident.
"""
import json
import os
import threading
import time

from sidereus.config import ASSET_DIR
from sidereus.features import state_off
from sidereus.bus import _load
from sidereus.redact import redact_rooms
from sidereus.sessions import sessions_cached
from sidereus.quota import quota
from sidereus.saver import _saver_state
from sidereus.state import STATE_COLD_S, STATE_FRESH_S, STATE_WAIT_S

V1_VERSION = 1
V1_TTL = 1.0           # same freshness as /api/state's shared body cache
V1_LAB_MAX = 200       # one-line labels (subagent lab · room topic)
V1_SCHEMA = os.path.join(ASSET_DIR, "docs", "schema", "sidereus-state.v1.json")
V1_CACHE = {"at": None, "obj": None}
V1_LOCK = threading.Lock()   # ⚠guards V1_CACHE only — the build runs outside it

_S_STR = ("sid", "id", "plat", "project", "cwd", "branch", "model", "state", "kind", "tool")
_S_INT = ("ctx", "win", "ageSec")


def _now():
    return time.time()


def _int(v):
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _str(v, n=None):
    s = v if isinstance(v, str) else ""
    return s[:n] if n else s


def _sub(a):
    out = {"lab": _str(a.get("lab"), V1_LAB_MAX), "min": _int(a.get("min"))}
    for k in ("aid", "tid"):
        if isinstance(a.get(k), str) and a[k]:
            out[k] = a[k]
    if isinstance(a.get("idle"), int) and not isinstance(a.get("idle"), bool):
        out["idle"] = a["idle"]
    return out


def _session(r):
    s = {k: _str(r.get(k)) for k in _S_STR}
    s["tool"] = s["tool"][:64]
    s.update({k: _int(r.get(k)) for k in _S_INT})
    p = r.get("plm")
    if isinstance(p, dict):
        s["plm"] = {"name": _str(p.get("name"), 40), "title": _str(p.get("title"), 40), "age": _int(p.get("age"))}
    # ⚠`plrun` (pl_runs) is screen-only: the v1 schema is additionalProperties:false, adding it is a schema change.
    s["sub"] = [_sub(a) for a in (r.get("sub") or []) if isinstance(a, dict)]
    if isinstance(r.get("acct"), str) and r["acct"]:   # non-primary Claude root label only (absent = primary)
        s["acct"] = r["acct"][:24]
    return s


def _quota(q):
    q = q if isinstance(q, dict) else {}
    out = {}
    for k in ("five_hour", "seven_day"):
        v = q.get(k)
        if isinstance(v, dict):
            out[k] = {"pct": v.get("pct") if isinstance(v.get("pct"), (int, float)) else None,
                      "resets_at": v.get("resets_at") if isinstance(v.get("resets_at"), str) else None,
                      "leftSec": v.get("leftSec") if isinstance(v.get("leftSec"), int) else None}
    if not out:
        return None
    pl = q.get("plan")
    if isinstance(pl, dict):   # ⚠tier codes only — `org` is an account identifier, left out of the public API
        out["plan"] = {k: pl[k] for k in ("tier", "seat") if isinstance(pl.get(k), str)}
    return out


def _saver(q):
    fh = (q or {}).get("five_hour") or {}
    s = _saver_state(fh.get("pct"), fh.get("leftSec"))
    if not isinstance(s, dict):
        return None
    pct = s.get("pct")
    return {"on": bool(s.get("on")), "pct": int(pct) if isinstance(pct, (int, float)) else None,
            "stage": _int(s.get("stage"))}


def _rooms(raw):
    out = {}
    for name, r in (redact_rooms(raw).items() if isinstance(raw, dict) else ()):
        if not isinstance(name, str) or not isinstance(r, dict):
            continue
        out[name] = {"created": _int(r.get("created")), "owner": _str(r.get("owner")),
                     "members": [m for m in (r.get("members") or []) if isinstance(m, str)],
                     "topic": _str(r.get("topic"), V1_LAB_MAX),   # free text, masked by redact_rooms as in /api/state
                     "invited": [m for m in (r.get("invited") or []) if isinstance(m, str)]}
    return out


def _build():
    off = state_off()
    q = quota()
    out = {"schema": "sidereus-state", "version": V1_VERSION, "at": int(_now())}
    if "sessions" not in off:
        rows = sessions_cached(wait=STATE_WAIT_S, max_age=STATE_FRESH_S, cold_wait=STATE_COLD_S)[0]
        out["sessions"] = [_session(r) for r in rows if isinstance(r, dict)]
    if "quota" not in off:
        out["quota"] = _quota(q)
    if "saver" not in off:
        out["saver"] = _saver(q)
    if "rooms" not in off:
        out["rooms"] = _rooms(_load("rooms.json", {}))
    out["x"] = {}
    return out


def build(max_age=V1_TTL):
    """sidereus-state v1 object (cached `max_age` s). ⚠Shared between callers — do not mutate."""
    now = _now()
    with V1_LOCK:
        if V1_CACHE["at"] is not None and 0 <= now - V1_CACHE["at"] < max_age:
            return V1_CACHE["obj"]
    obj = _build()
    with V1_LOCK:
        V1_CACHE["at"], V1_CACHE["obj"] = now, obj
    return obj


def load_schema(path=None):
    with open(path or V1_SCHEMA, encoding="utf-8") as f:
        return json.load(f)


_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _type_ok(v, t):
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES.get(t, ()))


def _check(v, s, root, path, errs):
    s = _resolve_ref(s, root)
    if not isinstance(s, dict):
        return
    t = s.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_type_ok(v, x) for x in ts):
            errs.append("%s: expected %s, got %s" % (path, "|".join(ts), type(v).__name__))
            return
    if "enum" in s and v not in s["enum"]:
        errs.append("%s: %r not in enum" % (path, v))
    if isinstance(v, str) and isinstance(s.get("maxLength"), int) and len(v) > s["maxLength"]:
        errs.append("%s: longer than %d" % (path, s["maxLength"]))
    if isinstance(v, list) and "items" in s:
        for i, it in enumerate(v):
            _check(it, s["items"], root, "%s[%d]" % (path, i), errs)
    if isinstance(v, dict):
        for k in s.get("required") or []:
            if k not in v:
                errs.append("%s: missing required %r" % (path, k))
        props = s.get("properties") or {}
        extra = s.get("additionalProperties", True)
        for k, it in v.items():
            if k in props:
                _check(it, props[k], root, "%s.%s" % (path, k), errs)
            elif extra is False:
                errs.append("%s: unexpected key %r" % (path, k))
            elif isinstance(extra, dict):
                _check(it, extra, root, "%s.%s" % (path, k), errs)


def _resolve_ref(s, root):
    """Follow local `#/a/b` refs only (the schema never points outside itself)."""
    seen = 0
    while isinstance(s, dict) and isinstance(s.get("$ref"), str) and seen < 16:
        ref, seen, node = s["$ref"], seen + 1, root
        if not ref.startswith("#/"):
            return {}
        for part in ref[2:].split("/"):
            node = node.get(part) if isinstance(node, dict) else None
        s = node
    return s


def validate(obj, schema):
    """Errors (list of str) of `obj` against `schema` — stdlib subset: type · required · properties ·
    additionalProperties · items · maxLength · enum · local $ref. [] = valid."""
    errs = []
    _check(obj, schema, schema, "$", errs)
    return errs
