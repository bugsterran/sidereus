"""`GET /api/arch?path=` body: the newest verified architecture map of one repo from the arch store.

Metadata only — modules, edges and their file/line/symbol evidence; never file contents. The stored files are
agent-written, so they are re-validated (arch_verify.schema_errors) and capped here before going to the page.
"""
import hashlib
import os
import stat
import subprocess

from sidereus.config import CODE_DIR, IS_CLONE
from sidereus.gitinfo import _git_run, _git_run_capped
from sidereus.structure import _struct_src_root
from sidereus.arch_verify import BRIEF_HTML, BRIEF_OK, ARCH_DIR, NAME_MAX, PATH_MAX, SYM_MAX, est_of, head_of, read_json, render_md, repo_key, \
    schema_errors, COMMIT_RE, ARCH_GIT_TIMEOUT, ARCH_TREE_MAX, ID_RE, STYLES, ROLES, FW_MAX, UNITS_MAX, EV_MAX, SUM_MAX, OWNS_MAX
from sidereus.arch_flow import load_flows
from sidereus.arch_checks import load_checks
from sidereus import sec_report as SR
from sidereus import arch_prov

SIDEREUS_ROOT = os.path.realpath(CODE_DIR) if IS_CLONE else ""   # "" = installed package, no repo to relay to; repo holding .claude/pipelines/arch-map.json; the view relays «Request a map» to a session there
BRIEF_MAX = 1_000_000      # bytes of brief.html served by /api/arch/brief
FILES_MAX = 200            # file names per module in /api/arch/files; total still counts all
_TREE_CACHE = {}           # (realpath, commit) -> (sorted names, cut); a commit's tree never changes, 4 entries kept
_REQ_SRC = None            # fn(sid, pl, now) -> repo the page last asked that session to run pl on, ""; set by pl_reqs


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
            "checks": None, "prov": None, "brief": _brief(root, head)}
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
                checks=load_checks(root, d, m, head), prov=_prov(root, commit, d),
                brief=base["brief"] or (_brief(root, commit) if stale else None))   # older map: its own passed brief, stamped in the menu


def _brief_file(root, commit):
    """(brief.html path, sha256 from the gate's brief.ok.json for this commit), ("", "") when either is missing or unsafe."""
    if not (isinstance(commit, str) and COMMIT_RE.fullmatch(commit)):
        return "", ""
    kd = os.path.join(os.path.realpath(ARCH_DIR), repo_key(root))
    fp, okp = os.path.join(kd, commit, BRIEF_HTML), os.path.join(kd, commit, BRIEF_OK)
    # ⚠realpath must equal the plain join: a symlinked key dir, commit dir or file escapes the store and is refused.
    if os.path.islink(kd) or any(os.path.islink(x) or os.path.realpath(x) != x or not os.path.isfile(x) for x in (fp, okp)):
        return "", ""
    try:
        ok = read_json(okp) if os.path.getsize(okp) <= 4096 else None
    except (OSError, ValueError):
        return "", ""
    sha = ok.get("sha256") if isinstance(ok, dict) and ok.get("commit") == commit else None
    return (fp, sha) if isinstance(sha, str) and sha else ("", "")


def _brief_bytes(root, commit):
    """(path, bytes) of brief.html only when its sha256 equals the gate's record (an agent-edited page is never served)."""
    fp, sha = _brief_file(root, commit)
    if not fp:
        return None
    try:
        with os.fdopen(os.open(fp, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as f:
            data = f.read(BRIEF_MAX + 1) if stat.S_ISREG(os.fstat(f.fileno()).st_mode) else b""
    except OSError:
        return None
    return (fp, data) if data and len(data) <= BRIEF_MAX and hashlib.sha256(data).hexdigest() == sha else None


def _brief(root, head):
    """`brief` of /api/arch: `commit`'s gate-passed overview, None when there is none (load: HEAD first, then the shown older map)."""
    b = _brief_bytes(root, head)
    return {"commit": head, "file": b[0]} if b else None


def brief_html(path, commit):
    """`GET /api/arch/brief?path=&commit=` body: brief.html bytes of an allowed repo's store, or {ok: False, err}."""
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "err": "Only projects shown on screen can be opened."}
    b = _brief_bytes(root, commit)
    return b[1] if b else {"ok": False, "err": "no brief"}


def _prov(root, commit, d):
    """Provenance of the shown map (arch_prov), None = unknown; ⚠never read from the store dir the agent writes."""
    try:
        return arch_prov.load_prov(root, commit, os.path.getmtime(os.path.join(d, "verify.json")), req=_REQ_SRC)
    except (OSError, ValueError, TypeError, KeyError):
        return None


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


def security_report(path, name):
    """`GET /api/arch/secreport?path=&name=` body: one security report file of an allowed repo's store.
    ⚠Serves only `security-report-*.md` under ARCH_DIR/<key>/ (name pattern + sec_report.read_text guards); nothing else."""
    root = _struct_src_root(path)
    if not root:
        return {"ok": False, "err": "Only projects shown on screen can be opened."}
    if not isinstance(name, str) or not SR.REPORT_RE.fullmatch(name):
        return {"ok": False, "err": "bad name"}
    text = SR.read_text(os.path.join(ARCH_DIR, repo_key(root)), name)
    if not isinstance(text, str):
        return {"ok": False, "err": "no report"}
    return {"ok": True, "name": name, "text": text}


def set_req_source(fn):
    """pl_reqs registers its request reader here (it imports arch_map, so arch_map cannot import it)."""
    global _REQ_SRC
    _REQ_SRC = fn
