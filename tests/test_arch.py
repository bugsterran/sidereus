"""Architecture rules from AGENTS.md and refactor/STAGE3.md as machine checks.

Reads repo source files only (never live data). Violations that already exist are
frozen in tests/arch_baseline.json: the test passes on today's tree and fails on a NEW
violation. ⚠Shrink the baseline when you fix one; never grow it to make a red test pass
without the owner's say-so. `python3 tests/test_arch.py --dump` prints the current
findings in baseline shape (to diff against the file, not to overwrite it blindly).
"""
import ast
import glob
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE = os.path.join(ROOT, "tests", "arch_baseline.json")

PY_FILE_CAP = 620
JS_FILE_CAP = 700
PY_FUNC_CAP = 130
# Outside STAGE3's import order: loaded lazily by main() under --demo only.
LAZY_ONLY = {"demo", "demo_data", "demo_git", "demo_rel", "demo_tools"}
# The only places allowed to build a ["git", ...] argv.
GIT_ARGV_OWNERS = {("sidereus/gitinfo.py", "git_argv"), ("sidereus/gitinfo.py", "_git_run"),
                   ("sidereus/gitinfo.py", "_git_run_capped"), ("sidereus/gitinfo.py", "_git_version"),
                   # plugin ships hooks/ only, so the hook cannot import gitinfo; its opts are pinned equal to GIT_SAFE_OPTS in test_ev_hook
                   ("hooks/ev_hook.py", "git_status"), ("hooks/pl_flow.py", "_head")}
# Work-popup files: the one place message bodies may be rendered (AGENTS.md rule 1 exception).
WORK_POPUP_RE = re.compile(r"^35[a-z]?-worklog")
BODY_KEYS = ("reply", "task", "prompt", "says", "arg")


def _rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")   # baseline keys use '/' on every OS


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _sidereus_files():
    return sorted(p for p in glob.glob(os.path.join(ROOT, "sidereus", "*.py"))
                  if os.path.basename(p) not in ("__init__.py", "__main__.py"))


def _server_py():
    """Server-side python outside tests: sidereus/, chat_server.py, mcp/, hooks/."""
    out = _sidereus_files() + [os.path.join(ROOT, "chat_server.py")]
    for d in ("mcp", "hooks"):
        out += sorted(glob.glob(os.path.join(ROOT, d, "*.py")))
    return out


def _js_files():
    return sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js")))


_AST = {}


def _tree(p):
    if p not in _AST:
        _AST[p] = ast.parse(_read(p), filename=p)
    return _AST[p]


# ── 1. layering ──────────────────────────────────────────────────────────────

def stage3_order():
    txt = _read(os.path.join(ROOT, "refactor", "STAGE3.md"))
    m = re.search(r"^## Modules \(import order[^\n]*\n(.*?)\n\s*\n", txt, re.S | re.M)
    lines = [ln for ln in m.group(1).splitlines() if not ln.lstrip().startswith("-")]
    return [w.strip() for w in " ".join(lines).split("·") if w.strip()]


def _sidereus_targets(node):
    """sidereus module names an import node pulls in."""
    out = []
    if isinstance(node, ast.Import):
        for a in node.names:
            if a.name.startswith("sidereus."):
                out.append(a.name.split(".")[1])
    elif isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if node.level == 1 or mod == "sidereus":
            if mod and node.level == 1:
                out.append(mod.split(".")[0])
            else:
                out += [a.name for a in node.names]
        elif mod.startswith("sidereus."):
            out.append(mod.split(".")[1])
    return out


def _imports(p):
    """(top-level sidereus imports, lazy [(func, mod)] imports) of one file."""
    top, lazy = set(), []

    def walk(node, fn):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.Import, ast.ImportFrom)):
                for t in _sidereus_targets(ch):
                    (lazy.append((fn, t)) if fn else top.add(t))
            elif isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                walk(ch, getattr(ch, "name", "<lambda>") if fn is None else fn)
            else:
                walk(ch, fn)
    walk(_tree(p), None)
    return top, lazy


def layering():
    order = stage3_order()
    idx = {m: i for i, m in enumerate(order)}
    viol, lazy_up = [], []
    for p in _sidereus_files():
        me = os.path.basename(p)[:-3]
        top, lazy = _imports(p)
        for t in sorted(top):
            if me in LAZY_ONLY:
                if t in LAZY_ONLY or t in idx:
                    continue
            elif t in LAZY_ONLY or t not in idx or me not in idx or idx[t] >= idx[me]:
                viol.append("%s -> %s" % (me, t))
        for fn, t in lazy:
            if me in idx and t in idx and idx[t] >= idx[me]:
                lazy_up.append("%s.%s -> %s" % (me, fn, t))
    return viol, sorted(set(lazy_up))


