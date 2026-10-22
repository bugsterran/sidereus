"""Architecture map (step 1): store layout, map.json v1/v2 schema and the evidence verifier.

An agent draws `map.json` (modules + edges, each edge citing file/line/symbol); this module re-reads every cited
file **at the stored commit** (`git show <commit>:<file>`, never the working tree) and keeps only the edges whose
evidence is really there. Output: `verify.json` (per-edge verdict) + `map.md` (mermaid of passed edges only).
Store: DATA_DIR/arch/<sha1(realpath repo)[:16]>/<commit>/ + DATA_DIR/arch/_last.json — never the target repo.
CLI wrapper: scripts/arch_verify.py. Stdlib only.
"""
import ast
import fnmatch
import functools
import hashlib
import json
import os
import re
import subprocess
import warnings

from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.gitinfo import _git_run, _git_run_capped
# Re-exported: callers import the schema names from arch_verify.
from sidereus.arch_schema import (COMMIT_RE, EDGE_MAX, ENTRY_EXTS, EV_MAX, EXTS, GROUP_MAX, ID_RE, KINDS,  # noqa: F401
                                  KINDS_V2, LAYERS, MOD_KINDS, MOD_KINDS_V2, MOD_MAX, NAME_MAX, OWNS_MAX, PATH_MAX,
                                  ROLE_LAYER, ROLES, STORE_EXTS, SUM_MAX, SYM_MAX, _groups_errors, _int, _line,
                                  _mod_v2_errors, schema_errors)

# ⚠Same SyntaxWarning filter as structure_lang: ast.parse of user code must not print to viewer.err.
_USER_SRC = "<user-src>"
warnings.filterwarnings("ignore", category=SyntaxWarning, module=re.escape(_USER_SRC) + "$")

ARCH_DIR = os.path.join(DATA_DIR, "arch")
ARCH_K = 2                 # symbol may sit within line ±K (agents miscount by a line or two)
ARCH_GATE_MIN = 0.7        # verified-edge rate below this fails the gate
ARCH_FILE_MAX = 1_000_000  # chars read per cited file; lines past the cap count as out of range
ARCH_TREE_MAX = 8_000_000  # chars of `ls-tree -r --name-only -z` kept
ARCH_GIT_TIMEOUT = 10
EST_KINDS = ("config", "di", "event")   # config/DI/event (v2) wiring cannot be proven by one symbol: always estimated
STYLES = ("layered", "modular", "apps", "routes", "feature-pkgs", "feature-folders", "crates", "mvvm", "hexagonal",
          "library", "other")
FW_MAX, UNITS_MAX = 80, 120  # framework holds a BE and an FE stack joined by " + "; 40 cut the FE part
# Allowed role -> role edges per style; every style also allows same-role and x -> shared. Styles without a table judge none.
STYLE_FLOW = {
    "layered": frozenset([("web", "service"), ("web", "domain"), ("service", "data"), ("service", "domain"),
                          ("data", "domain")]),
    "hexagonal": frozenset([("adapter", "port"), ("adapter", "domain"), ("adapter", "app"), ("app", "port"),
                            ("app", "domain"), ("port", "domain")]),   # adapter -> app: a driving adapter calls a use case
    "mvvm": frozenset([("view", "viewmodel"), ("viewmodel", "model"), ("view", "model")]),   # view binds to model types
}


def repo_key(repo):
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- persisted path key, not security
    return hashlib.sha1(os.path.realpath(repo).encode("utf-8", "surrogateescape"), usedforsecurity=False).hexdigest()[:16]


def store_dir(repo, commit):
    """Store dir for (repo, commit); ValueError for a commit that is not a full hex id."""
    if not (isinstance(commit, str) and COMMIT_RE.fullmatch(commit)):
        raise ValueError("commit must be a full hex id")
    return os.path.join(ARCH_DIR, repo_key(repo), commit)


