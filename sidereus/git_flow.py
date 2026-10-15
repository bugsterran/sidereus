"""Remote freshness and git-flow config (split out of sidereus/git_view.py for the size cap). Files and a caller-given
`run` only — no git call of its own, no mutable state; git_view re-exports the names git/git_rail import."""
import os
import re


# ── Remote freshness: ahead/behind vs a remote is only as fresh as the last fetch. Files only, no git call.
BR_FETCH_STALE_H = 24       # client mutes remote ahead/behind when the newest fetch is older than this
_CFG_REMOTE = re.compile(r'^\[\s*remote\s+"([^"]+)"\s*\]')
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_URL_SCP = re.compile(r"^(?:[^@/:\s]+@)?([^@/:\s]+):")


def _git_common_dir(cwd):
    """Common git dir shared by all worktrees of the repo containing cwd, from `.git`/`commondir` files; '' if none."""
    cur = os.path.abspath(cwd or "/")
    while True:
        g = os.path.join(cur, ".git")
        if os.path.isdir(g):
            return g
        if os.path.isfile(g):
            try:
                with open(g, encoding="utf-8") as f:
                    s = f.read(1000).strip()
            except OSError:
                return ""
            if not s.startswith("gitdir:"):
                return ""
            gd = os.path.normpath(os.path.join(cur, s.split(":", 1)[1].strip()))
            try:
                with open(os.path.join(gd, "commondir"), encoding="utf-8") as f:
                    return os.path.normpath(os.path.join(gd, f.read(1000).strip()))
            except OSError:
                return gd                 # no commondir (e.g. submodule gitdir) -> it is its own common dir
        up = os.path.dirname(cur)
        if up == cur:
            return ""
        cur = up


def _url_host(url):
    """Remote URL -> (host, local). Host only — ⚠never user/token/path (the page shows it)."""
    u = (url or "").strip()
    m = _URL_SCHEME.match(u)
    if m:
        if u.lower().startswith("file:"):
            return "", True
        auth = u[m.end():].split("/", 1)[0].rsplit("@", 1)[-1]
        host = auth[1:].split("]", 1)[0] if auth.startswith("[") else auth.split(":", 1)[0]
        return host.lower(), False
    if not u or u.startswith(("/", ".", "~")):
        return "", True
    m = _URL_SCP.match(u)
    return (m.group(1).lower(), False) if m else ("", True)


def _git_remotes(common):
    """[{name, host, local}] from `<common>/config` (first url per remote; includes ignored)."""
    out, cur = [], None
    try:
        with open(os.path.join(common, "config"), encoding="utf-8", errors="replace") as f:
            lines = f.read(200_000).splitlines()
    except OSError:
        return out
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            m = _CFG_REMOTE.match(s)
            cur = None
            if m:
                cur = next((r for r in out if r["name"] == m.group(1)), None)
                if cur is None:
                    cur = {"name": m.group(1), "host": "", "local": False, "_u": False}
                    out.append(cur)
            continue
        if cur is not None and not cur["_u"] and "=" in s:
            k, v = s.split("=", 1)
            if k.strip().lower() == "url":
                cur["host"], cur["local"] = _url_host(v.strip().strip('"'))
                cur["_u"] = True
    for r in out:
        r.pop("_u", None)
    return out


def _fetch_at(common):
    """Newest FETCH_HEAD mtime (int) or None = never fetched.
    ⚠FETCH_HEAD is per-worktree (a fetch run in a worktree writes worktrees/<n>/FETCH_HEAD), but remote refs are shared."""
    best = None
    paths = [os.path.join(common, "FETCH_HEAD")]
    try:
        wd = os.path.join(common, "worktrees")
        paths += [os.path.join(wd, n, "FETCH_HEAD") for n in os.listdir(wd)[:200]]
    except OSError:
        pass                      # no worktrees dir: only the common FETCH_HEAD
    for p in paths:
        try:
            t = int(os.path.getmtime(p))
        except OSError:
            continue
        best = t if best is None else max(best, t)
    return best