# ── 2. global ownership ──────────────────────────────────────────────────────

def _mod_aliases(tree):
    """Local names that are bound to modules by import statements (anywhere in the file)."""
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            src = n.module or ""
            if n.level == 1 or src == "sidereus":
                for a in n.names:
                    names.add(a.asname or a.name)
    return names


def _is_mod_ref(node, aliases):
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id in aliases


def ownership():
    out = []
    for p in _server_py():
        tree = _tree(p)
        aliases = _mod_aliases(tree)
        for n in ast.walk(tree):
            tgts = []
            if isinstance(n, ast.Assign):
                tgts = n.targets
            elif isinstance(n, (ast.AugAssign, ast.AnnAssign)):
                tgts = [n.target]
            for t in tgts:
                for e in (t.elts if isinstance(t, (ast.Tuple, ast.List)) else [t]):
                    if isinstance(e, ast.Attribute) and _is_mod_ref(e.value, aliases):
                        out.append("%s:%s.%s" % (_rel(p), _dotted(e.value), e.attr))
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("setattr", "delattr")
                    and n.args and _is_mod_ref(n.args[0], aliases)):
                out.append("%s:%s(%s)" % (_rel(p), n.func.id, _dotted(n.args[0])))
    return sorted(out)


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


# ── 3. size caps ─────────────────────────────────────────────────────────────

def _nlines(p):
    return _read(p).count("\n")


def long_functions():
    out = {}
    for p in _server_py():
        def walk(node, prefix):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    q = prefix + ch.name
                    if not isinstance(ch, ast.ClassDef):
                        n = ch.end_lineno - ch.lineno + 1
                        if n > PY_FUNC_CAP:
                            out["%s:%s" % (_rel(p), q)] = n
                    walk(ch, q + ".")
                else:
                    walk(ch, prefix)
        walk(_tree(p), "")
    return out


# ── 4. safety ────────────────────────────────────────────────────────────────

def safety():
    out = []
    for p in _server_py():
        rp = _rel(p)
        tree = _tree(p)

        def walk(node, fn):
            for ch in ast.iter_child_nodes(node):
                f = ch.name if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
                if isinstance(ch, ast.Call):
                    for k in ch.keywords:
                        if k.arg == "shell" and not (isinstance(k.value, ast.Constant) and k.value.value is False):
                            out.append("%s:%d shell=" % (rp, ch.lineno))
                    if isinstance(ch.func, ast.Name) and ch.func.id in ("eval", "exec"):
                        out.append("%s:%d %s(" % (rp, ch.lineno, ch.func.id))
                    if isinstance(ch.func, ast.Attribute) and ch.func.attr == "load" and _dotted(ch.func.value) == "yaml":
                        out.append("%s:%d yaml.load" % (rp, ch.lineno))
                if isinstance(ch, ast.List) and ch.elts:
                    e0 = ch.elts[0]
                    if isinstance(e0, ast.Constant) and e0.value == "git" and (rp, f) not in GIT_ARGV_OWNERS:
                        out.append("%s:%d git argv literal in %s" % (rp, ch.lineno, f))
                if isinstance(ch, (ast.Import, ast.ImportFrom)):
                    mods = [a.name for a in ch.names] + ([ch.module] if isinstance(ch, ast.ImportFrom) and ch.module else [])
                    if any(m.split(".")[0] in ("pickle", "cPickle", "marshal", "shelve") for m in mods):
                        out.append("%s:%d pickle import" % (rp, ch.lineno))
                walk(ch, f)
        walk(tree, None)
    return out


# ── 5. silent errors ─────────────────────────────────────────────────────────

_JS_EMPTY_CATCH = re.compile(r"\bcatch\s*(?:\(\s*[\w$]*\s*\))?\s*\{\s*\}")


def silent_py():
    out = {}
    for p in _sidereus_files():
        n = sum(1 for h in ast.walk(_tree(p)) if isinstance(h, ast.ExceptHandler)
                and len(h.body) == 1 and isinstance(h.body[0], ast.Pass))
        if n:
            out[_rel(p)] = n
    return out


def silent_js():
    out = {}
    for p in _js_files():
        n = len(_JS_EMPTY_CATCH.findall(_js_strip(_read(p), keep_strings=False)))
        if n:
            out[_rel(p)] = n
    return out


# ── 6. JS top-level names ────────────────────────────────────────────────────