def read_json(fp):
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def _write(fp, text):
    _atomic_write(fp, text.encode("utf-8"), prefix=".arch-", mode=0o644)   # unique tmp: concurrent runs never share one


def safe_rel(p):
    """Repo-relative path or "" — absolute, `..`, backslash and control characters are refused."""
    if not isinstance(p, str) or not p or p.startswith("/") or os.path.isabs(p) or "\\" in p \
            or any(ord(c) < 32 for c in p):
        return ""
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if not parts or ".." in parts:
        return ""
    return "/".join(parts)


def _tree(repo, commit):
    """Set of file paths in the commit's tree (a missing file must read as `nofile`, not as an empty file)."""
    text, _n = _git_run_capped(repo, ["ls-tree", "-r", "--name-only", "-z", commit], ARCH_GIT_TIMEOUT, ARCH_TREE_MAX)
    return set(x for x in text.split("\0") if x)


def _show(repo, commit, rel):
    text, _n = _git_run_capped(repo, ["show", commit + ":" + rel], ARCH_GIT_TIMEOUT, ARCH_FILE_MAX)
    lines = text[:ARCH_FILE_MAX].split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _word(sym):
    # Boundaries only on word-character ends: a URL symbol such as `/api/hook` sits right after `%d` in
    # `"http://127.0.0.1:%d/api/hook"`, and a lookbehind there turned a true edge into `nosym`.
    pre = r"(?<![A-Za-z0-9_])" if sym[:1].isalnum() or sym[:1] == "_" else ""
    post = r"(?![A-Za-z0-9_])" if sym[-1:].isalnum() or sym[-1:] == "_" else ""
    return re.compile(pre + re.escape(sym) + post)


def check_evidence(ev, kind, tree, read):
    """"" if this evidence holds, else nofile|range|nosym|bad (owner/overlap/nodef are checked in verify_map).
    `read(rel)` -> lines of the file at the commit."""
    rel = safe_rel(ev.get("file"))
    if not rel:
        return "bad"
    if rel not in tree:
        return "nofile"
    lines = read(rel)
    ln = ev.get("line")
    if not _int(ln) or ln < 1 or ln > len(lines):
        return "range"
    sym = ev.get("symbol") or ""
    pats = [_word(sym)]
    if kind == "import" and "." in sym.strip("."):
        pats.append(_word(sym.strip(".").rsplit(".", 1)[1]))   # `import a.b.C` evidence may cite the `C` usage line
    win = lines[max(0, ln - 1 - ARCH_K):ln + ARCH_K]
    return "" if any(p.search(x) for p in pats for x in win) else "nosym"


def plan_globs(plan):
    """{module id: [globs]} from a plan.json dict; malformed entries are skipped (the plan is agent-written)."""
    out = {}
    mods = plan.get("modules") if isinstance(plan, dict) else None
    for x in mods if isinstance(mods, list) else ():
        g = x.get("globs") if isinstance(x, dict) else None
        if isinstance(x.get("id") if isinstance(x, dict) else None, str) and isinstance(g, list):
            gs = [y for y in g[:200] if isinstance(y, str) and 0 < len(y) <= PATH_MAX]
            if gs:
                out[x["id"]] = gs
    return out


def owns(mod, rel, globs):
    """Does module dict `mod` own repo-relative file `rel`? Plan globs (fnmatch) first, else modules[].path as a
    file or directory prefix. External modules own no repo file."""
    if mod.get("kind") != "module":
        return False
    gs = globs.get(mod["id"])
    if gs:
        return bool(_glob_re(tuple(gs)).match(rel))
    p = safe_rel(mod.get("path"))
    return bool(p) and (rel == p or rel.startswith(p + "/"))


@functools.lru_cache(maxsize=512)
def _glob_re(gs):
    # One regex per module: owns() runs for every tree file x module in contested().
    return re.compile("|".join("(?:%s)" % fnmatch.translate(g) for g in gs))


