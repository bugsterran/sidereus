"""Feature registry (docs/dev/FEATURES.md): `features/<id>.json` manifests + on/off toggles in prefs `features`.

Off = its routes 404 `{"error":"feature off"}` (chat_server dispatch) · its threads are not started (main) ·
its state keys are omitted (state()). Toggles are cached in `_TOGGLES` (filled at import); `save()` swaps the cache on Save,
so a change applies without a restart (claimed loops idle while off, see start_threads).
⚠Modules and web files of an off feature still load, so PAGE is byte-identical for any toggle state.
Ids with no manifest (core, or a dep not migrated yet) are always on.
"""
import glob
import json
import os
import re
import threading

from sidereus.config import ASSET_DIR
from sidereus.warn import warn_once
from sidereus import prefs
from sidereus.prefs import effective, saved

FEATURES_DIR = os.path.join(ASSET_DIR, "features")
_ID_RE = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")   # ⚠`$` also matches before a final "\n" — use \Z
_LIST_FIELDS = ("deps", "modules", "routes", "threads", "state_keys", "web", "settings")


def _load(folder):
    """{id: manifest} from folder/*.json; a broken manifest is skipped with a warning (never fatal)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                m = json.load(f)
            if not isinstance(m, dict) or not _ID_RE.match(str(m.get("id") or "")):
                raise ValueError("id missing or invalid")
            if m["id"] in out:
                raise ValueError("duplicate id %s" % m["id"])
            for k in _LIST_FIELDS:
                v = m.setdefault(k, [])
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise ValueError("%s must be a list of strings" % k)
            m["default_on_public"] = m.get("default_on_public") is True
        except (OSError, ValueError) as e:
            warn_once("feature:" + os.path.basename(p), "Feature manifest {file} skipped ({err})",
                      vars={"file": os.path.basename(p), "err": str(e)})
            continue
        out[m["id"]] = m
    return out


_MANIFESTS = _load(FEATURES_DIR)
_TOGGLES = effective("features")    # {id: bool}; missing id = on (⚠never written at import; ⚠replaced whole by save(), never mutated)
_SWAP = threading.Lock()            # serialises save(): check, swap, write, roll back
_THREAD_SPEC = ()                   # ((name, start_fn, "loop"|"once"), ...) from register_threads (chat_server.main)
_STARTED = set()                    # thread names already started in this process
_TLOCK = threading.Lock()


def _on(fid, t, seen):
    m = _MANIFESTS.get(fid)
    if m is None:
        return True
    if fid in seen:              # ⚠dep cycle: stop instead of recursing forever
        return True
    seen.add(fid)
    return t.get(fid, True) is not False and all(_on(d, t, seen) for d in m["deps"])


def on(fid):
    """True unless the feature (or any dep, transitively) is toggled off. Unknown ids = core = on."""
    return _on(fid, _TOGGLES, set())   # ⚠one dict ref per call, so a concurrent save() never mixes old and new


def route_feature(path):
    """Id of the feature that claims `path` (exact, or `prefix*`), else None (core)."""
    for fid, m in _MANIFESTS.items():
        for r in m["routes"]:
            if path == r or (r.endswith("*") and path.startswith(r[:-1])):
                return fid
    return None


def thread_on(name):
    """False only when the feature claiming thread `name` is off."""
    t = _TOGGLES
    for fid, m in _MANIFESTS.items():
        if name in m["threads"]:
            return _on(fid, t, set())
    return True


def state_off():
    """/api/state keys to omit (claimed by off features)."""
    t = _TOGGLES
    return {k for fid, m in _MANIFESTS.items() if not _on(fid, t, set()) for k in m["state_keys"]}


def snapshot():
    """{id: on} for every manifest — the `features` key of /api/state."""
    t = _TOGGLES
    return {fid: _on(fid, t, set()) for fid in sorted(_MANIFESTS)}


def listing():
    """GET /api/prefs `features` rows (metadata only): running state `on` (cache) and the saved toggle `set` (file)."""
    want, t = saved("features"), _TOGGLES
    return [{"id": fid, "title": str(m.get("title") or fid)[:64], "deps": m["deps"], "default_on_public": m["default_on_public"],
             "on": _on(fid, t, set()), "set": want.get(fid, True) is not False} for fid, m in sorted(_MANIFESTS.items())]


def check_toggles(v):
    """ValueError unless v is {known id: bool} (POST /api/prefs/set key `features`)."""
    if not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(b, bool) for k, b in v.items()):
        raise ValueError("features must be {id: true|false}")
    bad = sorted(k for k in v if k not in _MANIFESTS)
    if bad:
        raise ValueError("unknown feature %s" % ", ".join(bad)[:200])


def save(req):
    """POST /api/prefs/set key `features`: swap the cache, write the config, roll back on a failed write -> (code, out)."""
    global _TOGGLES
    reset = isinstance(req, dict) and req.get("reset") is True
    with _SWAP:
        if reset:
            new = {}
        else:
            try:
                check_toggles(req.get("value") if isinstance(req, dict) else None)
            except ValueError as e:
                return 400, {"ok": False, "err": str(e)}
            new = dict(req["value"])
        old = _TOGGLES
        _TOGGLES = new                  # ⚠whole replacement: readers hold their own ref to the old dict
        code, out = prefs.prefs_set(req)
        if code != 200:
            _TOGGLES = old
            return code, out
    start_threads()
    out = dict(out)
    out.update(restart=False, features=snapshot())
    return 200, out


def register_threads(spec):
    """Threads chat_server.main may start: ((name, start_fn, "loop"|"once"), ...) in start order."""
    global _THREAD_SPEC
    _THREAD_SPEC = tuple(spec)


def start_threads():
    """Start each registered thread that is on and not started yet (boot and after save()).

    ⚠Contract: a claimed loop checks thread_on(name) each cycle and idles while off — it never exits, so
    on→off→on never starts a second copy. A "once" warm runs at most once per process.
    """
    with _TLOCK:
        for name, fn, kind in _THREAD_SPEC:
            if name in _STARTED or not thread_on(name):
                continue
            if kind == "loop":
                threading.Thread(target=fn, name=name, daemon=True).start()
            else:
                fn()
            _STARTED.add(name)
