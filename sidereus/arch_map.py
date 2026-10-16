"""`GET /api/arch?path=` body: the newest verified architecture map of one repo from the arch store.

Metadata only — modules, edges and their file/line/symbol evidence; never file contents. The stored files are
agent-written, so they are re-validated (arch_verify.schema_errors) and capped here before going to the page.
"""
import json
import os
import re
import subprocess
import time

from sidereus.config import CODE_DIR
from sidereus.gitinfo import _git_run, _git_run_capped
from sidereus.structure import _struct_src_root
from sidereus.arch_verify import ARCH_DIR, NAME_MAX, PATH_MAX, SYM_MAX, est_of, head_of, read_json, render_md, repo_key, \
    schema_errors, COMMIT_RE, ARCH_GIT_TIMEOUT, ARCH_TREE_MAX, ID_RE, STYLES, ROLES, FW_MAX, UNITS_MAX, EV_MAX, SUM_MAX, OWNS_MAX
from sidereus.arch_flow import load_flows
from sidereus.arch_checks import load_checks

SIDEREUS_ROOT = os.path.realpath(CODE_DIR)   # repo holding .claude/pipelines/arch-map.json; the view relays «Request a map» to a session there
ARCH_PL = "arch-map"
_ARCH_TAG = re.compile(r"\[pl:arch-map/([^\]]{1,80})\]")
ARCH_RUN_GAP_S = 180       # a run stays «in progress» this long after its last tagged sign (main thinks between stages)
ARCH_BUSY_S = 30 * 60      # a busy session keeps its open plrun only this long after the run last moved
ARCH_PEND_S = 6 * 3600     # = pl_runs.PLR_KEEP_S: an older plan.json without verify.json is an abandoned run
FILES_MAX = 200            # file names per module in /api/arch/files; total still counts all
_TREE_CACHE = {}           # (realpath, commit) -> (sorted names, cut); a commit's tree never changes, 4 entries kept
_RUN_SEEN = {}             # project path -> {stage, sid, t0, at}: last tagged sign per project (bridges stage gaps)


def _cut(s, mx):
    return s[:mx] if isinstance(s, str) else ""


def _newest(rdir):
    """Commit dir name under rdir whose verify.json is newest, "" if none."""
    best, at = "", -1.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return ""
    for c in names:
        if not COMMIT_RE.fullmatch(c):
            continue
        try:
            t = os.path.getmtime(os.path.join(rdir, c, "verify.json"))
        except OSError:
            continue
        if t > at:
            best, at = c, t
    return best


