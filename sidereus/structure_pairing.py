"""Source <-> test pairing for the structure view: name/mirror/dir rules, the reference fallback, and the file list.
Split from sidereus/structure.py (2026-09-24); the endpoint `structure_pair()` and its result cache stay there."""
import os
import re
import time
from sidereus.memo import BoundedMemo
from sidereus.structure_scan import STRUCT_SKIP, _struct_lock, _struct_wanted, _struct_is_test


# ── source <-> test pairing ──────────────────────────────────────────────────────
# Pair a file with its tests (or a test with
#   the code under test). Test classification is `_struct_is_test()` as-is, so it works with `?tests=0` too.
# ⚠Same confinement as `/api/structure/src` (allow list · relative path · STRUCT_EXTS). Current tree only.
# ⚠Name rules first; content references are a fallback only (common stems like `config` match noisily).
STRUCT_PAIR_TTL_S = 20            # file list reuse — the panel asks once per click, not per poll
STRUCT_PAIR_MAX = 12              # matches returned
STRUCT_PAIR_SCAN = 1500           # files opened for the reference fallback
_struct_pair_ls = BoundedMemo(32)   # root -> (time, [rel])
_PAIR_TEST_DECOR = (
    (re.compile(r"^test_(.+)\.py$"), ".py"), (re.compile(r"^(.+)_test\.py$"), ".py"),
    (re.compile(r"^(.+)\.(?:test|spec)\.(ts|tsx|js|jsx)$"), None),
    (re.compile(r"^(.+?)(?:Tests?|IT)\.(java|kt)$"), None), (re.compile(r"^(.+)_test\.go$"), ".go"),
    (re.compile(r"^(.+?)_(?:unit)?test\.(c|cc|cpp|cxx)$"), None), (re.compile(r"^test_(.+)\.(c|cc|cpp|cxx)$"), None),
    (re.compile(r"^(.+?)Tests?\.cs$"), ".cs"),
)
_PAIR_JS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_PAIR_C = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".hxx")     # a C/C++ test pairs with its source or header
_PAIR_CS_PROJ = re.compile(r"^(.+)\.(?:Unit|Integration)?Tests?$")       # .NET test project dir `X.Tests` -> `X`


def _struct_pair_subject(base):
    """Test file name -> (stem of the code under test, its extension family) or ("", "")."""
    for rx, ext in _PAIR_TEST_DECOR:
        m = rx.match(base)
        if m:
            e = ext or ("." + m.group(2))
            return m.group(1), e
    return "", ""


def _struct_pair_fam(ext):
    return _PAIR_JS if ext in _PAIR_JS else _PAIR_C if ext in _PAIR_C else (ext,)


def _struct_pair_proj(rel):
    """`tests/X.Tests/a/b.cs` -> `src/X/a/b.cs` (test project -> source project; a `test(s)` parent -> `src`), or ""."""
    parts = rel.split("/")
    for k, p in enumerate(parts[:-1]):
        m = _PAIR_CS_PROJ.match(p)
        if m:
            parts[k] = m.group(1)
            if k and parts[k - 1].lower() in ("test", "tests"):
                parts[k - 1] = "src"
            return "/".join(parts)
    return ""


def _struct_pair_mirror(rel):
    """`src/main/...` <-> `src/test/...` (Maven/Gradle), .NET `tests/X.Tests/...` -> `src/X/...`; else ""."""
    if _struct_pair_proj(rel):
        return _struct_pair_proj(rel)
    for a, b in (("/main/", "/test/"), ("/test/", "/main/")):
        if a in "/" + rel:
            return ("/" + rel).replace(a, b, 1)[1:]
    return ""


STRUCT_PAIR_REF_MAX = 5          # ref pairs are weaker — show only the top few
_PAIR_JAVA_ROOTS = ("/java/", "/kotlin/")
_PAIR_PY_IMP = re.compile(r"(?m)^[ \t]*import[ \t]+([\w., \t]+)$")
_PAIR_PY_FROM = re.compile(r"(?m)^[ \t]*from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]+)")
_PAIR_PY_LOAD = re.compile(r"\b(\w+)\(\s*[\"']([\w.]+)[\"']\s*\)")
_PAIR_JS_SPEC = re.compile(r"(?:\bfrom|\bimport|\brequire\(|\bimport\()\s*[\"']([^\"'\n]+)[\"']")
_PAIR_JS_BIND = re.compile(r"\bimport\s+([\w$*{},\s]+?)\s+from\s*[\"']([^\"'\n]+)[\"']\s*;?"
                           r"|\b(?:const|let|var)\s+([\w$]+|\{[^}]*\})\s*=\s*require\(\s*[\"']([^\"'\n]+)[\"']\s*\)")
