"""Symbol definition checks for the architecture map verifier (moved out of arch_verify; same rules).

`defined_in` / `defined_base` / `java_generated` / `defined_or_alias` decide whether an evidence symbol is defined in
the edge's `to` module (definition-line regex, Python class-body attribute, import alias, Java record accessor or
Lombok method). Used by arch_verify.verify_map and arch_flow.verify_flows. Stdlib only.
"""
import ast
import functools
import os
import re
import warnings

# ⚠Same SyntaxWarning filter as structure_lang: ast.parse of user code must not print to viewer.err.
_USER_SRC = "<user-src>"
warnings.filterwarnings("ignore", category=SyntaxWarning, module=re.escape(_USER_SRC) + "$")


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