def behind_of(repo, commit):
    """Commits on HEAD since commit (`git rev-list --count commit..HEAD`, read-only), None if unknown."""
    if not COMMIT_RE.fullmatch(commit or ""):
        return None
    try:
        r = _git_run(repo, ["rev-list", "--count", commit + "..HEAD"], ARCH_GIT_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return None
    n = r.stdout.strip() if r.returncode == 0 else ""
    return int(n) if n.isdigit() else None


def _gen_at(d, v):
    """Generation time (epoch s): verify.json `at` if the gate wrote one, else map.json mtime, None if neither."""
    t = v.get("at")
    if isinstance(t, (int, float)) and not isinstance(t, bool) and 0 < t < 2 ** 32:
        return float(t)
    try:
        return os.path.getmtime(os.path.join(d, "map.json"))
    except OSError:
        return None


def _style(x):
    """verify.json `style` re-checked for the page; None when absent or malformed (old stores have none)."""
    if not isinstance(x, dict) or x.get("style") not in STYLES or not isinstance(x.get("evidence"), list):
        return None
    evs = [{"file": _cut(e["file"], PATH_MAX), "ok": e.get("ok") is True}
           for e in x["evidence"][:EV_MAX] if isinstance(e, dict) and isinstance(e.get("file"), str) and e["file"]]
    return {"style": x["style"], "framework": _cut(x.get("framework"), FW_MAX), "units": _cut(x.get("units"), UNITS_MAX),
            "evidence": evs, "ok": x.get("ok") is True}


def _dev(x, edges):
    """verify.json `dev` kept only for an in-range, verified edge with two known roles; [] when absent."""
    out = []
    for d in x if isinstance(x, list) else ():
        i = d.get("i") if isinstance(d, dict) else None
        if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(edges) and edges[i]["ok"] \
                and d.get("a") in ROLES and d.get("b") in ROLES:
            out.append({"i": i, "a": d["a"], "b": d["b"]})
    return out


def load(path):
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "msg": "Only projects shown on screen can be opened.", "sidereus": SIDEREUS_ROOT}
    head = head_of(root)
    base = {"ok": True, "empty": True, "sidereus": SIDEREUS_ROOT, "commit": "", "head": head, "stale": False,
            "behind": None, "at": None, "v": None, "groups": [], "modules": [], "edges": [], "rate": None, "md": "", "style": None, "dev": [], "flows": [],
            "checks": None}
    commit = _newest(os.path.join(ARCH_DIR, repo_key(root)))
    if not commit:
        return base
    d = os.path.join(ARCH_DIR, repo_key(root), commit)
    try:
        m, v = read_json(os.path.join(d, "map.json")), read_json(os.path.join(d, "verify.json"))
    except (OSError, ValueError):
        return base
    # ⚠Verified against this root's realpath: a map copied from another repo's store is refused, not shown.
    if schema_errors(m, root, commit) or not isinstance(v, dict) or not isinstance(v.get("edges"), list):
        return dict(base, bad=True)
    oks = {x.get("i"): x.get("ok") is True for x in v["edges"] if isinstance(x, dict)}
    # ⚠Diagram rebuilt from the validated map + verdicts, never the stored map.md: it cannot disagree with them.
    md = render_md(m, {"edges": [{"i": i, "ok": oks.get(i, False)} for i in range(len(m["edges"]))]})
    rate = v.get("rate")
    mods = [dict({"id": x["id"], "name": _cut(x["name"], NAME_MAX), "path": _cut(x["path"], PATH_MAX),
                  "kind": x["kind"]}, **{k: x[k] for k in ("ext", "role", "layer", "group") if k in x},
                 **({"summary": _cut(x["summary"], SUM_MAX)} if "summary" in x else {}),
                 **({"owns": list(x["owns"][:OWNS_MAX])} if "owns" in x else {})) for x in m["modules"]]
    groups = [dict({"id": g["id"], "name": _cut(g["name"], NAME_MAX)}, **({"layer": g["layer"]} if "layer" in g else {}))
              for g in m.get("groups") or ()]   # v1 maps have none
    edges = [{"from": e["from"], "to": e["to"], "kind": e["kind"], "label": _cut(e["label"], NAME_MAX),
              "est": est_of(e), "ok": oks.get(i, False),
              "evidence": [{"file": _cut(x["file"], PATH_MAX), "line": x["line"], "symbol": _cut(x["symbol"], SYM_MAX)}
                           for x in e["evidence"]]} for i, e in enumerate(m["edges"])]
    stale = bool(head) and head != commit
    return dict(base, empty=False, commit=commit, stale=stale, behind=behind_of(root, commit) if stale else None,
                at=_gen_at(d, v),
                v=m["v"], groups=groups, modules=mods, edges=edges,
                rate=rate if isinstance(rate, (int, float)) and not isinstance(rate, bool) else None,
                md=md, style=_style(v.get("style")), dev=_dev(v.get("dev"), edges), flows=load_flows(d, m, root, commit),
                checks=load_checks(root, d, m, head))