def remote_info(cwd):
    """-> [{name, host, local, fetchAt}] (fetchAt is repo-wide: one FETCH_HEAD time for every remote)."""
    common = _git_common_dir(cwd)
    if not common:
        return []
    at = _fetch_at(common)
    rs = _git_remotes(common)
    for r in rs:
        r["fetchAt"] = at
    return rs


# ── git-flow: read-only config -> branch types, bases, PR targets.
FLOW_TYPES = ("feature", "bugfix", "release", "hotfix", "support")
FLOW_PREFIX_DEF = {t: t + "/" for t in FLOW_TYPES}


def flow_parse(cfg_text, local_names):
    """Pure: `git config --get-regexp '^gitflow\\.'` output + local branch names -> flow dict."""
    names, got, br, pre = set(local_names or ()), False, {}, dict(FLOW_PREFIX_DEF)
    for ln in (cfg_text or "").splitlines():
        k, _, v = ln.strip().partition(" ")
        k, v = k.lower(), v.strip()
        if not k.startswith("gitflow."):
            continue
        got = True
        if k.startswith("gitflow.branch.") and v:
            br[k[15:]] = v
        elif k.startswith("gitflow.prefix.") and k[15:] in pre:
            pre[k[15:]] = v             # ⚠an empty configured prefix is legal in git-flow — keep it
    dev = br.get("develop") or ("develop" if "develop" in names else None)
    mst = br.get("master") or next((n for n in ("main", "master") if n in names), None)
    return {"develop": dev, "master": mst, "prefix": pre, "src": "gitflow-config" if got else "default"}


def flow_base(branch, flow, fallback):
    """Pure: (base, prTargets) for a branch by its git-flow type; other names -> (fallback, [])."""
    if not flow or not branch:
        return fallback, []
    pre, dev, mst = flow.get("prefix") or {}, flow.get("develop"), flow.get("master")
    dpr = flow.get("devName") or dev          # PR target is the branch name, not the origin/develop ref
    mpr = flow.get("mstName") or mst
    typ = next((t for t in ("feature", "bugfix", "release", "hotfix")
                if pre.get(t) and branch.startswith(pre[t])), "")
    if typ in ("feature", "bugfix") and (dev or mst):
        return dev or mst, [dpr or mpr]
    if typ in ("release", "hotfix") and mst:
        return mst, [x for x in (mpr, dpr) if x]
    return fallback, []


def flow_info(run, local_names):
    """Runs one read-only `git config --get-regexp`; exit 1 (no keys) is normal -> defaults."""
    r = run(["config", "--get-regexp", r"^gitflow\."])
    f = flow_parse(r.stdout if r.returncode == 0 else "", local_names)
    want = f["develop"] or "develop"
    if want not in set(local_names or ()):
        # ⚠A fresh clone has develop only as <remote>/develop — base on that ref instead of silently using master.
        rr = run(["for-each-ref", "--format=%(refname:short)", "refs/remotes/*/" + want])
        f = flow_remote_dev(f, rr.stdout.split() if rr.returncode == 0 else [], want)
    if not f["master"] or f["master"] not in set(local_names or ()):
        # ⚠Same for master/main (release/hotfix base and PR target); a configured name is looked up as-is.
        names = [f["master"]] if f["master"] else ["main", "master"]
        rr = run(["for-each-ref", "--format=%(refname:short)"] + ["refs/remotes/*/" + n for n in names])
        ref = _remote_pick(rr.stdout.split() if rr.returncode == 0 else [], names)
        if ref:
            f = dict(f, master=ref, mstRemote=ref.partition("/")[0], mstName=ref.partition("/")[2])
    return f


def _remote_pick(remote_refs, names):
    """Pure: first `<remote>/<name>` by name priority, origin preferred within a name; None if absent."""
    for n in names:
        refs = [x for x in remote_refs if x.partition("/")[2] == n]
        if refs:
            return "origin/" + n if "origin/" + n in refs else sorted(refs)[0]
    return None


def flow_remote_dev(flow, remote_refs, want="develop"):
    """Pure: point `develop` at `<remote>/<want>` (origin preferred) when only a remote ref exists."""
    ref = _remote_pick(remote_refs, [want])
    if not ref:
        return flow
    return dict(flow, develop=ref, devRemote=ref.partition("/")[0], devName=want)
