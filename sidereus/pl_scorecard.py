"""Supply-chain posture of a project (subset of the OpenSSF Scorecard checks) for the pipeline «Evaluation» panel.
Verdicts come from tracked file names (`git ls-files`) and project pipeline gate strings only: no file contents,
no network, no tool runs. ⚠Only check ids, verdicts and counts leave this module (never paths or gate text)."""
import os
import shlex

from sidereus import gitinfo, pipeline
from sidereus.pipeline_schema import gate_mode
from sidereus.sec_checks import SEC_IDS

SC_IDS = ("security-policy", "license", "pinned-deps", "dep-update-tool", "secret-gate", "sast-gate", "dep-audit-gate",
          "binary-artifacts")
SC_VERDICTS = ("pass", "fail", "na")
SC_TIMEOUT_S = 2
SC_CACHE_MAX = 64
SC_CACHE = {}       # realpath -> ((head, pipeline mtimes), result)
# Gate check -> tool ids (sec_checks ids, plus pip-audit which the checks runner does not plan).
SC_GATE_TOOLS = {"secret-gate": ("gitleaks",), "sast-gate": ("semgrep", "bandit"),
                 "dep-audit-gate": ("npm-audit", "osv-scanner", "pip-audit")}
SC_DIRECT = ("gitleaks", "semgrep", "bandit", "osv-scanner", "pip-audit")
SC_POLICY = ("security.md", "security.rst", "security.txt")
SC_POLICY_DIRS = ("", ".github", "docs")
SC_LICENSE = ("license", "licence", "copying")
SC_DEP_UPDATE = (".github/dependabot.yml", ".github/dependabot.yaml", "renovate.json", "renovate.json5", ".renovaterc",
                 ".renovaterc.json", ".renovaterc.json5", ".github/renovate.json", ".github/renovate.json5")
SC_BINARY = (".exe", ".dll", ".so", ".jar", ".class", ".pyc")
SC_SKIP = ("node_modules", "vendor")
# Manifest -> lockfiles that pin it. requirements*.txt also counts for the python manifests (see _locked).
SC_LOCKS = {"package.json": ("package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock"),
            "pyproject.toml": ("poetry.lock", "uv.lock", "pdm.lock", "Pipfile.lock"),
            "Pipfile": ("Pipfile.lock",), "Cargo.toml": ("Cargo.lock",), "go.mod": ("go.sum",),
            "Gemfile": ("Gemfile.lock",), "composer.json": ("composer.lock",)}
SC_PY = ("pyproject.toml", "Pipfile")


def _split(p):
    d, _s, b = p.rpartition("/")
    return d, b


def _policy(files):
    return any(_split(f)[0] in SC_POLICY_DIRS and _split(f)[1].lower() in SC_POLICY for f in files)


def _license(files):
    return any("/" not in f and f.lower().startswith(SC_LICENSE) for f in files)


def _locked(d, m, by_dir):
    """A lockfile for manifest `m` in dir `d` or an ancestor (⚠workspaces: Cargo/npm members share the root lockfile)."""
    while True:
        names = by_dir.get(d, ())
        if any(x in names for x in SC_LOCKS[m]):
            return True
        if m in SC_PY and any(x.startswith("requirements") and x.endswith(".txt") for x in names):
            return True
        if not d:
            return False
        d = _split(d)[0]


def _pinned(files):
    by_dir = {}
    for f in files:
        d, b = _split(f)
        by_dir.setdefault(d, set()).add(b)
    mans = [(d, b) for f in files for d, b in [_split(f)] if b in SC_LOCKS and not any(s in SC_SKIP for s in d.split("/"))]
    if not mans:
        return "na"
    return "pass" if all(_locked(d, b, by_dir) for d, b in mans) else "fail"


def _tokens(g):
    try:
        return shlex.split(g)
    except ValueError:
        return g.split()


def gate_tools(g):
    """Tool ids a gate string runs: the checks-security runner (all SEC_IDS, or its `--only` list) and direct tool commands."""
    out = set()
    if not isinstance(g, str):
        return out
    tk = _tokens(g)
    if gate_mode(g) == "checks-security":
        only = None
        for i, t in enumerate(tk):
            if t == "--only" and i + 1 < len(tk):
                only = tk[i + 1]
            elif t.startswith("--only="):
                only = t[len("--only="):]
        out |= set(SEC_IDS) if only is None else {x.strip() for x in only.split(",")} & set(SEC_IDS)
    for i, t in enumerate(tk):
        b = t.rsplit("/", 1)[-1]
        if i and tk[i - 1] == "--only":   # ⚠a tool id given to --only is a filter, not a command
            continue
        if b in SC_DIRECT:
            out.add(b)
        elif b == "npm" and i + 1 < len(tk) and tk[i + 1] == "audit":
            out.add("npm-audit")
    return out


def score(files, gates):
    """{n, m, checks:[{id, v}]} — pure. files = tracked repo-relative paths · gates = gate strings of every project
    pipeline, or None when the project has none (the three gate checks are then na). n = passes, m = checks not na."""
    files = [f for f in files or [] if isinstance(f, str) and f]
    v = {"security-policy": "pass" if _policy(files) else "fail",
         "license": "pass" if _license(files) else "fail",
         "pinned-deps": _pinned(files),
         "dep-update-tool": "pass" if any(f in SC_DEP_UPDATE for f in files) else "fail",
         "binary-artifacts": "fail" if any(f.lower().endswith(SC_BINARY) for f in files) else "pass"}
    tools = set()
    for g in gates or []:
        tools |= gate_tools(g)
    for cid, want in SC_GATE_TOOLS.items():
        v[cid] = "na" if gates is None else ("pass" if tools & set(want) else "fail")
    checks = [{"id": c, "v": v[c]} for c in SC_IDS]
    return {"n": sum(c["v"] == "pass" for c in checks), "m": sum(c["v"] != "na" for c in checks), "checks": checks}


def _tracked(proj):
    """Tracked paths (`git ls-files -z`, read-only through git_argv) or None outside a work tree / on failure."""
    try:
        r = gitinfo._git_run(proj, ["ls-files", "-z"], SC_TIMEOUT_S, wait=0.5)
        return [p for p in (r.stdout or "").split("\0") if p] if r.returncode == 0 else None
    except Exception:
        return None


def _mtimes(proj, names):
    out = []
    for n in names:
        try:
            out.append(os.path.getmtime(os.path.join(pipeline._pipe_dir(proj), n + ".json")))
        except OSError:
            out.append(0)
    return tuple(sorted(out))


def _gates(proj, names):
    """Gate strings of every readable project pipeline, or None when the project has no pipelines."""
    if not names:
        return None
    gates = []
    for n in names:
        _raw, P, err = pipeline._read_pipe(proj, n)
        if err or not isinstance(P, dict):
            continue
        gates += [s["gate"] for s in P.get("stages") or [] if isinstance(s, dict) and isinstance(s.get("gate"), str)]
    return gates


def scorecard(proj, head):
    """score() for a project at `head` (caller's HEAD sha), cached per (realpath, head, pipeline mtimes); None off git."""
    if not head:
        return None
    rp, names = os.path.realpath(proj), pipeline._names(proj)
    key = (head, _mtimes(proj, names))
    hit = SC_CACHE.get(rp)
    if hit and hit[0] == key:
        return hit[1]
    files = _tracked(proj)
    if files is None:
        return None
    res = score(files, _gates(proj, names))
    if len(SC_CACHE) >= SC_CACHE_MAX:
        SC_CACHE.clear()
    SC_CACHE[rp] = (key, res)
    return res