def _ls(root, commit):
    """(sorted file names at commit, cut) via read-only `git ls-tree`; cut = output past ARCH_TREE_MAX. Cached per commit."""
    k = (root, commit)
    if k in _TREE_CACHE:
        return _TREE_CACHE[k]
    text, n = _git_run_capped(root, ["ls-tree", "-r", "--name-only", "-z", commit], ARCH_GIT_TIMEOUT, ARCH_TREE_MAX)
    names = sorted(x for x in text[:ARCH_TREE_MAX].split("\0") if x)
    if n > ARCH_TREE_MAX and names:
        names.pop()   # last name may be truncated mid-path
    while len(_TREE_CACHE) >= 4:
        _TREE_CACHE.pop(next(iter(_TREE_CACHE)))
    _TREE_CACHE[k] = (names, n > ARCH_TREE_MAX)
    return _TREE_CACHE[k]


def _mod_prefix(p):
    """Module path -> "" (repo root) or a clean prefix; None when unsafe (never reaches git: matching is in Python)."""
    if not isinstance(p, str) or len(p) > PATH_MAX or p.startswith(("/", "-", ":")) or os.path.isabs(p) \
            or "\\" in p or "\0" in p:
        return None
    while p.startswith("./"):
        p = p[2:]
    p = p.rstrip("/")
    if p == ".":
        p = ""
    if p.startswith(("-", ":", "/")) or ".." in p.split("/"):
        return None
    return p


def files(path, mid):
    """`GET /api/arch/files?path=&id=` body: file names under one module's path at the map's verified commit.
    ⚠The module path comes from the re-validated store map, never from the request (no client path or commit)."""
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "msg": "Only projects shown on screen can be opened."}
    out = {"ok": True, "commit": "", "id": "", "path": "", "files": [], "total": 0, "cut": False, "why": ""}
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        return dict(out, why="bad")
    out["id"] = mid
    commit = _newest(os.path.join(ARCH_DIR, repo_key(root)))
    if not COMMIT_RE.fullmatch(commit or ""):
        return dict(out, why="nomap")
    try:
        m = read_json(os.path.join(ARCH_DIR, repo_key(root), commit, "map.json"))
    except (OSError, ValueError):
        return dict(out, why="nomap")
    if schema_errors(m, root, commit):
        return dict(out, why="nomap")
    mod = next((x for x in m["modules"] if x["id"] == mid), None)
    if mod is None:
        return dict(out, commit=commit, why="bad")
    raw = mod["path"]
    out.update(commit=commit, path=_cut(raw, PATH_MAX))
    if mod["kind"] == "external":
        return dict(out, why="ext")
    if raw == "":
        return dict(out, why="nopath")
    pre = _mod_prefix(raw)
    if pre is None:
        return dict(out, why="bad")
    try:
        names, cut = _ls(root, commit)
    except (subprocess.SubprocessError, OSError):
        return dict(out, why="git")
    hit = names if pre == "" else [x for x in names if x == pre or x.startswith(pre + "/")]
    if not hit:
        return dict(out, cut=cut, why="gone")
    return dict(out, files=hit[:FILES_MAX], total=len(hit), cut=cut)

def _titles():
    """Stage titles of the arch-map pipeline in order, [] if unreadable (read directly: sidereus.pipeline is a feature module)."""
    try:
        with open(os.path.join(SIDEREUS_ROOT, ".claude", "pipelines", ARCH_PL + ".json"), "rb") as f:
            P = json.loads(f.read(65536))
        return [s["title"] for s in P["stages"] if isinstance(s, dict) and isinstance(s.get("title"), str)]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def _pending_at(root):
    """mtime of the newest plan.json under root's store with no newer verify.json (a run past stage 1), 0 if none."""
    rdir, best = os.path.join(ARCH_DIR, repo_key(root)), 0.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return 0.0
    for c in names:
        if not COMMIT_RE.fullmatch(c):
            continue
        try:
            p = os.path.getmtime(os.path.join(rdir, c, "plan.json"))
        except OSError:
            continue
        try:
            v = os.path.getmtime(os.path.join(rdir, c, "verify.json"))
        except OSError:
            v = 0.0
        if p > v and p > best:
            best = p
    return best


