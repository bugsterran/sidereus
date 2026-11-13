"""SBOM + SCA for the security runner: `syft` writes a CycloneDX SBOM of the exported tree, `grype` matches it against
its vulnerability DB. Plans, the SBOM check, the grype parser and the fix summary helpers.

⚠Metadata only: grype findings keep file · package · version · CVE id · severity · fix version. description, urls,
matchDetails, purl and cvss are never read. The SBOM is stored beside checks-security.json; only counts reach the page.
⚠No subprocess here (AGENTS.md rule 7) and no build tool ever runs: Maven versions come from syft's own POM lookup
(Maven Central, online only, behind the runner's probe). cwd is the runner's temp dir so a repo `.syft.yaml` /
`.grype.yaml` is never read. Stdlib only, Python 3.9.
"""
import json
import os
import re

from sidereus import sec_checks as SC
from sidereus.arch_checks_parse import SEV_RANK

IDS = ("syft", "grype")
SBOM_FILE = "sbom.cdx.json"
SYFT_JSON = "sbom.syft.json"   # grype's input; stays in the runner's temp dir
SBOM_MAX = 64 * 1024 * 1024
VER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:~-]{0,63}")
ISO_Z_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")   # --source-name / --source-version values
WHY_NO_PKGS = "no packages found"
WHY_NO_SBOM = "needs syft SBOM"
WHY_DB = "vuln DB not available"
WHY_UNREADABLE = "unreadable SBOM"
ENV = {"SYFT_CHECK_FOR_APP_UPDATE": "false", "GRYPE_CHECK_FOR_APP_UPDATE": "false"}
PARENT_DEPTH = 10   # ⚠0 means unlimited to syft: keep a positive cap on parent POM recursion
NOTES = ("mvn-offline", "mvn-unresolved", "gradle-no-lock")
_UNSET = ("", "UNKNOWN")   # syft's version for a Maven dependency it could not resolve
FIXES_MAX = 20
# ⚠grype -q prints nothing on a DB failure (rc 1, empty stderr): the plan runs without -q so this can match
_DB = re.compile(r"vulnerability db|vulnerability database|database does not exist|max allowed age|"
                 r"db (?:is )?(?:stale|too old)|unable to update", re.I)
_SEV = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "negligible": "low"}


def _walk(src):
    """{pom, gradle, glock}: a pom.xml, a build.gradle(.kts), a gradle.lockfile anywhere in the bounded walk."""
    s, dirs = {"pom": False, "gradle": False, "glock": False}, 0
    for dp, dns, fns in os.walk(src):
        rel = os.path.relpath(dp, src)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dns[:] = sorted(d for d in dns if d not in SC._SKIP and not d.startswith(".")) if depth < SC._WALK_DEPTH else []
        dirs += 1
        if dirs > SC._WALK_DIRS:
            break
        s["pom"] = s["pom"] or "pom.xml" in fns
        s["gradle"] = s["gradle"] or "build.gradle" in fns or "build.gradle.kts" in fns
        s["glock"] = s["glock"] or "gradle.lockfile" in fns
    return s


def detect(src, which, net, name, ver):
    """[syft, grype] plans (sec_checks.detect shape). argv is completed by bind() with the runner's temp dir.
    syft is online only for a pom.xml (Maven parent/BOM versions); otherwise it never touches the network."""
    w, out = _walk(src), []
    nm = name if isinstance(name, str) and NAME_RE.fullmatch(name) else "repo"
    vr = ver if isinstance(ver, str) and NAME_RE.fullmatch(ver) else "unknown"
    exe = which("syft")
    if not exe:
        out.append(SC._tool("syft", "default", status="missing", why=SC.install_hint("syft")))
    else:
        online = bool(net) and w["pom"]
        env = dict(ENV, SYFT_JAVA_USE_NETWORK="true" if online else "false",
                   SYFT_JAVA_RESOLVE_TRANSITIVE_DEPENDENCIES="true" if online else "false",
                   SYFT_JAVA_USE_MAVEN_LOCAL_REPOSITORY="false")
        if online:
            env["SYFT_JAVA_MAX_PARENT_RECURSIVE_DEPTH"] = str(PARENT_DEPTH)
        notes = (["mvn-offline"] if w["pom"] and not online else []) + \
            (["gradle-no-lock"] if w["gradle"] and not w["glock"] else [])
        out.append(SC._tool("syft", "default", argv=[exe], dir=src, name=nm, ver=vr, src="sbom", ok_rc=(0,), env=env,
                            net=online, notes=notes, pom=w["pom"]))
    exe = which("grype")
    out.append(SC._tool("grype", "default", status="missing", why=SC.install_hint("grype")) if not exe else
               SC._tool("grype", "default", status="skipped", why=SC.WHY_NET) if not net else
               SC._tool("grype", "default", argv=[exe], src="stdout", ok_rc=(0,), env=dict(ENV), net=True))
    return out


