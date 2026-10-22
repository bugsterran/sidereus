#!/usr/bin/python3
"""Refactor equivalence harness for chat_server.py (stdlib only, run with /usr/bin/python3).

  snap.py take <name> [--params <snap>]   capture pages, API shapes and module names from the live server
  snap.py diff <a> <b>                    compare two snapshots; exit 0 only when equivalent

Snapshots live in refactor/snap/<name>/ (gitignored: they hold live metadata, never publish them).
"""
import fnmatch
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import difflib
import contextlib
import urllib.error
import urllib.request
from urllib.parse import quote, urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mailbox_config  # noqa: E402

BASE_URL = "http://127.0.0.1:%d" % mailbox_config.port()   # live viewer: env SIDEREUS_PORT > config `port` > 8799
HERE = os.path.dirname(os.path.abspath(__file__))
SNAP_DIR = os.path.join(HERE, "snap")
SERVER_PY = os.path.join(os.path.dirname(HERE), "chat_server.py")
VOLATILE = os.path.join(HERE, "volatile.json")

# Page-body normalisation. Each entry: (label, regex, replacement).
# MY_BUILD is sha256(PAGE)[:12] computed at import; it changes whenever PAGE bytes change, so it is
# recorded raw in meta.json and masked for comparison (otherwise any byte change is reported twice).
PAGE_NORMALISE = [
    ("MY_BUILD", re.compile(r"(const MY_BUILD = ')[0-9a-f]{12}(')"), r"\1<BUILD>\2"),
]


def _get(path, timeout=180):
    req = urllib.request.Request(BASE_URL + path)   # no Accept-Encoding -> plain body
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # nosec B310 -- constant loopback http base
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


# ---------- params: pick live inputs once, then reuse them so later stages hit the same inputs ----------

