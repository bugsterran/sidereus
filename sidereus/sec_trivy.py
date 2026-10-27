"""Trivy plans and parsers for the security runner: `trivy-config` (Dockerfile misconfig, default) and `trivy-image`
(base-image CVEs, only with `--images`, one plan per base image ref from Dockerfile FROM and compose `image:`).

⚠Metadata only: rule / CVE id · severity · line · package name · whether a fix exists · image ref. Message, Code,
Description and InstalledVersion are never read. `--scanners vuln` keeps trivy's secret scanner off.
⚠No subprocess here (AGENTS.md rule 7). Images are never built or started; credentials are never asked for, passed or
read — trivy itself uses the user's docker login. Stdlib only (compose is read by line regex, no yaml), Python 3.9.
"""
import json
import os
import re

from sidereus import sec_checks as SC
from sidereus.arch_checks_parse import SEV_RANK, clean_help

IDS = ("trivy-config", "trivy-image")
# ⚠fullmatch and a leading alnum: a ref can never read as a trivy flag (argv also puts `--` before it)
REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/:@-]{0,199}")
IMG_MAX = 20          # image plans per run (each pulls layers)
IMG_ITEMS_MAX = 100   # merged image findings kept, so code findings survive arch_checks.ITEMS_MAX
WHY_IMAGES = "add --images"
WHY_ARG = "FROM uses a build ARG"
WHY_BAD = "invalid image reference"
WHY_NO_DF = "no Dockerfile"
WHY_DB = "vuln DB download failed: set TRIVY_DB_REPOSITORY"
WHY_CHECKS = "checks download failed: set TRIVY_CHECKS_BUNDLE_REPOSITORY"
WHY_NOT_FOUND = "image not found"
_DF = re.compile(r"Dockerfile.*|.*\.[Dd]ockerfile")
_COMPOSE = re.compile(r"(?:docker-)?compose[^/]*\.ya?ml")
_FROM = re.compile(r"\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.I)
_IMAGE = re.compile(r"\s*-?\s*image:\s*[\"']?([^\"'\s#]+)")
_BUILD = re.compile(r"\s*-?\s*build:")
_HEREDOC = re.compile(r"<<-?\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?")
_DB = re.compile(r"vulnerability DB|DB error|trivy-db", re.I)
_CHECKS = re.compile(r"checks bundle|trivy-checks|policy bundle", re.I)
_AUTH = re.compile(r"UNAUTHORIZED|denied|\b401\b|\b403\b|authentication required", re.I)
_NOT_FOUND = re.compile(r"MANIFEST_UNKNOWN|NAME_UNKNOWN|not found", re.I)
_SEV = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}


def _walk(src):
    """(dockerfiles, compose files) repo-relative, one bounded walk (same skip set and caps as sec_checks.scan)."""
    dfs, cps, dirs = [], [], 0
    for dp, dns, fns in os.walk(src):
        rel = os.path.relpath(dp, src)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dns[:] = sorted(d for d in dns if d not in SC._SKIP and not d.startswith(".")) if depth < SC._WALK_DEPTH else []
        dirs += 1
        if dirs > SC._WALK_DIRS:
            break
        for f in sorted(fns):
            r = f if rel == "." else (rel.replace(os.sep, "/") + "/" + f)
            if _DF.fullmatch(f):
                dfs.append(r)
            elif _COMPOSE.fullmatch(f):
                cps.append(r)
    return dfs, cps


def refs(src):
    """[{ref, file, line}] base images in walk order: Dockerfile FROM (minus `scratch` and earlier stage aliases) and
    compose `image:`. Refs are raw here; detect() validates them."""
    dfs, cps = _walk(src)
    out = []
    for f in dfs:
        alias, cont, doc = set(), False, None
        for i, ln in enumerate(SC._read(os.path.join(src, f)).splitlines(), 1):
            # ⚠a continuation line or heredoc body (`RUN <<EOF … EOF`) may hold `from x import y`: never a FROM
            if doc is not None:
                doc = None if ln.strip() == doc else doc
                continue
            prev, cont = cont, ln.rstrip().endswith("\\")
            hd = _HEREDOC.search(ln)
            if hd:
                doc = hd.group(1)
            m = None if prev else _FROM.match(ln)
            if not m:
                continue
            ref = m.group(1)
            if ref.lower() != "scratch" and ref.lower() not in alias:
                out.append({"ref": ref, "file": f, "line": i})
            if m.group(2):
                alias.add(m.group(2).lower())
    for f in cps:
        out += _compose_refs(f, SC._read(os.path.join(src, f)))
    return out