def bind(plan, tmp):
    """Plan with its full argv, cwd = tmp (no repo config is read) and its SBOM paths inside tmp."""
    cdx, sj = os.path.join(tmp, SBOM_FILE), os.path.join(tmp, SYFT_JSON)
    exe = plan["argv"][0]
    if plan["id"] == "syft":
        argv = [exe, "scan", "dir:" + plan["dir"], "-q", "--source-name", plan["name"], "--source-version", plan["ver"],
                "-o", "cyclonedx-json=" + cdx, "-o", "syft-json=" + sj]
    else:
        argv = [exe, "sbom:" + sj, "--by-cve", "-o", "json"]
    return dict(plan, argv=argv, cwd=tmp, tmp=tmp, sbom=cdx)


def _sbom_bytes(plan):
    """The CycloneDX file's bytes: a regular file (no symlink) under plan tmp, at most SBOM_MAX; else None."""
    fp, tmp = plan.get("sbom") or "", plan.get("tmp") or ""
    try:
        st = os.lstat(fp)
        root = os.path.realpath(tmp)
        if not tmp or not os.path.isfile(fp) or os.path.islink(fp) or st.st_size > SBOM_MAX \
                or not os.path.realpath(fp).startswith(root + os.sep):
            return None
        with open(fp, "rb") as f:
            b = f.read(SBOM_MAX + 1)
    except OSError:
        return None
    return b if len(b) <= SBOM_MAX else None


