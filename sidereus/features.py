"""Feature registry (docs/dev/FEATURES.md): `features/<id>.json` manifests + on/off toggles in prefs `features`.

Off = its routes 404 `{"error":"feature off"}` (chat_server dispatch) · its threads are not started (main) ·
its state keys are omitted (state()). Read once at import — a toggle change applies after a restart.
⚠Modules and web files of an off feature still load, so PAGE is byte-identical for any toggle state.
Ids with no manifest (core, or a dep not migrated yet) are always on.
"""
import glob
import json
import os
import re

from sidereus.config import CODE_DIR
from sidereus.warn import warn_once
from sidereus.prefs import effective, saved

FEATURES_DIR = os.path.join(CODE_DIR, "features")
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
_TOGGLES = effective("features")    # {id: bool}; missing id = on (⚠never written at import)


def on(fid, _seen=None):
    """True unless the feature (or any dep, transitively) is toggled off. Unknown ids = core = on."""
    m = _MANIFESTS.get(fid)
    if m is None:
        return True
    seen = _seen or set()
    if fid in seen:              # ⚠dep cycle: stop instead of recursing forever
        return True
    seen.add(fid)
    return _TOGGLES.get(fid, True) is not False and all(on(d, seen) for d in m["deps"])


def route_feature(path):
    """Id of the feature that claims `path` (exact, or `prefix*`), else None (core)."""
    for fid, m in _MANIFESTS.items():
        for r in m["routes"]:
            if path == r or (r.endswith("*") and path.startswith(r[:-1])):
                return fid
    return None


def thread_on(name):
    """False only when the feature claiming thread `name` is off."""
    for fid, m in _MANIFESTS.items():
        if name in m["threads"]:
            return on(fid)
    return True


def state_off():
    """/api/state keys to omit (claimed by off features)."""
    return {k for fid, m in _MANIFESTS.items() if not on(fid) for k in m["state_keys"]}


def snapshot():
    """{id: on} for every manifest — the `features` key of /api/state."""
    return {fid: on(fid) for fid in sorted(_MANIFESTS)}


def listing():
    """GET /api/prefs `features` rows (metadata only): running state `on` and the saved toggle `set` (applies after restart)."""
    want = saved("features")
    return [{"id": fid, "title": str(m.get("title") or fid)[:64], "deps": m["deps"], "default_on_public": m["default_on_public"],
             "on": on(fid), "set": want.get(fid, True) is not False} for fid, m in sorted(_MANIFESTS.items())]


def check_toggles(v):
    """ValueError unless v is {known id: bool} (POST /api/prefs/set key `features`)."""
    if not isinstance(v, dict) or not all(isinstance(k, str) and isinstance(b, bool) for k, b in v.items()):
        raise ValueError("features must be {id: true|false}")
    bad = sorted(k for k in v if k not in _MANIFESTS)
    if bad:
        raise ValueError("unknown feature %s" % ", ".join(bad)[:200])