def _compose_refs(f, text):
    """compose `image:` refs, minus services that also have `build:` (a locally built tag exists in no registry)."""
    stack, imgs, built = [], [], set()   # stack: (indent, line no) of open keys; a key's parent = enclosing block
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.lstrip()
        if not s or s.startswith("#"):
            continue
        ind = len(ln) - len(s)
        while stack and stack[-1][0] >= ind:
            stack.pop()
        parent = stack[-1][1] if stack else 0
        stack.append((ind, i))
        m = _IMAGE.match(ln)
        if m:
            imgs.append((parent, {"ref": m.group(1), "file": f, "line": i}))
        elif _BUILD.match(ln):
            built.add(parent)
    return [r for p, r in imgs if p not in built]


def detect(src, which, net=False, images=False):
    """Trivy plans (same shape as sec_checks.detect). No Dockerfile or compose file -> no rows at all."""
    dfs, cps = _walk(src)
    if not dfs and not cps:
        return []
    exe, out = which("trivy"), []
    if not dfs:
        out.append(SC._tool("trivy-config", "default", status="skipped", why=WHY_NO_DF))
    elif not exe:
        out.append(SC._tool("trivy-config", "default", status="missing", why=SC.install_hint("trivy")))
    else:
        argv = [exe, "config", "--misconfig-scanners", "dockerfile", "--format", "json", "--quiet"]
        argv += ([] if net else ["--skip-check-update"]) + ["."]
        out.append(SC._tool("trivy-config", "default", argv=argv, cwd=src, src="stdout", ok_rc=(0,), net=bool(net)))
    if not images:
        return out + [SC._tool("trivy-image", "default", status="skipped", why=WHY_IMAGES)]
    if not exe:
        return out + [SC._tool("trivy-image", "default", status="missing", why=SC.install_hint("trivy"))]
    seen, bad = set(), set()
    for r in refs(src):
        ref = r["ref"]
        if "$" in ref or not REF_RE.fullmatch(ref):
            if (r["file"], "$" in ref) not in bad:   # one row per file and reason
                bad.add((r["file"], "$" in ref))
                out.append(SC._tool("trivy-image", "default", status="skipped", why=WHY_ARG if "$" in ref else WHY_BAD))
            continue
        if ref in seen or len(seen) >= IMG_MAX:
            continue
        seen.add(ref)
        if not net:
            out.append(SC._tool("trivy-image", "default", status="skipped", why=SC.WHY_NET, target=ref))
            continue
        argv = [exe, "image", "--scanners", "vuln", "--image-src", "docker,remote", "--format", "json", "--quiet", "--", ref]
        out.append(SC._tool("trivy-image", "default", argv=argv, cwd=src, src="stdout", ok_rc=(0,), net=True, target=ref,
                            at=(r["file"], r["line"])))
    return out


def registry(ref):
    """Registry host of an image ref: first path part when it has '.' or ':' or is localhost, else docker.io."""
    head, slash, _rest = ref.partition("/")
    return head if slash and ("." in head or ":" in head or head == "localhost") else "docker.io"


def fail_why(plan, res):
    """Short reason for a failed trivy run (rc != 0), None otherwise; the caller judges it `fail`, never ok."""
    if res.get("rc") in (0, None) or res.get("timeout"):
        return None
    txt = (res.get("err") or "") + "\n" + (res.get("out") or "")
    if _DB.search(txt):
        return WHY_DB
    if plan.get("id") == "trivy-config":
        return WHY_CHECKS if _CHECKS.search(txt) else None
    ref = plan.get("target") or ""
    if _AUTH.search(txt):
        return "docker login %s needed" % registry(ref)
    if _NOT_FOUND.search(txt):
        return WHY_NOT_FOUND
    return None