def _owners(tree, mods, globs):
    """{file: [module ids owning it]} for every tree file (kind=module only)."""
    ms = [d for d in (mods.values() if isinstance(mods, dict) else mods) if d.get("kind") == "module"]
    return {rel: [d["id"] for d in ms if owns(d, rel, globs)] for rel in tree}


def contested(tree, mods, globs, owners=None):
    """(files owned by >= 2 modules, {n, files[:20], pairs[:20], broad}). `broad` = modules owning every tree file.
    ⚠A shared file would let one line back edges of either module, so it backs none (why `overlap`)."""
    own = _owners(tree, mods, globs) if owners is None else owners
    bad = sorted(f for f, ids in own.items() if len(ids) > 1)
    pairs = sorted(set((a, b) for f in bad for i, a in enumerate(sorted(own[f])) for b in sorted(own[f])[i + 1:]))
    cnt = {}
    for ids in own.values():
        for x in ids:
            cnt[x] = cnt.get(x, 0) + 1
    broad = sorted(x for x, n in cnt.items() if own and n == len(own))
    return set(bad), {"n": len(bad), "files": bad[:20], "pairs": [list(p) for p in pairs[:20]], "broad": broad}


_DEF_KW = r"(?:def|class|function|const|let|var|interface|enum|record|struct|fun|func|fn|trait|type)"
_DEF_MOD = r"(?:(?:export|default|public|private|protected|internal|static|final|abstract|async|pub|open|data|sealed|" \
           r"inline|extern|virtual|override|unsafe|declare)\s+)*"


def _def_re(sym):
    w = re.escape(sym) + r"(?![A-Za-z0-9_$])"
    return re.compile(r"^\s*" + _DEF_MOD + _DEF_KW + r"\s+\*?" + w          # def/class/const ... sym
                      + r"|^" + w + r"\s*(?::|=(?!=))"                         # top-level `sym =` / `sym:`
                      + r"|^\s*(?:[\w$<>\[\],.*&:?]+\s+)*[*&]?" + w + r"\s*\([^;]*\)[^;{}]*\{"   # C-like `sym(...) {`
                      # object-literal method `sym: async <T>(..) =>` / `sym: function (` (not `sym: vi.fn()`)
                      + r"|^\s*" + w + r"\s*:\s*(?:async\s+)?(?:<[^()]*>\s*)?(?:\(|function\b)"
                      # interface/abstract `Type sym(..);` ⚠type token required, no `=`, no statement keyword
                      + r"|^(?!\s*(?:return|new|throw|await|yield|else|case)\b)\s*(?:[\w$<>\[\],.?]+\s+)+" + w
                      + r"\s*\([^;{}]*\)\s*(?:throws\s+[\w$.,\s]+)?;\s*$")


@functools.lru_cache(maxsize=64)
def _py_ast(text):
    """Parsed module or None (a file that does not parse proves nothing)."""
    try:
        return ast.parse(text, filename=_USER_SRC)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _py_class_attr(lines, s):
    """Is `s` an Assign/AnnAssign target or def directly in a class body? (ast: docstrings and dict keys never match)"""
    tree = _py_ast("\n".join(lines))
    for c in ast.walk(tree) if tree else ():
        if not isinstance(c, ast.ClassDef):
            continue
        for n in c.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == s:
                return True
            tg = n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, ast.AnnAssign) else []
            if any(isinstance(x, ast.Name) and x.id == s for x in tg):
                return True
    return False


_JREC_RE = re.compile(r"\brecord\s+([A-Za-z_$][\w$]*)\s*(?:<[^(]*>)?\s*\(")
_JANN_RE = re.compile(r"@[\w$.]+\s*(?:\([^()]*\))?")
_JGEN_RE = re.compile(r"<[^<>]*>")
_JIDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
_JTYPE_RE = re.compile(r"^\s*(?:@[\w$.]+(?:\([^()]*\))?\s+)*(?:(?:public|protected|private|abstract|final|static|"
                       r"sealed|non-sealed)\s+)*(?:class|record|enum|interface)\s+([A-Za-z_$][\w$]*)")