def _js_strip(src, keep_strings=True):
    """Blank out comments (and string/template/regex bodies unless keep_strings) keeping offsets."""
    out = list(src)
    i, n = 0, len(src)
    prev = ""  # last significant char, for regex-vs-divide

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in "'\"`":
            j = i + 1
            depth = 0
            while j < n:
                d = src[j]
                if d == "\\":
                    j += 2
                    continue
                if c == "`" and d == "$" and j + 1 < n and src[j + 1] == "{":
                    depth += 1
                    j += 2
                    continue
                if c == "`" and d == "}" and depth:
                    depth -= 1
                elif d == c and not depth:
                    break
                j += 1
            blank(i + 1, j)
            i = j + 1
            prev = c
            continue
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^" or _ends_kw(src, i)):
            j, cls = i + 1, False
            while j < n and src[j] != "\n":
                d = src[j]
                if d == "\\":
                    j += 2
                    continue
                if d == "[":
                    cls = True
                elif d == "]":
                    cls = False
                elif d == "/" and not cls:
                    break
                j += 1
            blank(i + 1, j)
            i = j + 1
            prev = "a"
            continue
        if not c.isspace():
            prev = c
        i += 1
    s = "".join(out)
    return s


def _ends_kw(src, i):
    m = re.search(r"(?:return|typeof|case|in|of|void|delete|throw|else)\s*$", src[max(0, i - 12):i])
    return bool(m)


_IDENT = r"[A-Za-z_$][\w$]*"


def js_top_names(src):
    """{name: line} for top-level function/class/const/let/var declarations."""
    s = _js_strip(src)
    names = {}
    depth, i, n = 0, 0, len(s)
    decl = False
    last = ""
    tok = re.compile(r"(?:async\s+)?function\s*\*?\s*(" + _IDENT + r")|class\s+(" + _IDENT + r")|(?:const|let|var)\s+")

    def add(name, pos):
        names.setdefault(name, s.count("\n", 0, pos) + 1)
    while i < n:
        c = s[i]
        if c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
        elif depth == 0:
            if decl and c == ";":
                decl = False
            elif decl and c == "\n" and last != ",":
                decl = False
            elif decl and c == ",":
                m = re.match(r",\s*(" + _IDENT + ")", s[i:])
                if m:
                    add(m.group(1), i + m.start(1))
            elif (c.isalpha() or c in "_$") and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] in "_$.")):
                m = tok.match(s, i)
                if m:
                    if m.group(1) or m.group(2):
                        add(m.group(1) or m.group(2), i)
                        i = m.end()
                        continue
                    j = m.end()
                    if j < n and s[j] in "{[":
                        k, dd = j, 0
                        while k < n:
                            if s[k] in "{[":
                                dd += 1
                            elif s[k] in "}]":
                                dd -= 1
                                if not dd:
                                    break
                            k += 1
                        for nm in re.findall(r"(?:^|[{\[,])\s*(?:" + _IDENT + r"\s*:\s*)?(" + _IDENT + ")", s[j:k + 1]):
                            add(nm, j)
                        i = k + 1
                    else:
                        mm = re.match(_IDENT, s[j:])
                        if mm:
                            add(mm.group(0), j)
                        i = j + (mm.end() if mm else 0)
                    decl = True
                    last = ""
                    continue
        if not c.isspace():
            last = c
        i += 1
    return names


def js_collisions():
    seen, out = {}, []
    files = [os.path.join(ROOT, "web", "app-head.js")] + _js_files()
    for p in files:
        if not os.path.exists(p):
            continue
        for name, line in sorted(js_top_names(_read(p)).items()):
            if name in seen:
                out.append("%s (%s, %s:%d)" % (name, seen[name], _rel(p), line))
            else:
                seen[name] = "%s:%d" % (_rel(p), line)
    return sorted(out)


# ── 7. metadata-only ─────────────────────────────────────────────────────────

_BODY_RE = re.compile(r"(?:\.(%s)\b(?!\s*[:(])|\[\s*['\"](%s)['\"]\s*\])" % ("|".join(BODY_KEYS), "|".join(BODY_KEYS)))


def body_keys():
    out = {}
    for p in _js_files():
        if WORK_POPUP_RE.match(os.path.basename(p)):
            continue
        s = _js_strip(_read(p))
        for m in _BODY_RE.finditer(s):
            k = "%s:.%s" % (_rel(p), m.group(1) or m.group(2))
            out.setdefault(k, []).append(s.count("\n", 0, m.start()) + 1)
    return {k: len(v) for k, v in out.items()}, out


# ── 8. feature manifests (docs/dev/FEATURES.md) ──────────────────────────────

