"""Compaction markers (hooks/compact_mark.py) -> row `cmp`. Owns CMP_DIR, CMP_MAX_S, _MS_CACHE."""
import glob
import json
import os
import re
import time
from sidereus.config import DATA_DIR
from sidereus import claude_roots
from sidereus import transcript

CMP_DIR = os.path.join(DATA_DIR, "compacting")
# ⚠PostCompact may never fire (crash, kill, failed compaction): an older marker is an orphan, never «Compacting».
CMP_MAX_S = 300
_SID_RE = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
MS_TTL_S = 600
MS_FILES = 12
MS_AGE_S = 14 * 86400
MS_TAIL = 2_000_000
MS_KEEP = 20
_MS_CACHE = {}     # projects dir -> (computed at, median ms, samples)
_FILE_MEMO = {}    # transcript path -> (size, [(timestamp, durationMs)])


def _marker_t(sid):
    try:
        with open(os.path.join(CMP_DIR, sid + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        return float(d.get("t") or 0) if isinstance(d, dict) else 0
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _file_ms(fp, size):
    """[(timestamp, durationMs)] of compact_boundary lines in the last MS_TAIL bytes; memo on (fp, size)."""
    hit = _FILE_MEMO.get(fp)
    if hit and hit[0] == size:
        return hit[1]
    out = []
    try:
        with open(fp, "rb") as f:
            if size > MS_TAIL:
                f.seek(size - MS_TAIL)
                f.readline()            # drop the partial first line
            data = f.read(MS_TAIL)
    except OSError:
        data = b""
    for ln in data.split(b"\n"):
        if b'"subtype":"compact_boundary"' not in ln:
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        # ⚠Check the type: a user/assistant line can merely mention the subtype string.
        if not isinstance(e, dict) or e.get("type") != "system" or e.get("subtype") != "compact_boundary":
            continue
        m = e.get("compactMetadata")
        try:
            ms = int((m or {}).get("durationMs") or 0) if isinstance(m, dict) else 0
        except (ValueError, TypeError):
            ms = 0
        if ms > 0:
            out.append((str(e.get("timestamp") or ""), ms))
    if len(_FILE_MEMO) > 256:
        _FILE_MEMO.clear()
    _FILE_MEMO[fp] = (size, out)
    return out


def _median_ms(proj_dir, now):
    """(median durationMs, samples) over the newest transcripts of one account; (0, 0) without history."""
    hit = _MS_CACHE.get(proj_dir)
    if hit and 0 <= now - hit[0] < MS_TTL_S:
        return hit[1], hit[2]
    files = []
    for fp in glob.glob(os.path.join(glob.escape(proj_dir), "*", "*.jsonl")):
        try:
            st = os.stat(fp)
        except OSError:
            continue
        if now - st.st_mtime <= MS_AGE_S:
            files.append((st.st_mtime, fp, st.st_size))
    files.sort(reverse=True)
    vals = []
    for _mt, fp, size in files[:MS_FILES]:
        vals.extend(_file_ms(fp, size))
    vals = [ms for _ts, ms in sorted(vals)[-MS_KEEP:]]
    med = 0
    if vals:
        s = sorted(vals)
        k = len(s) // 2
        med = s[k] if len(s) % 2 else (s[k - 1] + s[k]) // 2
    _MS_CACHE[proj_dir] = (now, med, len(vals))
    return med, len(vals)


def _proj_dir(sid, fp):
    d = claude_roots.acct_of(sid, fp)[1]
    return os.path.join(d, "projects") if d else transcript.CLAUDE_PROJECTS


def compacting(sid, fp, act_at, now=None):
    """None, or {"at", "estMs", "n"} while a compaction marker is newer than the last activity and at most CMP_MAX_S old."""
    if not isinstance(sid, str) or not _SID_RE.match(sid):
        return None
    now = time.time() if now is None else now
    t = _marker_t(sid)
    if not t or not (float(act_at or 0) < t <= now + 5) or now - t > CMP_MAX_S:
        return None
    med, n = _median_ms(_proj_dir(sid, fp), now)
    return {"at": int(t), "estMs": int(med), "n": n}