# `private final Foo<A, B> name;` / `int name = 1;` — a type token is required before the name.
_JFIELD_RE = re.compile(r"^(?!\s*(?:return|throw|new|else|case|yield|import|package)\b)\s*(?:@[\w$.]+(?:\([^()]*\))?\s+)*"
                        r"(?:(?:private|protected|public|static|final|transient|volatile)\s+)*[\w$.]+(?:<[^;=]*>)?"
                        r"(?:\[\])*\s+([A-Za-z_$][\w$]*)\s*(?:;|=)")
_LMB_ANN_RE = re.compile(r"@(?:lombok\.)?(Getter|Setter|Data|Value)\b(\s*\([^()]*\))?")
_LMB_ACC_RE = re.compile(r"(get|is|set)([A-Z][\w$]*)$")
_LMB_BUILDER_RE = re.compile(r"@(?:lombok\.)?(?:Super)?Builder\b")


@functools.lru_cache(maxsize=512)
def _word_re(w):
    return re.compile(r"(?<![\w$])" + re.escape(w) + r"(?![\w$])")


def _java_records(text):
    """[(record name, {component names})] for every `record X(...)` header in `text` (headers may span lines)."""
    out = []
    for m in _JREC_RE.finditer(text):
        i, depth = m.end(), 1
        while i < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            i += 1
        body = _JANN_RE.sub(" ", text[m.end():i - 1])
        while _JGEN_RE.search(body):   # ⚠nested generics: strip innermost first so `Map<K, List<V>>` keeps no comma
            body = _JGEN_RE.sub(" ", body)
        names = set()
        for comp in body.split(","):
            ids = _JIDENT_RE.findall(comp)
            if len(ids) >= 2:
                names.add(ids[-1])
        out.append((m.group(1), names))
    return out


def _lmb_flags(text):
    """{"get"/"set": True|False} from Lombok annotations in `text`; ⚠`AccessLevel.NONE` turns the accessor off."""
    out = {}
    for m in _LMB_ANN_RE.finditer(text):
        on = "AccessLevel.NONE" not in (m.group(2) or "")
        for k in {"Getter": ("get",), "Setter": ("set",), "Data": ("get", "set"), "Value": ("get",)}[m.group(1)]:
            out[k] = on
    return out


def _java_facts(lines):
    """(records, type names, has @Builder, getter fields, setter fields) of one Java file."""
    text = "\n".join(lines)
    head = next((k for k, x in enumerate(lines) if _JTYPE_RE.search(x)), None)
    cls = _lmb_flags("\n".join(lines[:head + 1])) if head is not None else {}
    get, set_ = set(), set()
    for k, x in enumerate(lines):
        fm = _JFIELD_RE.search(x)
        if not fm or k == head:
            continue
        j = k   # field-level annotation lines directly above the field
        while j > 0 and lines[j - 1].strip().startswith("@"):
            j -= 1
        fl = dict(cls, **_lmb_flags("\n".join(lines[j:k + 1])))
        if fl.get("get"):
            get.add(fm.group(1))
        if fl.get("set"):
            set_.add(fm.group(1))
    types = set(m.group(1) for m in (_JTYPE_RE.search(x) for x in lines) if m)
    return _java_records(text), types, bool(_LMB_BUILDER_RE.search(text)), get, set_


def _sym_seg(sym):
    raw = (sym or "").strip()
    return raw, raw.strip(".").rsplit(".", 1)[-1]