# Wiring points: they import a feature's route bodies / thread targets, which the manifest gates at run time.
FEATURE_WIRING = {"chat_server", "routes_get", "routes_post"}


def manifests():
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "features", "*.json"))):
        m = json.loads(_read(p))
        out[m["id"]] = m
    return out


def _dep_closure(man, fid):
    seen, todo = set(), list(man.get(fid, {}).get("deps", []))
    while todo:
        d = todo.pop()
        if d not in seen:
            seen.add(d)
            todo += man.get(d, {}).get("deps", [])
    return seen


def feature_couplings():
    """"importer -> module" where the module belongs to a feature the importer's feature does not depend on."""
    man = manifests()
    owner = {mod: fid for fid, m in man.items() for mod in m.get("modules", [])}
    out = set()
    for p in _sidereus_files():
        me = os.path.basename(p)[:-3]
        if me in FEATURE_WIRING:
            continue
        top, lazy = _imports(p)
        mine = owner.get(me)
        for t in top | {t for _, t in lazy}:
            fb = owner.get(t)
            if fb and fb != mine and not (mine and fb in _dep_closure(man, mine)):
                out.add("%s -> %s" % (me, t))
    return sorted(out)


# ── collection + test ────────────────────────────────────────────────────────

def collect():
    viol, lazy = layering()
    return {
        "layering": viol,
        "lazy_upward_imports": lazy,
        "ownership": ownership(),
        "py_file_lines": {_rel(p): _nlines(p) for p in _sidereus_files() if _nlines(p) > PY_FILE_CAP},
        "js_file_lines": {_rel(p): _nlines(p) for p in _js_files() if _nlines(p) > JS_FILE_CAP},
        "py_func_lines": long_functions(),
        "safety": [re.sub(r":\d+ ", " ", v) for v in safety()],
        "silent_py": silent_py(),
        "silent_js": silent_js(),
        "js_collisions": [re.sub(r":\d+", "", v) for v in js_collisions()],
        "body_keys": body_keys()[0],
        "feature_couplings": feature_couplings(),
    }


