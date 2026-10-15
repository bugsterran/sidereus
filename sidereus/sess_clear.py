"""/clear pairing: which sid replaced which in the same Claude process (hooks/invite_notice.py `record_clear`).

⚠`claude agents` keeps reporting the pre-/clear sid, so old -> new comes only from the hook's pid record.
Metadata only: pid, two sids, time.
"""
import json
import os
import re
import threading

from sidereus.config import DATA_DIR

CLEAR_FILE = os.path.join(DATA_DIR, "clears.jsonl")
SESSPID_DIR = os.path.join(DATA_DIR, "sesspid")
CLEAR_TAIL = 64 * 1024               # bytes read from the end of CLEAR_FILE
CLEAR_MAX = 200                      # newest links kept
_SID_RE = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
_clr_cache = {"key": None, "links": []}
_clr_lock = threading.Lock()


def _parse(raw):
    out = []
    for ln in raw.splitlines():
        try:
            d = json.loads(ln)
            pid, old, new, at = str(d["pid"]), d["old"], d["new"], int(d["at"])
        except Exception:
            continue
        if not pid.isdigit() or not isinstance(old, str) or not isinstance(new, str):
            continue
        if not _SID_RE.match(old) or not _SID_RE.match(new) or old == new:
            continue
        out.append({"pid": pid, "old": old, "new": new, "at": at})
    return out[-CLEAR_MAX:]


def clear_links():
    """[{"pid", "old", "new", "at"}] oldest first, ≤ CLEAR_MAX; cached on the file's mtime/size."""
    try:
        st = os.stat(CLEAR_FILE)
    except OSError:
        return []
    key = (CLEAR_FILE, st.st_mtime_ns, st.st_size)
    with _clr_lock:
        if _clr_cache["key"] != key:
            try:
                with open(CLEAR_FILE, "rb") as f:
                    if st.st_size > CLEAR_TAIL:
                        f.seek(st.st_size - CLEAR_TAIL)
                        f.readline()                 # drop the partial first line
                    raw = f.read(CLEAR_TAIL).decode("utf-8", "replace")
            except OSError:
                return []
            _clr_cache["links"] = _parse(raw)
            _clr_cache["key"] = key
        return [dict(x) for x in _clr_cache["links"]]


def clear_of(sid):
    """Links whose `new` is `sid` (the clears that started this session), oldest first."""
    if not sid:
        return []
    return [x for x in clear_links() if x["new"] == sid]