_PAIR_JV_PKG = re.compile(r"(?m)^\s*package\s+([\w.]+)")
_PAIR_JV_IMP = re.compile(r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)(\.\*)?\s*;?")
_PAIR_JV_NOISE = re.compile(r'"""[\s\S]*?"""|//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')


def _struct_pair_index(files):
    """Non-test files keyed the way code refers to them: python dotted module (suffixes of >=2 parts,
    bare name only at repo root) · java/kotlin FQCN (path after `/java/`|`/kotlin/`) · js/ts path without extension."""
    py, jv, js = {}, {}, {}
    for f in files:
        if _struct_is_test(f):
            continue
        stem, ext = os.path.splitext(f)
        if ext == ".py":
            parts = stem.split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for k in range(len(parts) - 1 if len(parts) > 1 else 0, -1, -1):
                if len(parts) - k >= 2 or len(parts) == 1:
                    py.setdefault(".".join(parts[k:]), f)
        elif ext in (".java", ".kt"):
            p = "/" + stem
            for r in _PAIR_JAVA_ROOTS:
                if r in p:
                    jv.setdefault(p.split(r, 1)[1].replace("/", "."), f)
                    break
        elif ext in _PAIR_JS:
            js.setdefault(stem, f)
            if stem.endswith("/index"):
                js.setdefault(stem[:-6], f)
    return {"py": py, "jv": jv, "js": js}


def _struct_pair_py_code(body):
    """(python source with strings/comments blanked, [(fn, "arg")] real `fn("arg")` calls).
    ⚠tokenize, not regex — a test that holds `'sidereus("usage")'` inside a string literal must not pair."""
    import io
    import tokenize
    lines = body.split("\n")
    loads = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(body).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return body, [(m.group(1), m.group(2)) for m in _PAIR_PY_LOAD.finditer(body)]
    for i, t in enumerate(toks):
        if (t.type == tokenize.STRING and 2 <= i < len(toks) - 1 and toks[i - 1].string == "("
                and toks[i - 2].type == tokenize.NAME and toks[i + 1].string == ")"):
            m = re.match(r"^[\"']([\w.]+)[\"']$", t.string)
            if m:
                loads.append((toks[i - 2].string, m.group(1)))
    for t in reversed(toks):                  # blank from the end so earlier offsets stay valid
        if t.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (r0, c0), (r1, c1) = t.start, t.end
        for r in range(r0, r1 + 1):
            ln = lines[r - 1]
            a = c0 if r == r0 else 0
            b = c1 if r == r1 else len(ln)
            lines[r - 1] = ln[:a] + " " * (b - a) + ln[b:]
    return "\n".join(lines), loads


