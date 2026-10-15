"""«Pipelines» «Delete»: POST /api/pipelines/delete {proj, name, dry} (split from sidereus/pipeline.py at the 620-line cap).

AGENTS.md rule 7: delete never deletes — the file MOVES into the same DATA_DIR/pipeline-bak/<ts>/ folder as save backups,
so undo = move it back. dry = preview {path, to}; dry:false moves and returns {backup}. ⚠Caller checks Origin.
"""
import os
import re

from sidereus import pipeline as _pl
from sidereus.pipeline_projects import _proj_ok
from sidereus.pipeline_schema import _NAME


def delete(req):
    """(code, body). Refuses unknown projects, names outside ^[a-z0-9-]{1,40}$, symlinks and a symlinked pipelines dir."""
    if not isinstance(req, dict):
        return 400, {"ok": False, "err": "bad body"}
    proj, name = req.get("proj"), req.get("name")
    if not _proj_ok(proj):
        return 403, {"ok": False, "err": "unknown project"}
    if not (isinstance(name, str) and _NAME.fullmatch(name)):
        return 400, {"ok": False, "err": "bad name"}
    d = _pl._pipe_dir(proj)
    p = os.path.join(d, name + ".json")
    rel = ".claude/pipelines/%s.json" % name
    with _pl._LOCK:
        if os.path.islink(p) or os.path.realpath(d) != os.path.join(os.path.realpath(proj), ".claude", "pipelines"):
            return 400, {"ok": False, "err": "path leaves the project"}   # ⚠a symlink would move a file from outside
        if not os.path.isfile(p):
            return 404, {"ok": False, "err": "%s not found" % rel}
        if req.get("dry") is not False:
            to = os.path.join(_pl._bak_dir(), _pl._strftime("%Y%m%d-%H%M%S"),
                              "%s--%s.json" % (re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(proj.rstrip("/"))), name))
            return 200, {"ok": True, "dry": True, "path": p, "to": to}
        try:
            dst = _pl._backup(p, proj, name, move=True)
        except OSError as e:
            return 500, {"ok": False, "err": "move failed (%s)" % type(e).__name__}
    return 200, {"ok": True, "dry": False, "path": p, "backup": dst}