def _jd(text):
    try:
        j = json.loads(text or "")
    except ValueError:
        raise ValueError("trivy: bad json")
    if not isinstance(j, dict):
        raise ValueError("trivy: not an object")
    return j


def _results(j):
    return [r for r in j.get("Results") or () if isinstance(r, dict)] if isinstance(j.get("Results"), list) else []


def _sev(s):
    return _SEV.get(str(s or "").lower(), "medium")


def _line(x):
    try:
        return max(0, int(x))
    except (TypeError, ValueError):
        return 0


def _item(f, line, rule, sev, url, title, pkg=None, fix=None):
    x = {"file": f if isinstance(f, str) else "", "line": _line(line), "rule": rule if isinstance(rule, str) else "",
         "sev": sev}
    if isinstance(pkg, str) and SC.PKG_RE.fullmatch(pkg):
        x["pkg"] = pkg
    if fix is not None:
        x["fix"] = bool(fix)
    h = clean_help(title, url)
    if h:
        x["help"] = h
    return x


def parse_config(text):
    """⚠Reads ID/AVDID · Severity · CauseMetadata.StartLine · PrimaryURL · Title only — never Message or Code."""
    out = []
    for r in _results(_jd(text)):
        for m in r.get("Misconfigurations") or () if isinstance(r.get("Misconfigurations"), list) else ():
            if isinstance(m, dict):
                cm = m.get("CauseMetadata") if isinstance(m.get("CauseMetadata"), dict) else {}
                out.append(_item(r.get("Target"), cm.get("StartLine"), m.get("ID") or m.get("AVDID"),
                                 _sev(m.get("Severity")), m.get("PrimaryURL"), m.get("Title")))
    return out


def parse_image(text):
    """⚠Reads VulnerabilityID · PkgName · Severity · PrimaryURL · Title and only the presence of FixedVersion — never
    Description or InstalledVersion. file stays "": the runner places it on the FROM / image: line (plan `at`)."""
    out = []
    for r in _results(_jd(text)):
        for v in r.get("Vulnerabilities") or () if isinstance(r.get("Vulnerabilities"), list) else ():
            if isinstance(v, dict):
                out.append(_item("", 0, v.get("VulnerabilityID"), _sev(v.get("Severity")), v.get("PrimaryURL"),
                                 v.get("Title"), v.get("PkgName"), bool(v.get("FixedVersion"))))
    return out


PARSERS = {"trivy-config": parse_config, "trivy-image": parse_image}


def files(plan, res, repo):
    """Files examined: config = Dockerfiles in the tree once trivy wrote a report; image = 1 per scanned image."""
    try:
        j = _jd(res.get("out"))
    except ValueError:
        return 0
    if "Results" not in j and "ArtifactName" not in j:
        return 0
    return len(_walk(repo)[0]) if plan["id"] == "trivy-config" else 1


def counts(items):
    """(fixable, waiting) high/critical findings of one image: with / without a fixed version."""
    hc = [x for x in items if x.get("sev") in ("critical", "high")]
    return sum(1 for x in hc if x.get("fix")), sum(1 for x in hc if not x.get("fix"))


def merge(items):
    """Image findings deduped per (CVE, package): worst severity, imgs = distinct images, fix = any; others unchanged.
    Capped at IMG_ITEMS_MAX (most severe first)."""
    rest, by = [], {}
    for x in items:
        if x.get("tool") != "trivy-image":
            rest.append(x)
            continue
        k = (x["rule"], x.get("pkg") or "")
        g = by.get(k)
        if g is None:
            by[k] = g = dict(x, _imgs=set())
        elif SEV_RANK[x["sev"]] < SEV_RANK[g["sev"]]:
            g["sev"] = x["sev"]
        g["_imgs"].add(x.get("img") or "")
        g["fix"] = bool(g.get("fix")) or bool(x.get("fix"))
    imgs = []
    for g in by.values():
        n = g.pop("_imgs")
        g.pop("img", None)
        imgs.append(dict(g, imgs=max(1, len(n))))
    imgs.sort(key=lambda x: (SEV_RANK[x["sev"]], x["rule"], x.get("pkg") or ""))
    return rest + imgs[:IMG_ITEMS_MAX]