def _baseline():
    try:
        with open(BASELINE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


class Arch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = _baseline()

    def _list_rule(self, key, found, why):
        new = sorted(set(found) - set(self.base.get(key, [])))
        self.assertEqual(new, [], "%s (new, not in tests/arch_baseline.json[%r])" % (why, key))

    def _count_rule(self, key, found, cap, why):
        base = self.base.get(key, {})
        over = {k: (v, max(cap, base.get(k, cap))) for k, v in found.items() if v > max(cap, base.get(k, cap))}
        self.assertEqual(over, {}, "%s — {item: (now, allowed)}" % why)

    def test_layering(self):
        viol, lazy = layering()
        self._list_rule("layering", viol, "top-level import of a module not earlier in STAGE3's order")
        self._list_rule("lazy_upward_imports", lazy,
                        "in-function import of a later module — register it in the baseline if intended")

    def test_modules_registered_and_counted(self):
        order = stage3_order()
        self.assertEqual(len(order), len(set(order)), "duplicate module in STAGE3 order")
        real = {os.path.basename(p)[:-3] for p in _sidereus_files()}
        self.assertEqual(sorted(real - set(order) - LAZY_ONLY), [], "sidereus module missing from refactor/STAGE3.md order")
        self.assertEqual(sorted(set(order) - real), [], "STAGE3 order names a module that does not exist")
        st = re.search(r"(\d+) modules total", _read(os.path.join(ROOT, "refactor", "STAGE3.md")))
        ag = re.search(r"\((\d+) modules", _read(os.path.join(ROOT, "AGENTS.md")))
        self.assertEqual(int(st.group(1)), len(real), "STAGE3.md 'N modules total' is stale")
        self.assertEqual(int(ag.group(1)), len(real), "AGENTS.md '(N modules' count is stale")

    def test_chat_server_imports_in_order(self):
        order = stage3_order()
        idx = {m: i for i, m in enumerate(order)}
        seq = []
        for node in _tree(os.path.join(ROOT, "chat_server.py")).body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                seq += [t for t in _sidereus_targets(node) if t in idx]
        late, hi = [], -1
        for t in seq:
            if idx[t] < hi:
                late.append(t)
            hi = max(hi, idx[t])
        self._list_rule("chat_server_order", late, "chat_server.py imports these sidereus modules after a later one")

    def test_global_ownership(self):
        self._list_rule("ownership", ownership(), "assignment to another module's global — fix it in the owner module")

    def test_size_caps(self):
        self._count_rule("py_file_lines", {_rel(p): _nlines(p) for p in _sidereus_files()}, PY_FILE_CAP,
                         "sidereus/*.py over %d lines — split it" % PY_FILE_CAP)
        self._count_rule("js_file_lines", {_rel(p): _nlines(p) for p in _js_files()}, JS_FILE_CAP,
                         "web/js/*.js over %d lines — split it at a top-level statement" % JS_FILE_CAP)
        self._count_rule("py_func_lines", long_functions(), PY_FUNC_CAP,
                         "python function over %d lines" % PY_FUNC_CAP)

    def test_safety(self):
        found = [re.sub(r":\d+ ", " ", v) for v in safety()]
        self._list_rule("safety", found, "shell=True / eval / exec / pickle / yaml.load / git argv outside gitinfo.git_argv")

    def test_silent_errors(self):
        self._count_rule("silent_py", silent_py(), 0, "`except ...: pass` count rose — use warn_once")
        self._count_rule("silent_js", silent_js(), 0, "empty catch{} count rose — use softErr(tag, e)")

    def test_js_global_collisions(self):
        self._list_rule("js_collisions", [re.sub(r":\d+", "", v) for v in js_collisions()],
                        "top-level name defined in two web files (they share one global scope)")

    def test_no_bare_localstorage(self):
        # UI prefs live in UIS (web/app-head.js, server-backed); only rvnotes drafts and notification keys stay in localStorage.
        ok = {"88e-rvnotes.js", "43-notify.js", "35e-worklog-plrun.js"}   # cross-window jump needs the storage event; UIS never fires it
        bad = ["%s:%d" % (_rel(p), _js_strip(_read(p)).count("\n", 0, m.start()) + 1)
               for p in _js_files() if os.path.basename(p) not in ok
               for m in re.finditer(r"\blocalStorage\b", _js_strip(_read(p)))]
        self.assertEqual(bad, [], "use UIS (or lsGet/lsSet) instead of localStorage")

    def test_metadata_only(self):
        counts, _ = body_keys()
        self._count_rule("body_keys", counts, 0,
                         "web/js renders a message-body key outside the 35*-worklog* popups (AGENTS.md rule 1)")

    def test_feature_manifests(self):
        man, order = manifests(), set(stage3_order()) | LAZY_ONLY
        routes_src = _read(os.path.join(ROOT, "sidereus", "routes_get.py")) + _read(os.path.join(ROOT, "sidereus", "routes_post.py"))
        claims = {}
        for fid, m in man.items():
            self.assertEqual(sorted(set(m["modules"]) - order), [], "%s: manifest module not in STAGE3" % fid)
            for w in m["web"]:
                self.assertTrue(os.path.isfile(os.path.join(ROOT, "web", w)), "%s: web file %s missing" % (fid, w))
                claims.setdefault("web:" + w, []).append(fid)
            for r in m["routes"]:
                if not r.endswith("*"):
                    self.assertIn('"%s"' % r, routes_src, "%s: route %s not in a route table" % (fid, r))
                claims.setdefault("route:" + r, []).append(fid)
            for t in m["threads"]:
                claims.setdefault("thread:" + t, []).append(fid)
        self.assertEqual({k: v for k, v in claims.items() if len(v) > 1}, {}, "claimed by more than one manifest")
        # ⚠Prefix claims overlap too: `/api/x*` in one manifest and `/api/x/y` in another is a double claim.
        rs = [(r, fid) for fid, m in man.items() for r in m["routes"]]
        clash = sorted("%s(%s) ~ %s(%s)" % (a, fa, b, fb) for a, fa in rs for b, fb in rs
                       if fa != fb and a.endswith("*") and b.rstrip("*").startswith(a[:-1]))
        self.assertEqual(clash, [], "route prefix claimed by more than one manifest")

    def test_feature_couplings(self):
        self._list_rule("feature_couplings", feature_couplings(),
                        "import of another feature's module without a declared dep (features/<id>.json deps)")

    def test_parsers_see_something(self):
        # Guards against a checker silently matching nothing (a regex/parse change would make every rule pass).
        self.assertGreater(len(stage3_order()), 40)
        self.assertIn("setHtml", js_top_names(_read(os.path.join(ROOT, "web", "js", "08-ui-kit.js"))))
        self.assertEqual(js_top_names("var a = 1,\n  b = 2;\nfunction f(){ let c = 1; }\nconst {d, e: g} = h;"),
                         {"a": 1, "b": 2, "f": 3, "d": 4, "g": 4})


if __name__ == "__main__":
    if "--dump" in sys.argv:
        d = collect()
        d["_body_key_lines"] = body_keys()[1]
        print(json.dumps(d, indent=1, ensure_ascii=False, sort_keys=True))
    else:
        unittest.main()