def java_generated(sym, owned_files, read, grep, ev, facts=None):
    """Record accessor or Lombok method in a `.java` file of `to` (`facts` = optional per-run {file: facts} cache).
    ⚠Counts only when the evidence file names the owning type, so `list.size()` / `obj.getId()` /
    `WebClient.builder()` never match an unrelated record / @Data / @Builder class."""
    s = _sym_seg(sym)[1]
    evt = "\n".join(ev or ())
    if not s or not evt or "\n" in s or not owned_files:
        return False
    m = _LMB_ACC_RE.match(s)
    fld = (m.group(2)[0].lower() + m.group(2)[1:]) if m else None
    q = "Builder" if s == "builder" else fld or s
    facts = {} if facts is None else facts
    for f in [f for f in grep(q) if f in owned_files and f.endswith(".java")][:50]:
        if f not in facts:
            facts[f] = _java_facts(read(f))
        recs, types, builder, get, set_ = facts[f]
        if any(s in comps and _word_re(name).search(evt) for name, comps in recs):
            return True
        named = any(_word_re(t).search(evt) for t in types)
        if named and (s == "builder" and builder or m and fld in (set_ if m.group(1) == "set" else get)):
            return True
    return False


def defined_base(sym, owned_files, read, grep):
    """`defined_in` without the evidence-dependent Java fallback (cacheable per (to, sym))."""
    raw, s = _sym_seg(sym)
    if not s or not owned_files or "\n" in s:   # ⚠git grep -F splits patterns on newlines
        return False
    # ⚠A file-name symbol (`index.html`) would otherwise be cut to its extension (`html`).
    if ("." in raw or "/" in raw) and any(f == raw or f.endswith("/" + raw) for f in owned_files):
        return True
    for f in owned_files:
        parts = f.split("/")
        if s in parts[:-1] or s == os.path.splitext(parts[-1])[0]:
            return True
    rx = _def_re(s)
    hits = [f for f in grep(s) if f in owned_files][:50]
    if any(rx.search(x[:2000]) for f in hits for x in read(f)):   # ⚠cap: the C-like branch backtracks on minified lines
        return True
    return any(_py_class_attr(read(f), s) for f in hits if f.endswith(".py"))


def defined_in(sym, mod, owned_files, read, grep, ev=None):
    """Is `sym` (last dotted segment) defined in module `mod`? (a) a file in `owned_files` (its uncontested files)
    is named `sym` (a file name/path, e.g. `index.html`), or a path component (file stem or dir) equals sym; else
    (b) `grep(sym)` -> candidate files, <= 50 owned ones read, a definition-line regex (or, in .py, a class-body
    assignment) must hit; else (c) a Java record accessor / Lombok method (`ev` = evidence file lines).
    ⚠Fail-closed: an empty/failed grep means not defined."""
    return defined_base(sym, owned_files, read, grep) or java_generated(sym, owned_files, read, grep, ev)


def import_alias(sym, lines, rel):
    """[(original name, [candidate module files])] for each `import X as sym` / `from M import X as sym` in the
    .py file `rel` (ast; `with ... as`, comments and strings never match). Relative imports resolve from `rel`."""
    tree = _py_ast("\n".join(lines)) if sym else None
    out = []
    for n in ast.walk(tree) if tree else ():
        if isinstance(n, ast.Import):
            out.extend((a.name, [a.name.replace(".", "/") + x for x in (".py", "/__init__.py")])
                       for a in n.names if a.asname == sym)
        elif isinstance(n, ast.ImportFrom):
            base = "/".join(rel.split("/")[:-n.level]) if n.level else ""
            m = "/".join(x for x in (base, (n.module or "").replace(".", "/")) if x)
            # `X` lives in module `m`, or is itself the submodule `m/X`.
            out.extend((a.name, [c + x for c in ((m, m + "/" + a.name) if m else (a.name,)) for x in (".py", "/__init__.py")])
                       for a in n.names if a.asname == sym)
    return out


def defined_or_alias(sym, ev_rel, read, defined, owned):
    """defined(sym), else defined(original) when `sym` is an import alias in the evidence's .py file whose module is
    a file of `to` (`owned()` = its uncontested files)."""
    if defined(sym):
        return True
    if not (ev_rel and ev_rel.endswith(".py")):
        return False
    al = import_alias(sym, read(ev_rel), ev_rel)
    return any(defined(o) for o, cs in al if set(cs) & owned())