def _struct_pair_targets(trel, body, idx, uses=None):
    """Source files a test really references -> [(rel, via)] strongest first.
    `uses` (dict, optional) receives rel -> how often the test's code uses the names that reference binds.
    ⚠Real references only (2026-09-23 follow-up: a quoted "usage" in unrelated code paired wrongly;
    repo-J 725/1,146 main classes paired by loose `\\bName\\b`). Comments/strings never count."""
    out, seen = [], set()
    binds, extra = {}, {}       # rel -> names bound by the reference · rel -> offset (binding lines, bare calls)
    use_code = [""]             # code the names are counted in (import statements blanked)

    def put(f, via, *bound):
        if f and f != trel:
            binds.setdefault(f, set()).update(n for n in bound if n)
        if f and f not in seen and f != trel:
            seen.add(f)
            out.append((f, via))
    ext = os.path.splitext(trel)[1]
    tdir = os.path.dirname(trel)
    if ext == ".py":
        py = idx["py"]
        raw = body
        body, loads = _struct_pair_py_code(body)
        use_code[0] = _PAIR_PY_FROM.sub(" ", _PAIR_PY_IMP.sub(" ", body))
        for m in _PAIR_PY_IMP.finditer(body):
            for part in m.group(1).split(","):
                put(py.get(part.split(" as ")[0].strip()), "import", part.split(" as ")[-1].strip())
        for m in _PAIR_PY_FROM.finditer(body):
            mod = m.group(1)
            if mod.startswith("."):          # relative import — resolve against the test's package
                ups = len(mod) - len(mod.lstrip("."))
                base = tdir.split("/") if tdir else []
                base = base[:len(base) - (ups - 1)] if ups > 1 else base
                mod = ".".join([x for x in base if x] + ([mod.lstrip(".")] if mod.lstrip(".") else []))
            parts = [(n.split(" as ")[0].strip(), n.split(" as ")[-1].strip())
                     for n in m.group(2).strip("() \t\n").split(",")]
            parts = [(n, a) for n, a in parts if n and n != "*"]
            for n, a in parts:
                put(py.get(mod + "." + n if mod else n), "import", a)
            put(py.get(mod), "import", *[a for _n, a in parts])
        for fn, arg in sorted(set(loads)):        # `sidereus("usage")` · `import_module("sidereus.usage")`
            f = py.get(arg) if fn in ("import_module", "__import__") else py.get(fn + "." + arg)
            call = r"\b%s\(\s*[\"']%s[\"']\s*\)" % (re.escape(fn), re.escape(arg))
            bm = re.search(r"(?m)^[ \t]*(\w+)[ \t]*=[ \t]*[\w.]*" + call, raw)
            put(f, "loader", bm.group(1) if bm else "")
            if f and f != trel:   # `S = sidereus("x")`: its own line is not a use of S; every other bare call is one use
                n = loads.count((fn, arg))
                extra[f] = extra.get(f, 0) + (n - 2 if bm else n)
    elif ext in (".java", ".kt"):
        jv = idx["jv"]
        pm = _PAIR_JV_PKG.search(body)
        pkg = pm.group(1) if pm else ""
        code = _PAIR_JV_NOISE.sub(" ", body)
        body_code = re.sub(r"(?m)^\s*(?:package|import)\s[^\n]*", " ", code)
        toks = set(re.findall(r"\b[A-Z][\w$]*\b", body_code))
        use_code[0] = body_code
        wild = []
        for m in _PAIR_JV_IMP.finditer(code):
            if m.group(2):
                wild.append(m.group(1))
            elif m.group(1).rsplit(".", 1)[-1] in toks:     # an unused import is not a reference
                put(jv.get(m.group(1)), "import", m.group(1).rsplit(".", 1)[-1])
        for t in sorted(toks):
            for p in ([pkg] if pkg else []) + wild:
                put(jv.get(p + "." + t), "package" if p == pkg else "import", t)
    elif ext in _PAIR_JS:
        js = idx["js"]
        # ⚠`(?<![:\w])` keeps `'http://x'` intact while dropping `// from './a'` comments.
        jcode = re.sub(r"(?<![:\w])//[^\n]*|/\*[\s\S]*?\*/", " ", body)
        jbind = {}                               # spec -> local names its import/require binds
        for m in _PAIR_JS_BIND.finditer(jcode):
            clause, spec = (m.group(1), m.group(2)) if m.group(2) else (m.group(3), m.group(4))
            clause = re.sub(r"\b[\w$]+\s+as\s+", "", clause.replace("* as", " "))
            jbind.setdefault(spec, set()).update(n for n in re.findall(r"[\w$]+", clause) if n != "type")
        use_code[0] = _PAIR_JS_BIND.sub(" ", jcode)
        for m in _PAIR_JS_SPEC.finditer(jcode):
            spec = m.group(1)
            nb = jbind.get(spec, ())
            if spec.startswith("."):
                key = os.path.normpath(os.path.join(tdir, spec)).replace(os.sep, "/")
                key = os.path.splitext(key)[0] if key.endswith(_PAIR_JS) else key
                put(js.get(key), "import", *nb)
            elif spec.startswith(("@/", "~/")):      # common `@/` -> `src/` alias
                tail = "src/" + spec[2:]
                for k, f in js.items():
                    if k == tail or k.endswith("/" + tail):
                        put(f, "import", *nb)
                        break
    order = {"import": 0, "package": 1, "loader": 2}
    out.sort(key=lambda r: order.get(r[1], 9))
    if uses is not None:
        for f, _via in out:
            n = sum(len(re.findall(r"(?<![\w$.])%s(?![\w$])" % re.escape(b), use_code[0])) for b in binds.get(f, ()))
            uses[f] = max(0, n + extra.get(f, 0))
    return out