def discover_params():
    _, _, body = _get("/api/state")
    st = json.loads(body)
    sess = st.get("sessions") or []
    sidereus = os.path.dirname(HERE)
    pick = next((s for s in sess if s.get("cwd") == sidereus), None) or (sess[0] if sess else {})
    cwd = pick.get("cwd") or sidereus
    tid = ""
    for s in [pick] + sess:
        for a in s.get("sub") or []:
            if a.get("tid"):
                tid, cwd = a["tid"], s.get("cwd") or cwd
                break
        if tid:
            break
    sid = next((s.get("sid") for s in sess if s.get("cwd") == cwd and s.get("sid")), "")
    try:
        sha = subprocess.run(["git", "-C", sidereus, "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10).stdout.strip()
    except Exception:
        sha = ""
    return {"cwd": cwd, "sid": sid, "tid": tid, "repo": sidereus, "sha": sha,
            "file": "chat_server.py", "smallfile": ".gitignore"}


def routes(p):
    q = lambda v: quote(v or "", safe="")
    c, r = q(p["cwd"]), q(p["repo"])
    pages = [
        "/",
        "/diff?cwd=" + c,
        "/work?cwd=%s&tid=%s" % (c, q(p["tid"])),
        "/brdiff?repo=%s&sha=%s&path=%s" % (r, q(p["sha"]), q(p["smallfile"])),
    ]
    apis = [
        "/api/state",
        "/api/state?since=0&cards=300",
        "/api/cards?n=300",
        "/api/live",
        "/api/otel",
        "/api/quota/burn",
        "/api/wkuse?range=7",
        "/api/history?days=7",
        "/api/agents/timeline",
        "/api/failures",
        "/api/wreckage",
        "/api/structure",
        "/api/structure/src?file=%s&line=1&lines=40" % q(p["file"]),
        "/api/branches?cwd=" + r,
        "/api/git/wtfiles?cwd=" + r,
        "/api/git/commit?repo=%s&sha=%s" % (r, q(p["sha"])),
        "/api/git/commit?repo=%s&sha=%s&path=%s" % (r, q(p["sha"]), q(p["smallfile"])),
        "/api/git/diff?cwd=%s&scope=all&pw=today" % r,
        "/api/git/file?cwd=%s&path=%s&scope=all" % (r, q(p["smallfile"])),
        "/api/agent/work?cwd=%s&tid=%s" % (c, q(p["tid"])),
        "/api/session/work?cwd=%s&sid=%s" % (c, q(p["sid"])),
        "/api/session/work?cwd=" + c,
        # error paths: status codes must survive the refactor too
        "/api/branches",
        "/api/git/commit?repo=%s&sha=zz" % r,
        "/api/nope",
        "/nope",
    ]
    return pages, apis


# ---------- page assembly (stage 2 moves JS/CSS out; compare the assembled document too) ----------

_SCRIPT_SRC = re.compile(r'<script\b[^>]*\bsrc=["\']?([^"\' >]+)["\']?[^>]*>\s*</script>', re.I)
_LINK_CSS = re.compile(r'<link\b[^>]*\brel=["\']?stylesheet["\']?[^>]*>', re.I)
_HREF = re.compile(r'\bhref=["\']?([^"\' >]+)', re.I)


def assemble(page_path, text, assets):
    """Inline same-origin <script src> and stylesheet <link> so a split page compares to the monolith."""
    def fetch(ref):
        u = urljoin(BASE_URL + page_path, ref)
        if urlparse(u).netloc != urlparse(BASE_URL).netloc:
            return None
        pth = urlparse(u).path + (("?" + urlparse(u).query) if urlparse(u).query else "")
        if pth not in assets:
            code, _, b = _get(pth)
            assets[pth] = b.decode("utf-8", "replace") if code == 200 else None
        return assets[pth]

    def rs(m):
        b = fetch(m.group(1))
        return m.group(0) if b is None else "<script>" + b + "</script>"

    def rl(m):
        h = _HREF.search(m.group(0))
        b = fetch(h.group(1)) if h else None
        return m.group(0) if b is None else "<style>" + b + "</style>"

    return _LINK_CSS.sub(rl, _SCRIPT_SRC.sub(rs, text))


def normalise_page(text):
    for _, rx, rep in PAGE_NORMALISE:
        text = rx.sub(rep, text)
    return text


# ---------- JSON shape ----------

_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _tname(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "num"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    return "dict"


def _is_map(path, d, maps):
    if any(_pglob(path, m) for m in maps):
        return True
    # Heuristic: keys that are not identifiers (paths, ids with '-', ':', digits first, non-ascii) = data-keyed map
    return bool(d) and any(not _IDENT.match(k) for k in d)


def shape(v, maps):
    types, empties = {}, set()

    def walk(x, path):
        types.setdefault(path, set()).add(_tname(x))
        if isinstance(x, dict):
            if _is_map(path, x, maps):
                if not x:
                    empties.add(path + "{*}")
                for val in x.values():
                    walk(val, path + "{*}")
            else:
                for k, val in x.items():
                    walk(val, path + "." + k)
        elif isinstance(x, list):
            if not x:
                empties.add(path + "[]")
            for e in x:
                walk(e, path + "[]")

    walk(v, "$")
    return {"types": {k: sorted(s) for k, s in sorted(types.items())}, "empty": sorted(empties)}


def maps_for(route, vol):
    """Shape-path globs whose dict keys are data for this route; `maps` is a list (all routes) or route glob -> list."""
    m = vol.get("maps", [])
    if isinstance(m, list):
        return m
    return [x for pat, xs in m.items() if fnmatch.fnmatchcase(route, pat) for x in xs]


def _pglob(path, pat):
    # Shape paths contain '[]' and '{*}', which fnmatch reads as char classes: only '*' is a wildcard here.
    return re.fullmatch(re.escape(pat).replace(r"\*", ".*"), path) is not None


_SEG = re.compile(r"\.[^.\[{]+|\[\]|\{\*\}")


def fold_shape(sh, maps):
    """Re-fold a stored shape with the current maps, so snapshots taken before a map was listed compare too."""
    if not maps or not sh:
        return sh
    def fold(path):
        cur, rest = path[:1], path[1:]
        for tok in _SEG.findall(rest):
            cur += "{*}" if tok[0] == "." and any(_pglob(cur, m) for m in maps) else tok
        return cur
    types = {}
    for p, ts in sh["types"].items():
        types.setdefault(fold(p), set()).update(ts)
    empties = {fold(e) for e in sh["empty"]}
    # A listed map seen only as an empty dict has no {*} child: record it as empty so either side may be empty.
    for p, ts in types.items():
        if "dict" in ts and any(_pglob(p, m) for m in maps) and p + "{*}" not in types:
            empties.add(p + "{*}")
    return {"types": {k: sorted(v) for k, v in sorted(types.items())}, "empty": sorted(empties)}


def load_volatile():
    try:
        with open(VOLATILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"maps": [], "optional": {}}


# ---------- module names ----------

def module_names():
    spec = importlib.util.spec_from_file_location("cs", SERVER_PY)
    cs = importlib.util.module_from_spec(spec)
    sys.modules["cs"] = cs
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(cs)   # main() sits behind __main__: no threads, live server untouched
    # Since 1e261ef chat_server.py is a thin entry point and the code lives in sidereus/<module>.py, so the
    # check is the union of top-level names over chat_server + every loaded sidereus.* module, keyed by bare
    # name (a name moving between modules is not a difference; a name vanishing everywhere is).
    # ⚠Snapshots taken before this change hold chat_server names only: diff them against each other only.
    mods = [cs] + [m for k, m in sorted(sys.modules.items())
                   if m is not None and (k == "sidereus" or k.startswith("sidereus."))]
    kinds = {}
    for m in mods:
        for n, v in vars(m).items():
            if n.startswith("__") and n.endswith("__"):
                continue
            if m is not cs and getattr(v, "__name__", "").startswith("sidereus.") and type(v).__name__ == "module":
                continue   # package attribute for a submodule (sidereus.state vs state()): not a name of ours
            kinds.setdefault(n, set()).add(type(v).__name__)
    out = ["# scope: chat_server + %d sidereus modules" % (len(mods) - 1)]
    for n in sorted(kinds):
        out.append("%s\t%s" % (n, "|".join(sorted(kinds[n]))))
    return out


# ---------- take ----------

def _key(route):
    return re.sub(r"[^A-Za-z0-9]+", "_", route).strip("_") or "root"


def take(name, params_from=None):
    d = os.path.join(SNAP_DIR, name)
    os.makedirs(os.path.join(d, "pages"), exist_ok=True)
    src = params_from or ("base" if name != "base" and os.path.isfile(
        os.path.join(SNAP_DIR, "base", "params.json")) else None)
    if src:
        with open(os.path.join(SNAP_DIR, src, "params.json"), encoding="utf-8") as f:
            params = json.load(f)
    else:
        params = discover_params()
    vol = load_volatile()
    pages, apis = routes(params)
    meta = {"params": params, "paramsFrom": src, "pages": {}, "apis": {}}

    assets = {}
    for r in pages:
        code, ct, body = _get(r)
        text = body.decode("utf-8", "replace")
        builds = [m.group(0) for _, rx, _ in PAGE_NORMALISE for m in rx.finditer(text)]
        k = _key(r)
        with open(os.path.join(d, "pages", k + ".html"), "wb") as f:
            f.write(body)
        asm = assemble(urlparse(r).path, text, assets)
        with open(os.path.join(d, "pages", k + ".assembled.html"), "w", encoding="utf-8") as f:
            f.write(asm)
        meta["pages"][r] = {"status": code, "ctype": ct, "sha256": hashlib.sha256(body).hexdigest(),
                            "bytes": len(body), "file": k, "volatile": builds,
                            "normSha256": hashlib.sha256(normalise_page(asm).encode()).hexdigest()}
    shapes = {}
    for r in apis:
        code, ct, body = _get(r)
        ent = {"status": code, "ctype": ct, "bytes": len(body)}
        if "json" in ct:
            try:
                ent["shape"] = shape(json.loads(body), maps_for(r, vol))
            except ValueError as e:
                ent["shape"] = None
                ent["err"] = "bad json: %s" % e
        else:
            ent["text"] = body.decode("utf-8", "replace")[:200]
        shapes[r] = ent
        print("  %-3s %-7d %s" % (code, len(body), r))
    with open(os.path.join(d, "api.json"), "w", encoding="utf-8") as f:
        json.dump(shapes, f, ensure_ascii=False, indent=1, sort_keys=True)
    with open(os.path.join(d, "params.json"), "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=1)
    names = module_names()
    with open(os.path.join(d, "names.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print("took %s: %d pages, %d api routes, %d names (params from %s)"
          % (name, len(pages), len(apis), sum("\t" in l for l in names), src or "live"))


# ---------- diff ----------

def _load(name):
    d = os.path.join(SNAP_DIR, name)
    with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    with open(os.path.join(d, "api.json"), encoding="utf-8") as f:
        api = json.load(f)
    with open(os.path.join(d, "names.txt"), encoding="utf-8") as f:
        names = dict(l.rstrip("\n").split("\t", 1) for l in f if "\t" in l)
    return d, meta, api, names


def _scope(name):
    with open(os.path.join(SNAP_DIR, name, "names.txt"), encoding="utf-8") as f:
        first = f.readline()
    return first[len("# scope: "):].strip() if first.startswith("# scope: ") else "chat_server only"


def _under(path, prefixes):
    return any(path == p or path.startswith(p + ".") or path.startswith(p + "[")
               or path.startswith(p + "{") for p in prefixes)


def shape_diff(route, a, b, vol):
    out = []
    if a["status"] != b["status"]:
        out.append("status %s -> %s" % (a["status"], b["status"]))
    if a["ctype"] != b["ctype"]:
        out.append("ctype %r -> %r" % (a["ctype"], b["ctype"]))
    mp = maps_for(route, vol)
    sa, sb = fold_shape(a.get("shape"), mp), fold_shape(b.get("shape"), mp)
    if (sa is None) != (sb is None):
        out.append("json-ness changed")
    if not sa or not sb:
        if "text" in a and a.get("text") != b.get("text"):
            out.append("text body %r -> %r" % (a.get("text"), b.get("text")))
        return out
    empties = set(sa["empty"]) | set(sb["empty"])
    opt = []
    for pat, pats in vol.get("optional", {}).items():
        if fnmatch.fnmatchcase(route, pat):
            opt += pats
    ok_path = lambda p: _under(p, empties) or any(fnmatch.fnmatchcase(p, o) for o in opt)
    ta, tb = sa["types"], sb["types"]
    for p in sorted(set(ta) - set(tb)):
        if not ok_path(p):
            out.append("missing %s" % p)
    for p in sorted(set(tb) - set(ta)):
        if not ok_path(p):
            out.append("new     %s" % p)
    for p in sorted(set(ta) & set(tb)):
        xa, xb = set(ta[p]) - {"null"}, set(tb[p]) - {"null"}
        if xa and xb and xa != xb and not ok_path(p):
            out.append("type    %s %s -> %s" % (p, sorted(ta[p]), sorted(tb[p])))
    return out


def diff(an, bn):
    da, ma, aa, na = _load(an)
    db, mb, ab, nb = _load(bn)
    vol = load_volatile()
    bad = 0
    print("== pages")
    for r, pa in ma["pages"].items():
        pb = mb["pages"].get(r)
        if not pb:
            print("  MISSING %s" % r); bad += 1; continue
        if pa["status"] != pb["status"] or pa["ctype"] != pb["ctype"]:
            print("  DIFF    %s status/ctype %s %r -> %s %r" % (r, pa["status"], pa["ctype"],
                                                               pb["status"], pb["ctype"])); bad += 1
        if pa["sha256"] == pb["sha256"]:
            print("  same    %s (byte-exact)" % r); continue
        if pa["normSha256"] == pb["normSha256"]:
            print("  same    %s (after normalising %s / assembling assets)"
                  % (r, ",".join(l for l, _, _ in PAGE_NORMALISE))); continue
        bad += 1
        print("  DIFF    %s" % r)
        ra = normalise_page(open(os.path.join(da, "pages", pa["file"] + ".assembled.html"),
                                 encoding="utf-8").read()).splitlines()
        rb = normalise_page(open(os.path.join(db, "pages", pb["file"] + ".assembled.html"),
                                 encoding="utf-8").read()).splitlines()
        ud = list(difflib.unified_diff(ra, rb, an, bn, n=1, lineterm=""))
        for l in ud[:40]:
            print("    " + l[:200])
        if len(ud) > 40:
            print("    ... (%d more diff lines)" % (len(ud) - 40))
    print("== api")
    for r, xa in aa.items():
        xb = ab.get(r)
        if xb is None:
            print("  MISSING %s" % r); bad += 1; continue
        d = shape_diff(r, xa, xb, vol)
        if d:
            bad += 1
            print("  DIFF    %s" % r)
            for l in d[:30]:
                print("    " + l)
            if len(d) > 30:
                print("    ... (%d more)" % (len(d) - 30))
        else:
            print("  same    %s" % r)
    print("== names")
    sa, sb = _scope(an), _scope(bn)
    if sa.split(" + ")[0] != sb.split(" + ")[0]:
        print("  ⚠scope differs (%s vs %s): take both snapshots with the same snap.py" % (sa, sb))
    miss = sorted(set(na) - set(nb))
    kind = sorted(n for n in set(na) & set(nb) if na[n] != nb[n])
    new = sorted(set(nb) - set(na))
    if miss:
        bad += 1
        print("  missing (%d): %s" % (len(miss), " ".join(miss[:80])))
    if kind:
        bad += 1
        print("  kind changed: %s" % " ".join("%s(%s->%s)" % (n, na[n], nb[n]) for n in kind[:40]))
    print("  %d names, %d missing, %d kind-changed, %d new%s"
          % (len(na), len(miss), len(kind), len(new), (": " + " ".join(new[:40])) if new else ""))
    print("RESULT: %s" % ("EQUIVALENT" if not bad else "%d difference(s)" % bad))
    return 0 if not bad else 1


def main(argv):
    if len(argv) >= 2 and argv[0] == "take":
        pf = argv[argv.index("--params") + 1] if "--params" in argv else None
        take(argv[1], pf)
        return 0
    if len(argv) == 3 and argv[0] == "diff":
        return diff(argv[1], argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
