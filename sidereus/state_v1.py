"""«sidereus-state v1» — the public, versioned projection behind `GET /api/v1/state` (schema `docs/schema/sidereus-state.v1.json`).

Built straight from `sessions_cached` + `quota` + `_saver_state` + rooms.json — never from the full `state()` (3 MB).
⚠Metadata only: every field is copied through an allow-list below, never by spreading a row — a key added to
  `sessions._session_row` (e.g. `targ`, `blocked`) must not reach this API by accident.
"""
import json
import os
import re
import threading
import time

from sidereus.config import ASSET_DIR, CODE_DIR, DATA_DIR
from sidereus.memo import BoundedMemo
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
V1_PAST_MAX = 5        # = sidereus/pl_runs.py PLR_PAST_MAX: earlier runs per name
V1_ROWS_MAX = 8        # = sidereus/pl_runs.py PLR_MAX: head runs per session row
V1_DEF_MAX = 65536     # bytes of one pipeline definition; larger -> unreadable (verdict unknown)
V1_DEFS = BoundedMemo(64)   # definition path -> (titles | None, builtin), stamped (st_mtime_ns, st_size)
_V1_NAME = re.compile(r"[a-z0-9-]{1,40}")
_V1_AGENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}")   # = pipeline_schema._AGENT
V1_MODELS = ("inherit", "opus", "sonnet", "haiku")          # = pipeline_schema.MODELS
V1_EFFORTS = ("low", "medium", "high", "xhigh", "max")      # = pipeline_schema.EFFORTS
V1_RENAMED = {"\ucd5c\uc885 \uac80\uc99d": "\uc7ac\uac80\uc99d"}   # = pipeline_schema.RENAMED (duplicate check renames first)
_V1_WS = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"   # = pipeline_schema._JS_WS
_V1_PASS = ("done", "skip")

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


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e18 else 0


def verdict(S, end, stop, titles, cur, past=False):
    """'pass' | 'fail' | 'unknown' — same rule as 48n visitVerdict (vectors: tests/fixtures/verdict_vectors.json).
    ⚠A past run with `stop` None was archived before the hook kept it: never pass (_close_stale turns a stopped cur stage into done)."""
    S = S if isinstance(S, dict) else {}
    if any(isinstance(s, dict) and s.get("o") == "fail" for s in S.values()):
        return "fail"
    if past and stop is None:
        return "unknown"
    last = titles[-1] if isinstance(titles, list) and titles else None
    c = S.get(cur) if isinstance(last, str) and isinstance(cur, str) and cur == last else None
    ok = isinstance(end, (int, float)) and not isinstance(end, bool) and end > 0
    return "pass" if ok and not stop and isinstance(c, dict) and c.get("o") in _V1_PASS else "unknown"


def _def_dirs():
    """Dirs shipping Sidereus `"builtin": true` pipelines (run on a target repo), CODE_DIR first; DATA_DIR too, like pipeline._bi_owner."""
    return (CODE_DIR, DATA_DIR)


def _ulen(x):
    return len(x.encode("utf-16-le", "surrogatepass")) // 2   # JS .length, as pipeline_schema counts


def _line(x, mx):
    return isinstance(x, str) and 0 < _ulen(x) <= mx and "\r" not in x and "\n" not in x and bool(x.strip(_V1_WS))


def _int_in(x, lo, hi):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and float(x).is_integer() and lo <= x <= hi


def _def_ok(P, name):
    """Subset of pipeline_schema.validate deciding whether the strip gets titles (pipeline._row adds `stages` only when
    it passes): v, name == stem, title, defaults, 1..20 stages with a unique one-line title and an agent.
    ⚠Never more lenient on these; the rest (optional stage keys, custom-stage task, guards) is left out —
    pipeline_schema belongs to the pipeline feature (feature_couplings). tests/test_state_v1.py pins MODELS/EFFORTS."""
    if not (isinstance(P, dict) and _int_in(P.get("v"), 1, 1) and P.get("name") == name and _line(P.get("title"), 80)):
        return False
    D = P.get("defaults") if isinstance(P.get("defaults"), dict) else {}
    if D.get("model") not in V1_MODELS or ("effort" in D and D["effort"] not in V1_EFFORTS) or not _int_in(D.get("retry"), 0, 3):
        return False
    S = P.get("stages")
    if not (isinstance(S, list) and 0 < len(S) <= 20 and all(isinstance(s, dict) for s in S)):
        return False
    ts = [s.get("title") for s in S]
    return (all(_line(t, 40) for t in ts) and len({V1_RENAMED.get(t, t) for t in ts}) == len(ts)
            and all(isinstance(s.get("agent"), str) and _V1_AGENT.fullmatch(s["agent"]) for s in S))


def _read_def_bytes(fp):
    with open(fp, "rb") as f:
        return f.read(V1_DEF_MAX + 1)