def sbom_doc(plan):
    """(bytes, components, files, unresolved) of a valid CycloneDX SBOM, None otherwise. components = non-`file`
    entries; files = distinct `syft:location:*:path` values (at least 1 when there are components); unresolved =
    Maven components (purl pkg:maven/) with an empty or UNKNOWN version."""
    b = _sbom_bytes(plan)
    if b is None:
        return None
    try:
        j = json.loads(b.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(j, dict) or j.get("bomFormat") != "CycloneDX":
        return None
    comps = j.get("components") if isinstance(j.get("components"), list) else []
    n, paths, unres = 0, set(), 0
    for c in comps:
        if not isinstance(c, dict) or c.get("type") == "file":
            continue
        n += 1
        # ⚠syft logs nothing when Maven Central is unreachable: an unresolved version is the only evidence
        if str(c.get("purl") or "").startswith("pkg:maven/") and str(c.get("version") or "") in _UNSET:
            unres += 1
        for p in c.get("properties") or () if isinstance(c.get("properties"), list) else ():
            k = p.get("name") if isinstance(p, dict) else None
            if isinstance(k, str) and k.startswith("syft:location:") and k.endswith(":path") and isinstance(p.get("value"), str):
                paths.add(p["value"])
    return b, n, (max(1, len(paths)) if n else 0), unres


def sbom_state(plan):
    """(components, files) or None (see sbom_doc)."""
    d = sbom_doc(plan)
    return None if d is None else (d[1], d[2])


def notes(plan, res, unresolved=0):
    """Note codes of a syft row: the plan's own (offline pom.xml, Gradle without lockfile), a network error on stderr,
    and `mvn-unresolved` when the SBOM holds Maven components without a version (online or offline)."""
    out = list(plan.get("notes") or ()) + (["mvn-unresolved"] if unresolved else [])
    if plan.get("pom") and "mvn-offline" not in out and SC.NET_RE.search(res.get("err") or ""):
        out.insert(0, "mvn-offline")
    return [n for n in NOTES if n in out]


def fail_why(plan, res):
    """WHY_DB when grype failed to load, update or trust its vulnerability DB; None otherwise (caller: skipped)."""
    if plan.get("id") != "grype" or res.get("rc") in (0, None) or res.get("timeout"):
        return None
    return WHY_DB if _DB.search((res.get("err") or "") + "\n" + (res.get("out") or "")) else None


def _jd(text):
    try:
        j = json.loads(text or "")
    except ValueError:
        raise ValueError("grype: bad json")
    if not isinstance(j, dict):
        raise ValueError("grype: not an object")
    return j


def _ver(v):
    return v if isinstance(v, str) and VER_RE.fullmatch(v) else None


def parse_grype(text):
    """⚠Reads vulnerability.id/severity/fix.versions, relatedVulnerabilities[].id, artifact.name/version and
    locations[0].path only. file "" = no location (the judge drops it and counts it)."""
    j, out, seen = _jd(text), [], set()
    for m in j.get("matches") or () if isinstance(j.get("matches"), list) else ():
        if not isinstance(m, dict):
            continue
        v = m.get("vulnerability") if isinstance(m.get("vulnerability"), dict) else {}
        a = m.get("artifact") if isinstance(m.get("artifact"), dict) else {}
        rule = v.get("id") if isinstance(v.get("id"), str) else ""
        locs = a.get("locations") if isinstance(a.get("locations"), list) else []
        p = locs[0].get("path") if locs and isinstance(locs[0], dict) else None
        f = p.lstrip("/") if isinstance(p, str) else ""
        pkg = a.get("name") if isinstance(a.get("name"), str) and SC.PKG_RE.fullmatch(a.get("name")) else None
        ver = _ver(a.get("version"))
        k = (rule, pkg, ver, f)
        if k in seen:
            continue
        seen.add(k)
        fx = v.get("fix") if isinstance(v.get("fix"), dict) else {}
        fixv = next((x for x in fx.get("versions") or () if _ver(x)), None) if isinstance(fx.get("versions"), list) else None
        rel = [r.get("id") for r in m.get("relatedVulnerabilities") or () if isinstance(r, dict)] \
            if isinstance(m.get("relatedVulnerabilities"), list) else []
        x = {"file": f, "line": 1, "rule": rule, "sev": _SEV.get(str(v.get("severity") or "").lower(), "medium")}
        if pkg:
            x["pkg"] = pkg
        if ver:
            x["ver"] = ver
        if fixv:
            x["fixv"] = fixv
        cv = SC.cves([c for c in rel if c != rule])
        if cv:
            x["cve"] = cv
        out.append(x)
    return out


PARSERS = {"grype": parse_grype}


def db_built(text):
    """grype's DB build time (ISO-Z) from `descriptor.db.status.built` (v6) or `descriptor.db.built` (older); None
    when absent or malformed — never 0 or the epoch."""
    try:
        d = (_jd(text).get("descriptor") or {}).get("db")
    except (ValueError, AttributeError):
        return None
    if not isinstance(d, dict):
        return None
    st = d.get("status") if isinstance(d.get("status"), dict) else {}
    b = st.get("built", d.get("built"))
    return b if isinstance(b, str) and ISO_Z_RE.fullmatch(b) else None


def files(plan, res, repo):
    """syft: distinct package locations in the SBOM; grype: the syft count passed in by the runner (`sbom_files`)."""
    if plan["id"] == "syft":
        s = sbom_state(plan)
        return s[1] if s else 0
    n = plan.get("sbom_files")
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else 0


def vkey(v):
    """Natural sort key of a version: numbers compare as numbers; a pre-release tag sorts below its release."""
    ts = re.findall(r"\d+|[A-Za-z]+", v)
    i = next((k for k, t in enumerate(ts) if not t.isdigit()), len(ts))
    while i > 1 and int(ts[i - 1]) == 0:   # 1.10.0 == 1.10, so 1.10.0-rc1 stays below 1.10
        del ts[i - 1]
        i -= 1
    return tuple((2, int(t), "") if t.isdigit() else (0, 0, t.lower()) for t in ts) + ((1, 0, ""),)


def fixes(items):
    """([{pkg, ver, to, n, sev}], more): grype items grouped by (pkg, ver); to = highest fix version, n = CVEs that
    have one, sev = worst among them. Worst severity first, capped at FIXES_MAX; more = groups left out."""
    by = {}
    for x in items:
        if x.get("tool") != "grype" or not x.get("pkg") or not x.get("ver") or not x.get("fixv"):
            continue
        g = by.setdefault((x["pkg"], x["ver"]), {"to": x["fixv"], "rules": set(), "sev": x["sev"]})
        if vkey(x["fixv"]) > vkey(g["to"]):
            g["to"] = x["fixv"]
        if SEV_RANK[x["sev"]] < SEV_RANK[g["sev"]]:
            g["sev"] = x["sev"]
        g["rules"].add(x["rule"])
    rows = [{"pkg": p, "ver": v, "to": g["to"], "n": len(g["rules"]), "sev": g["sev"]} for (p, v), g in by.items()]
    rows.sort(key=lambda r: (SEV_RANK[r["sev"]], -r["n"], r["pkg"], r["ver"]))
    return rows[:FIXES_MAX], max(0, len(rows) - FIXES_MAX)