def _struct_pair_match(rel, files, read=None):
    """Pure matcher. rel + all relative paths (+ reader for the reference fallback) ->
    (is rel a test, [{file, reason}] strongest first). reason: mirror · name · dir · ref."""
    is_test = _struct_is_test(rel)
    d, base = os.path.split(rel)
    stem, ext = os.path.splitext(base)
    out, seen = [], {rel}

    def add(f, why):
        if f not in seen:
            seen.add(f)
            out.append({"file": f, "reason": why})
    if is_test:
        want, wext = _struct_pair_subject(base)
        want = want or stem
        wext = wext or ext
        fam = _struct_pair_fam(wext)
        cands = [f for f in files if not _struct_is_test(f)
                 and os.path.splitext(os.path.basename(f))[0] == want and f.endswith(fam)
                 and (wext != ".go" or os.path.dirname(f) == d)]   # ⚠Go tests live in their package's dir
        mir = _struct_pair_mirror(os.path.join(d, want + wext))
        pdir = os.path.dirname(d)            # tests/x_test.py -> sibling of tests/, __tests__/x.test.ts -> parent
        for f in sorted(cands, key=lambda f: (f != mir, os.path.dirname(f) not in (d, pdir), len(f), f)):
            add(f, "mirror" if f == mir else ("dir" if os.path.dirname(f) in (d, pdir) else "name"))
        if not out and read:
            uses = {}
            refs = _struct_pair_targets(rel, read(rel) or "", _struct_pair_index(files), uses)
            refs.sort(key=lambda r: -uses.get(r[0], 0))      # most-used first; stable, so ties keep via order
            for f, via in refs[:STRUCT_PAIR_REF_MAX]:
                add(f, "ref")
                out[-1].update(via=via, uses=uses.get(f, 0))
    else:
        fam = _struct_pair_fam(ext)
        mir = _struct_pair_mirror(rel)
        mird = os.path.dirname(mir) if mir else None
        tests = [f for f in files if _struct_is_test(f)]
        for f in tests:
            s2, e2 = _struct_pair_subject(os.path.basename(f))
            ok = bool(s2) and s2 == stem and e2 in fam
            if not ok:     # `__tests__/x.ts` — the directory alone marks it as the test of `x.ts`
                ok = (os.path.splitext(os.path.basename(f))[0] == stem and f.endswith(fam)
                      and ("__tests__" in f.split("/") or bool(_struct_pair_proj(f))))
            if not ok:
                continue
            fd = os.path.dirname(f)
            if ext == ".go" and fd != d:   # ⚠`b/x_test.go` cannot test `a/x.go` (one package = one dir)
                continue
            pj = _struct_pair_proj(f)
            if mird is not None and fd == mird or pj and os.path.dirname(pj) == d:
                why = "mirror"
            elif fd == d or os.path.dirname(fd) == d or fd == os.path.join(d, "__tests__"):
                why = "dir"
            else:
                why = "name"
            add(f, why)
        out.sort(key=lambda r: (("mirror", "dir", "name").index(r["reason"]), len(r["file"]), r["file"]))
        if not out and read:
            idx = None
            hits = []
            probe = os.path.basename(d) if stem == "index" and d else stem   # `./api` imports `api/index.ts`
            for f in tests[:STRUCT_PAIR_SCAN]:
                b = read(f) or ""
                if probe not in b:                # cheap prefilter before parsing imports
                    continue
                idx = idx or _struct_pair_index(files)
                uses = {}
                for g, via in _struct_pair_targets(f, b, idx, uses):
                    if g == rel:
                        hits.append((-uses.get(g, 0), ("import", "package", "loader").index(via), len(f), f, via))
            # ★2026-09-24: a config test importing it once outranked the controller's own test — rank by use count.
            for n, _o, _n, f, via in sorted(hits)[:STRUCT_PAIR_REF_MAX]:
                add(f, "ref")
                out[-1].update(via=via, uses=-n)
    return is_test, out[:STRUCT_PAIR_MAX]


def _struct_pair_files(root):
    """Relative paths the structure scan would look at (tests included), reused for STRUCT_PAIR_TTL_S."""
    now = time.time()
    with _struct_lock:
        hit = _struct_pair_ls.get(root)
    if hit and now - hit[0] < STRUCT_PAIR_TTL_S:
        return hit[1]
    got = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [x for x in dns if x not in STRUCT_SKIP and not x.startswith(".")]
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
            if _struct_wanted(rel):
                got.append(rel)
    got.sort()
    with _struct_lock:
        _struct_pair_ls.put(root, (now, got))
    return got