def _grep(repo, commit, sym):
    """Files at the commit containing `sym` as a whole word; [] on any git error."""
    try:
        text, _n = _git_run_capped(repo, ["grep", "-l", "-z", "-I", "-w", "-F", "-e", sym, commit, "--"],
                                   ARCH_GIT_TIMEOUT, ARCH_TREE_MAX)
    except (subprocess.SubprocessError, OSError):
        return []
    pre = commit + ":"
    return [x[len(pre):] for x in text[:ARCH_TREE_MAX].split("\0") if x.startswith(pre)]


def owner_of(e, mods):
    """Module whose files may back edge `e`: `from` (always for read/write); `to` for serve or a non-module `from`
    (e.g. a hook calling in). ⚠Without this a line from module Z could back an X->Y edge — common symbols then pass almost everywhere."""
    k, f = e.get("kind"), mods[e["from"]]
    return f if k in ("read", "write") or (k != "serve" and f.get("kind") == "module") else mods[e["to"]]


def verify_map(repo, commit, m, globs=None):
    """Verdict dict {commit, total, passed, rate, edges:[{i, ok, why}], overlap} for a schema-valid map.
    An evidence counts only if its file belongs to the edge's owner module (else why `owner`) and to no other
    (`overlap`), the symbol is there, and for module->module import/call the symbol is defined in `to` (`nodef`)."""
    globs = globs or {}
    mods = {d["id"]: d for d in m["modules"]}
    try:
        tree = _tree(repo, commit)
    except (subprocess.SubprocessError, OSError):
        tree = set()
    memo = {}

    def read(rel):
        if rel not in memo:
            try:
                memo[rel] = _show(repo, commit, rel)
            except (subprocess.SubprocessError, OSError):
                memo[rel] = []
        return memo[rel]

    owners = _owners(tree, mods, globs)
    cont, overlap = contested(tree, mods, globs, owners)
    files_of, dmemo, gmemo, jmemo, facts = {}, {}, {}, {}, {}

    def owned(to):
        if to not in files_of:
            files_of[to] = set(f for f, ids in owners.items() if ids == [to])
        return files_of[to]

    def grep(s):
        if s not in gmemo:
            gmemo[s] = _grep(repo, commit, s)
        return gmemo[s]

    def defined(to, sym, rel):
        # Base result per (to, sym); only the Java fallback depends on the evidence file (it must name the type).
        if (to, sym) not in dmemo:
            dmemo[(to, sym)] = defined_base(sym, owned(to), read, grep)
        if dmemo[(to, sym)] or not rel:
            return dmemo[(to, sym)]
        if (to, sym, rel) not in jmemo:
            jmemo[(to, sym, rel)] = java_generated(sym, owned(to), read, grep, read(rel), facts)
        return jmemo[(to, sym, rel)]

    def why(x, e, own):
        rel = safe_rel(x.get("file"))
        if rel and not owns(own, rel, globs):
            return "owner"
        if rel in cont:
            return "overlap"
        w = check_evidence(x, e["kind"], tree, read)
        # ⚠Config/DI and external ends are exempt: their wiring is not a symbol defined in the target's files.
        if w == "" and e["kind"] in ("import", "call") and mods[e["from"]].get("kind") == "module" \
                and mods[e["to"]].get("kind") == "module" and not is_route(x["symbol"]) \
                and not defined_or_alias(x["symbol"], rel, read, lambda s: defined(e["to"], s, rel), lambda: owned(e["to"])):
            return "nodef"
        return w

    out = []
    for i, e in enumerate(m["edges"]):
        own = owner_of(e, mods)
        whys = [why(x, e, own) for x in e["evidence"]]
        ok = "" in whys
        out.append({"i": i, "ok": ok, "why": None if ok else whys[0]})
    passed = sum(1 for x in out if x["ok"])
    # ⚠No edges = nothing unverified; rate 1.0 so a one-module repo can pass (run() refuses >= 2 modules with 0 edges).
    rate = round(passed / len(out), 4) if out else 1.0
    return {"commit": commit, "total": len(out), "passed": passed, "rate": rate, "edges": out, "overlap": overlap}


