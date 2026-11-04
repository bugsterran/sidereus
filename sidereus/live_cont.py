"""`claude -c` session claims for live_cwds and the newest-transcript lookup (split from live for its size cap)."""
import os
import re
import time
from sidereus import claude_roots
from sidereus.transcript import CLAUDE_PROJECTS
from sidereus.ident import _slug
from sidereus.live_probe import _UUID_RE

CONT_HOLD_MAX = 256


def _newest_jsonl(d):
    """**Newest .jsonl** in that project directory ("" if none). ⚠Depth 1 only (`subagents/` is out of scope)."""
    best, best_mt = "", 0
    try:
        for fn in os.listdir(d):
            if not fn.endswith(".jsonl"):
                continue
            fp = os.path.join(d, fn)
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            if mt > best_mt:
                best, best_mt = fp, mt
    except OSError:
        return ""
    return best


def _newest_slug(cwd):
    """Newest .jsonl of cwd's slug across every Claude root ("" if none). ⚠Same cwd in two roots: newest wins."""
    best, best_mt = "", -1.0
    for root in claude_roots.projects_dirs(CLAUDE_PROJECTS):
        f = _newest_jsonl(os.path.join(root, _slug(cwd)))
        try:
            mt = os.path.getmtime(f) if f else -1.0
        except OSError:
            continue
        if mt > best_mt:
            best, best_mt = f, mt
    return best


# ⚠`claude -c` appends to the newest transcript of its cwd under the same sessionId but has no sid in argv; until its
#   first new line an /exit tail reads EXITED, gives up the path slot and an older same-cwd row looked live (false ask).
#   ⇒ claim the newest sid of the cwd as first seen for this pid+argv; a different newest later (/clear, another
#     session) drops the claim back to path counting. `--fork-session` starts a new sid, a bare `--resume` is a picker.
_CONT_ARG_RE = re.compile(r"(?:^|\s)(?:-c|--continue)(?=\s|$)")
_CONT_SKIP_RE = re.compile(r"(?:^|\s)(?:--fork-session|--resume|-r)(?=[\s=]|$)")
_cont_sid = {}        # pid -> (argv, sid newest in its cwd when first seen)
_cont_newest = [0.0, {}]   # (measured at, cwd -> newest transcript path)
CONT_NEWEST_TTL = 5


def _cont_newest_sid(cwd):
    """Newest transcript sid of cwd ("" if none or not a uuid name); cached CONT_NEWEST_TTL s."""
    now = time.time()
    if now - _cont_newest[0] > CONT_NEWEST_TTL:
        _cont_newest[0], _cont_newest[1] = now, {}
    c = _cont_newest[1]
    if cwd not in c:
        c[cwd] = _newest_slug(cwd)
    sid = os.path.basename(c[cwd])[:-6] if c[cwd].endswith(".jsonl") else ""
    return sid if _UUID_RE.fullmatch(sid) else ""


def _cont_claim(pid, cmd, cwd, sids, claimed):
    """A `claude -c` pid claims the sid it continued (comment above); fills sids/claimed in place."""
    if not cwd:
        return
    sid = _cont_newest_sid(cwd)
    first = _cont_sid.get(pid)
    if first is None or first[0] != cmd:
        if not sid or (pid not in _cont_sid and len(_cont_sid) >= CONT_HOLD_MAX):
            return
        _cont_sid[pid] = first = (cmd, sid)
    if not sid or first[1] != sid or sid in sids:
        return                     # moved on, or another live process already owns it: path counting as before
    sids.add(sid)
    claimed.add(pid)


def _cont_prune(snap):
    cmds = {str(p): c for p, _pp, c in snap or ()}
    for p in [p for p, (c, _s) in _cont_sid.items() if cmds.get(p) != c]:
        del _cont_sid[p]           # gone or argv changed (pid reuse): never revived