def _result_at(root):
    """mtime of the newest verify.json under root's store (a run's gate result), 0 if none."""
    rdir, best = os.path.join(ARCH_DIR, repo_key(root)), 0.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return 0.0
    for c in names:
        if COMMIT_RE.fullmatch(c):
            f = os.path.join(rdir, c, "verify.json")
            if os.path.isfile(f):   # most commit dirs have no gate result yet; a vanished file just counts as none
                try:
                    best = max(best, os.path.getmtime(f))
                except OSError:
                    continue
    return best


def _finished(p, s, sg, pt, old):
    """True when p's run already has its result: a verify.json newer than any sign of this run started, and either the
    run record closed after it or no tagged subagent / Agent call is still live in the session."""
    v = _result_at(p)
    if not v or pt > v or sg[1] > v or (old and old["t0"] > v):
        return False
    for r in s.get("plrun") or ():
        e = r.get("end") if isinstance(r, dict) and r.get("name") == ARCH_PL else None
        if isinstance(e, (int, float)) and not isinstance(e, bool) and e >= v:
            return True
    subs = any(isinstance(x, dict) and isinstance(x.get("lab"), str) and _ARCH_TAG.search(x["lab"]) for x in s.get("sub") or ())
    targ = s.get("tool") in ("Agent", "Task") and isinstance(s.get("targ"), str) and _ARCH_TAG.search(s["targ"])
    return not (subs or targ)


def _sign(s, now):
    """(stage title, start time | 0) of a live arch-map stage in one session row, None if none.
    Sources: open plrun run · live subagent label · main's [pl:] marker · the Agent call in flight (targ)."""
    for r in s.get("plrun") or ():
        if isinstance(r, dict) and r.get("name") == ARCH_PL and not r.get("end") and isinstance(r.get("cur"), str) and r["cur"]:
            # ⚠An open run is kept by the hook for hours: count it only while the session works or the run moved recently.
            t1 = r.get("t1") if isinstance(r.get("t1"), (int, float)) and not isinstance(r.get("t1"), bool) else 0
            if now - t1 <= (ARCH_BUSY_S if s.get("state") in ("think", "tool") else ARCH_RUN_GAP_S):
                return r["cur"], float(r.get("t0") or 0)
    for x in s.get("sub") or ():
        m = _ARCH_TAG.search(x.get("lab") or "") if isinstance(x, dict) and isinstance(x.get("lab"), str) else None
        if m:
            mn = x.get("min")
            return m.group(1), (now - 60 * mn if isinstance(mn, int) and not isinstance(mn, bool) and mn >= 0 else 0.0)
    plm = s.get("plm")
    if isinstance(plm, dict) and plm.get("name") == ARCH_PL and isinstance(plm.get("title"), str) and plm["title"]:
        return plm["title"], 0.0
    m = _ARCH_TAG.search(s.get("targ") or "") if s.get("tool") in ("Agent", "Task") and isinstance(s.get("targ"), str) else None
    return (m.group(1), 0.0) if m else None


PLAN_MAX = 1_000_000   # bytes of a store plan.json read to find its repo


def _store_repo(c):
    """c, or for a path inside the arch store (`<ARCH_DIR>/<key>/<commit>/…`) the repo its plan.json records, "" if unknown.
    ⚠Stages run with cwd in the store dir: keyed as-is, the run showed the commit hash instead of the repo."""
    store = os.path.realpath(ARCH_DIR)
    rc = os.path.realpath(c)
    if rc != store and not rc.startswith(store + os.sep):
        return c
    parts = os.path.relpath(rc, store).split(os.sep)
    if len(parts) < 2 or not COMMIT_RE.fullmatch(parts[1]):
        return ""
    fp = os.path.join(store, parts[0], parts[1], "plan.json")
    try:
        if os.path.getsize(fp) > PLAN_MAX:
            return ""
        repo = read_json(fp).get("repo")
    except (OSError, ValueError, AttributeError):
        return ""
    if not (isinstance(repo, str) and os.path.isabs(repo) and os.path.isdir(repo)):
        return ""
    repo = os.path.realpath(repo)
    return repo if repo_key(repo) == parts[0] and not repo.startswith(store + os.sep) else ""