def is_route(sym):
    """A URL/route string (`/codebook`, `http://...`): an HTTP call is wired by the router, not by a symbol defined in
    the target's files, so it skips `nodef` and the edge is shown as estimated instead of dropped."""
    s = str(sym or "")
    return s.startswith("/") or "://" in s


def est_of(e):
    ev = e.get("evidence") or []
    routed = bool(ev) and all(isinstance(x, dict) and is_route(x.get("symbol")) for x in ev)
    return 1 if e.get("kind") in EST_KINDS or e.get("est") or routed else 0


def plan_arch(plan):
    """Cleaned plan.arch {style, framework, units, evidence:[rel]} or None. ⚠Advisory only: a bad arch never fails the gate."""
    a = plan.get("arch") if isinstance(plan, dict) else None
    if not isinstance(a, dict) or set(a) - {"style", "framework", "units", "evidence"} or a.get("style") not in STYLES:
        return None
    fw, un, evs = a.get("framework", ""), a.get("units", ""), a.get("evidence")
    # Over-long free text is cut, not refused: a 124-char `units` once dropped a correct style without a word.
    fw, un = (x[:mx - 1] + "\u2026" if isinstance(x, str) and len(x) > mx else x for x, mx in ((fw, FW_MAX), (un, UNITS_MAX)))
    if not (_line(fw, FW_MAX, empty=True) and _line(un, UNITS_MAX, empty=True)):
        return None
    if not isinstance(evs, list) or not 1 <= len(evs) <= EV_MAX:
        return None
    rels = [safe_rel(x) if _line(x, PATH_MAX) else "" for x in evs]
    if not all(rels):
        return None
    return {"style": a["style"], "framework": fw, "units": un, "evidence": rels}


def check_style(arch, tree):
    """verify.json `style`: each evidence file must exist in the commit's tree; None without a plan.arch."""
    if not arch:
        return None
    evs = [{"file": f, "ok": f in tree} for f in arch["evidence"]]
    return {"style": arch["style"], "framework": arch["framework"], "units": arch["units"], "evidence": evs,
            "ok": all(x["ok"] for x in evs)}


def deviations(m, verdict, style):
    """verify.json `dev` [{i, a, b}]: verified, non-estimated import/call edges whose (from role, to role) is outside
    the style's flow. Edges with a missing role, or a role outside that style's table, on either end are not judged."""
    flow = STYLE_FLOW.get(style)
    if not flow:
        return []
    known = set(r for p in flow for r in p) | {"shared"}
    mods = {d["id"]: d for d in m["modules"]}
    out = []
    for v in verdict["edges"]:
        e = m["edges"][v["i"]]
        if not v["ok"] or est_of(e) or e["kind"] not in ("import", "call"):
            continue
        a, b = mods[e["from"]].get("role"), mods[e["to"]].get("role")
        if a in known and b in known and a != b and b != "shared" and (a, b) not in flow:
            out.append({"i": v["i"], "a": a, "b": b})
    return out


# Look-alikes for the chars that end a quoted label (`"`, `|`), start mermaid markdown (`) or get decoded as
# entities/tags (`#..;`, `&..;`, `<..>`). ⚠No `#NN;` entities: the in-page flowchart renderer (81e) does not decode them.
_MM_MAP = {c: " " for c in range(32)}
_MM_MAP.update({ord('"'): "'", ord("`"): "'", ord("|"): "\u00a6", ord("<"): "\u2039", ord(">"): "\u203a",
                ord("#"): "\uff03", ord("&"): "\uff06"})


def mm_text(s):
    """Mermaid label text, safe inside `"..."`; other chars ([ ] ' @ ; ...) stay as they are."""
    return (s or "").translate(_MM_MAP)