def _def_at(d, name):
    """(exists, titles | None, builtin) of <d>/.claude/pipelines/<name>.json.
    ⚠Read here, not via pipeline._read_pipe: state_v1 belongs to no feature manifest (feature_couplings)."""
    if not (isinstance(d, str) and os.path.isabs(d)):
        return False, None, False
    pd = os.path.join(d, ".claude", "pipelines")
    fp = os.path.join(pd, name + ".json")
    try:
        st = os.stat(fp)
    except OSError:
        return False, None, False
    # ⚠a symlinked repo root resolves; a pipelines dir or file pointing outside the project is refused
    rpd = os.path.realpath(pd)
    if rpd != os.path.join(os.path.realpath(d), ".claude", "pipelines") or os.path.dirname(os.path.realpath(fp)) != rpd:
        return True, None, False
    stamp = (st.st_mtime_ns, st.st_size)
    hit = V1_DEFS.get(fp, stamp=stamp)
    if hit is not None:
        return (True,) + hit
    titles, bi = None, False
    try:
        b = _read_def_bytes(fp)
        P = json.loads(b.decode("utf-8")) if len(b) <= V1_DEF_MAX else None
    except (OSError, ValueError):
        P = None
    bi = isinstance(P, dict) and P.get("builtin") is True   # ⚠valid or not, like pipeline._bi_owner: an invalid builtin still owns the name
    if _def_ok(P, name):
        titles = [s["title"] for s in P["stages"]]
    V1_DEFS.put(fp, (titles, bi), stamp=stamp)
    return True, titles, bi


def _titles(proj, name, hints, memo):
    """Stage titles of pipeline `name` or None (unknown). Order: proj, then a builtin in _def_dirs(), then the hints;
    the first file that exists decides (invalid -> None), like /api/pipelines local -> builtin owner -> run hints."""
    if not (isinstance(name, str) and _V1_NAME.fullmatch(name)):
        return None
    key = (proj, name, tuple(hints))
    if key in memo:
        return memo[key]
    out, dirs = None, _def_dirs()
    ex, t, bi = _def_at(proj, name)
    if ex:
        # ⚠a builtin in CODE_DIR (dirs[0]) is hidden from its own list (pipeline._listed) and never borrowed: no titles there
        out = None if bi and dirs and isinstance(proj, str) and os.path.realpath(proj) == os.path.realpath(dirs[0]) else t
    else:
        for d in dirs:
            ex, t, bi = _def_at(d, name)
            if ex and bi:
                out = t
                break
        else:
            for h in hints:
                ex, t, _bi = _def_at(h, name)
                if ex:
                    out = t
                    break
    memo[key] = out
    return out


def _run(q, name, titles, past):
    """One allow-listed run; ⚠never spread `q` — lab, ag, from, stop, proj, sid stay out (rule 1)."""
    S = q.get("stages") if isinstance(q.get("stages"), dict) else {}
    stop = None if past and q.get("stop") is None else _num(q.get("stop"))
    end = _num(q.get("end"))   # ⚠stamped end only: a past run's t1 dates its idle close, it never proves it finished
    t0 = _num(q.get("t0"))
    rid = _num(q["rid"]) if q.get("rid") is not None else t0
    return {"name": name[:40], "rid": rid, "t0": t0, "end": end or None, "cur": _str(q.get("cur"), 80),
            "verdict": verdict(S, end, stop, titles, q.get("cur"), past),
            "stages": {k[:80]: s["o"][:8] for k, s in S.items() if isinstance(k, str) and isinstance(s, dict) and isinstance(s.get("o"), str)}}


def _runs(r, memo):
    """Session `runs`: each plrun head + its past entries, newest t0 first."""
    out = []
    cwd = r.get("cwd") if isinstance(r.get("cwd"), str) else ""
    repos = [x for x in (r.get("repos") if isinstance(r.get("repos"), list) else ()) if isinstance(x, str) and x]
    for x in (r.get("plrun") if isinstance(r.get("plrun"), list) else ())[:V1_ROWS_MAX]:
        if not (isinstance(x, dict) and isinstance(x.get("name"), str) and x["name"]):
            continue
        rp = x.get("proj") if isinstance(x.get("proj"), str) else ""
        hints = []
        for h in [rp, cwd] + repos:
            if h and h not in hints:
                hints.append(h)
        titles = _titles(rp or cwd, x["name"], hints, memo)
        head = _run(x, x["name"], titles, False)
        out.append(head)
        ps = [q for q in (x.get("past") if isinstance(x.get("past"), list) else ()) if isinstance(q, dict)]
        ps = [p for p in (_run(q, x["name"], titles, True) for q in ps) if p["rid"] != head["rid"]]
        out.extend(sorted(ps, key=lambda p: -p["t0"])[:V1_PAST_MAX])
    out.sort(key=lambda p: -p["t0"])
    return out


def _session(r, memo=None):
    s = {k: _str(r.get(k)) for k in _S_STR}
    s["tool"] = s["tool"][:64]
    s.update({k: _int(r.get(k)) for k in _S_INT})
    p = r.get("plm")
    if isinstance(p, dict):
        s["plm"] = {"name": _str(p.get("name"), 40), "title": _str(p.get("title"), 40), "age": _int(p.get("age"))}
    # `runs` = an allow-listed projection of `plrun`, not plrun itself (its labels, agents and paths stay screen-only); absent when empty
    runs = _runs(r, {} if memo is None else memo)
    if runs:
        s["runs"] = runs
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
        memo = {}   # (proj, name, hints) -> titles, one definition lookup per build
        out["sessions"] = [_session(r, memo) for r in rows if isinstance(r, dict)]
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