def _target(s, now):
    """Project an arch-map session works on: the candidate (cwd + repos) with a pending store dir, else the first candidate
    that is not the Sidereus repo (the pipeline's home, not the target), else ""."""
    cands = []
    for c in [s.get("cwd")] + list(s.get("repos") or ()):
        if isinstance(c, str) and c and os.path.isabs(c):
            c = _store_repo(c)
            if c and c not in cands:
                cands.append(c)
    pend = [(t, c) for c, t in ((c, _pending_at(c)) for c in cands) if t and now - t <= ARCH_PEND_S]
    if pend:
        return max(pend)[1], max(pend)[0]
    # Stage 1 writes no plan.json yet: a Sidereus-cwd session still names its target in repos (reload keeps «Analysing»).
    other = [c for c in cands if os.path.realpath(c) != SIDEREUS_ROOT]
    return (other[0], 0.0) if other else ("", 0.0)


def seen_runs():
    """{project: {sid}} of the last runs() result (= state `archRun` keys) without recomputing; for GET /api/pipelines."""
    return {p: {"sid": v.get("sid") or ""} for p, v in list(_RUN_SEEN.items()) if isinstance(v, dict)}


def runs(sessions, now=None):
    """`/api/state` `archRun`: {project path: {stage, n, of, t0, sid}} for arch-map runs in progress, from session rows.
    ⚠Metadata only — stage title, times, session id. The pipeline hook keeps no run for a session whose cwd has its own
    pipelines (arch-map lives in the Sidereus repo), so the row's live [pl:arch-map/…] tags are the source, not plrun alone."""
    now = time.time() if now is None else now
    seen, ended = {}, set()
    for s in sessions or ():
        if not isinstance(s, dict) or s.get("state") in ("done", "gone"):
            continue
        sg = _sign(s, now)
        if not sg:
            continue
        p, pt = _target(s, now)
        if not p:
            continue
        old = _RUN_SEEN.get(p)
        # ⚠A busy orchestrator keeps signs alive long after the gate passed: once the result exists the run is over.
        if _finished(p, s, sg, pt, old):
            ended.add(p)
            continue
        t0s = [t for t in (sg[1], pt, old and old["t0"]) if t]
        seen[p] = {"stage": sg[0][:80], "sid": str(s.get("sid") or "")[:64], "t0": min(t0s) if t0s else now, "at": now}
    alive = {str(s.get("sid") or "") for s in sessions or () if isinstance(s, dict) and s.get("state") not in ("done", "gone")}
    # ⚠One session = one run: stage 1 guesses the target (no plan.json yet), so when plan.json names another repo the
    #   guessed key must not be carried beside the real one (one run showed on two projects).
    live = {v["sid"] for v in seen.values()}
    for p, v in list(_RUN_SEEN.items()):   # ⚠a stage gap keeps the run only while its session lives; past the gap it is over
        if p not in seen and p not in ended and v["sid"] in alive and v["sid"] not in live and now - v["at"] <= ARCH_RUN_GAP_S \
                and _result_at(p) < v["t0"]:
            seen[p] = v
    _RUN_SEEN.clear()
    _RUN_SEEN.update(seen)
    titles = _titles()
    return {p: {"stage": v["stage"], "n": titles.index(v["stage"]) + 1 if v["stage"] in titles else 0, "of": len(titles),
                "t0": v["t0"], "sid": v["sid"]} for p, v in seen.items()}