def render_md(m, verdict):
    """map.md: mermaid flowchart of passed edges only; estimated edges dashed. Node ids are n0..nN (module ids
    may contain `.`/`-`, which mermaid reads as edge syntax)."""
    nid = {d["id"]: "n%d" % k for k, d in enumerate(m["modules"])}
    rows = ["```mermaid", "flowchart LR"]
    for d in m["modules"]:
        t = mm_text(d["name"])
        rows.append('  %s%s' % (nid[d["id"]], '(["%s"])' % t if d["kind"] == "external" else '["%s"]' % t))
    for v in verdict["edges"]:
        if not v["ok"]:
            continue
        e = m["edges"][v["i"]]
        arrow = "-.->" if est_of(e) else "-->"
        lab = '|"%s"|' % mm_text(e["label"]) if e["label"] else ""
        rows.append("  %s %s%s %s" % (nid[e["from"]], arrow, lab, nid[e["to"]]))
    rows.append("```")
    return "\n".join(rows) + "\n"


def run(repo, commit):
    """Verify the stored map for (repo, commit), write verify.json + map.md. Returns (exit code, one-line summary)."""
    try:
        d = store_dir(repo, commit)
    except ValueError as e:
        return 1, "arch_verify: %s" % e
    try:
        m = read_json(os.path.join(d, "map.json"))
    except (OSError, ValueError) as e:
        return 1, "arch_verify: schema: map.json unreadable (%s)" % type(e).__name__
    errs = schema_errors(m, repo, commit)
    if errs:
        return 1, "arch_verify: schema: %s" % "; ".join(errs[:5])
    # ⚠rate 1.0 with no edges is only legitimate for a one-module repo; with more it means nothing was checked.
    if len(m["modules"]) >= 2 and not m["edges"]:
        return 1, "arch_verify: EMPTY: %d modules, 0 edges — nothing was checked" % len(m["modules"])
    try:
        plan = read_json(os.path.join(d, "plan.json"))
    except (OSError, ValueError):
        plan = {}
    globs, arch = plan_globs(plan), plan_arch(plan)
    v = verify_map(repo, commit, m, globs)
    try:
        tree = _tree(repo, commit) if arch else set()
    except (subprocess.SubprocessError, OSError):
        tree = set()   # unreadable tree: every style evidence reads as missing
    # ⚠Style and deviations are advisory: they never change the rate, the summary line or the exit code.
    v["style"] = check_style(arch, tree)
    v["dev"] = deviations(m, v, arch["style"] if arch else None)
    _write(os.path.join(d, "verify.json"), json.dumps(v, ensure_ascii=False) + "\n")
    _write(os.path.join(d, "map.md"), render_md(m, v))
    line = "arch_verify: rate %.2f (%d/%d)" % (v["rate"], v["passed"], v["total"])
    if v["overlap"]["n"]:
        line += " · overlap %d" % v["overlap"]["n"]
    if isinstance(plan, dict) and "arch" in plan and not arch:
        line += " · plan.arch ignored (invalid)"   # say it, so the plan stage can be rerun; still advisory
    return (0 if v["rate"] >= ARCH_GATE_MIN else 1), line


def last():
    """(repo, commit) from DATA_DIR/arch/_last.json, or raises ValueError."""
    try:
        j = read_json(os.path.join(ARCH_DIR, "_last.json"))
    except (OSError, ValueError):
        raise ValueError("_last.json unreadable")
    repo, commit = (j.get("repo"), j.get("commit")) if isinstance(j, dict) else (None, None)
    if not (isinstance(repo, str) and os.path.isdir(repo)):
        raise ValueError("_last.json: repo is not a directory")
    return os.path.realpath(repo), commit


def head_of(repo):
    """HEAD commit id of repo, "" if unreadable."""
    try:
        r = _git_run(repo, ["rev-parse", "HEAD"], ARCH_GIT_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return ""
    h = r.stdout.strip() if r.returncode == 0 else ""
    return h if COMMIT_RE.fullmatch(h) else ""
