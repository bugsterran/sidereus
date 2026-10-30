"""Harness report «Found by a person first»: ended runs of bug-fix pipelines (file key `"catch": "person"`) — a defect a
person found before any gate did — each with the commits that landed in its window and the tests/ files they touched.

⚠Metadata only: pipeline names, run times, commit hashes and tests/ file names. Git argv is `rev-parse` and one
`log --name-only` (hash + commit time); never subjects, -p/--stat or a diff. Non-test file names are dropped here.
"""
import re
import subprocess
import time

from sidereus import gitinfo, pipeline, pl_outcome

PS_GRACE_S = 900          # a commit up to 15 min after the run ended still belongs to it (orchestrator commits last)
PS_HEAD_TTL = 20          # seconds the resolved HEAD is reused, so a repaint spawns nothing
PS_LOG_MAX = 300          # commits read by the one `log --name-only`
PS_CARD_MAX = 20          # newest runs listed as cards
PS_COMMITS_MAX = 8
PS_TESTS_MAX = 8
PS_PATH_MAX = 200
PS_CACHE_MAX = 32
PS_GIT_TIMEOUT = 3
PS_GIT_WAIT = 0.5
PS_NAME = re.compile(r"[a-z0-9-]{1,40}")
PS_HEX = re.compile(r"[0-9a-f]{4,40}")
_PS_CACHE = {}            # (key, HEAD, newest end, pipes) -> person() · ("head", repo) -> (at, HEAD)
_now = time.time


def _git(repo, args):
    """(returncode, stdout) of a read-only git call, or None on timeout/spawn failure. Tests patch this."""
    try:
        r = gitinfo._git_run(repo, args, PS_GIT_TIMEOUT, wait=PS_GIT_WAIT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.returncode, r.stdout or ""


def _pipes(proj):
    """Sorted names of `<proj>/.claude/pipelines/*.json` with `"catch": "person"` (pipeline's guarded reader)."""
    out = []
    for n in pipeline._names(proj):
        P = pipeline._read_pipe(proj, n)[1]
        if isinstance(P, dict) and P.get("catch") == "person":
            out.append(n)
    return out


def _tests(files):
    return sorted(set(f for f in files if isinstance(f, str) and f.startswith("tests/") and len(f) <= PS_PATH_MAX))


def shape(runs, log, pipes):
    """Pure: {pipes, runs, cards, git} from ledger rows (any order), git log [(sha, ct, [files])] (None = git miss) and
    catch=person pipeline names. Window per run = [t0, min(end + PS_GRACE_S, t0 of the first later row starting at/after end)]."""
    pipes = sorted(set(p for p in pipes or () if isinstance(p, str)))
    rows = sorted((r for r in runs or () if isinstance(r, dict)), key=lambda r: r.get("t0") or 0)
    mine = [(i, r) for i, r in enumerate(rows) if r.get("name") in pipes]
    # ⚠a full log (PS_LOG_MAX) is truncated: windows older than its oldest commit are unknown, not «no commit»
    floor = min(c[1] for c in log) if log and len(log) >= PS_LOG_MAX else None
    cards = []
    for i, r in reversed(mine[-PS_CARD_MAX:]):
        t0, end = r["t0"], r["end"]
        hi = end + PS_GRACE_S
        # ⚠rows overlapping this run belong to other sessions; only a run starting after it ended caps the window
        nxt = next((x["t0"] for x in rows[i + 1:] if x["t0"] >= end), None)
        if nxt is not None:
            hi = min(hi, nxt)
        commits = tests = None
        if log is not None and (floor is None or t0 >= floor):
            hit = [c for c in log if t0 <= c[1] <= hi][:PS_COMMITS_MAX]
            commits = [c[0][:12] for c in hit]
            tests = _tests(f for c in hit for f in c[2])[:PS_TESTS_MAX]
        cards.append({"name": r["name"], "t0": t0, "end": end, "commits": commits, "tests": tests or []})
    return {"pipes": pipes, "runs": len(mine), "cards": cards, "git": log is not None}


def _head(repo):
    hit = _PS_CACHE.get(("head", repo))
    if hit and _now() - hit[0] < PS_HEAD_TTL:
        return hit[1]
    out = _git(repo, ["rev-parse", "--verify", "-q", "HEAD"])
    h = out[1].strip() if out and out[0] == 0 else ""
    if not PS_HEX.fullmatch(h):
        return ""
    _PS_CACHE[("head", repo)] = (_now(), h)
    return h


def _log(repo, since):
    """[(sha, ct, [tests/ files])] newest first, or None on a git miss. Non-test names never leave this function."""
    out = _git(repo, ["log", "-n", str(PS_LOG_MAX), "--since=@%d" % int(since), "--format=%x1e%H%x1f%ct", "--name-only", "HEAD"])
    if not out or out[0] != 0:
        return None
    rows = []
    for rec in out[1].split("\x1e")[1:]:
        head, _, rest = rec.partition("\n")
        sha, _, ct = head.partition("\x1f")
        if not PS_HEX.fullmatch(sha.strip()) or not ct.strip().isdigit():
            continue
        rows.append((sha.strip(), int(ct.strip()), _tests(ln.strip() for ln in rest.splitlines())))
    return rows


def person(proj, git=True):
    """shape() for project `proj` from its run ledger; ≤2 git spawns (HEAD memoised PS_HEAD_TTL), cached per HEAD."""
    empty = {"pipes": [], "runs": 0, "cards": [], "git": False}
    if not isinstance(proj, str) or not proj:
        return empty
    pipes = _pipes(proj)
    if not pipes:
        return empty
    runs = pl_outcome.ledger(pl_outcome.repo_key(proj), 0)
    mine = sorted((r for r in runs if r["name"] in pipes), key=lambda r: r["t0"])
    if not mine or not git:
        return shape(runs, None, pipes)
    head = _head(proj)
    if not head:
        return shape(runs, None, pipes)   # git miss: commits null, not cached
    key = (pl_outcome.repo_key(proj), head, max(r["end"] for r in runs), tuple(pipes))
    if key in _PS_CACHE:
        return _PS_CACHE[key]
    log = _log(proj, min(r["t0"] for r in mine[-PS_CARD_MAX:]))
    out = shape(runs, log, pipes)
    if log is not None:
        if len(_PS_CACHE) >= PS_CACHE_MAX:
            _PS_CACHE.clear()
        _PS_CACHE[key] = out
    return out
