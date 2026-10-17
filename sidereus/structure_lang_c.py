"""Structure plug-in for C/C++: treemap function cells from one masked pass.

Metadata only (names, kinds, paths, lines). ⚠Best-effort, no parser: missing beats guessing wrong.
⚠Every step is linear in the file: one masking pass, one brace pass, declaration heads cut to C_HEAD_MAX chars,
  template<...> skipped within C_TMPL_MAX chars — pathological input (`<` x 1e5, `#if 0` x 5e4) stays fast.
"""
import bisect
import hashlib
import re
from sidereus.structure_c_util import (C_HEAD_MAX, C_TMPL_MAX, _close_paren, _qual_back, _skip_tmpl,
                                    c_mask)
from sidereus.structure_plug import lang_register

C_EXTS = (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx", ".inl")
C_SKIP = ("third_party", "external", "vendor", "deps", "build", "cmake-build-*")
C_GEN = ("*.pb.*", "moc_*", "ui_*")
C_TEST_DIRS = ("test", "tests", "unittest", "unittests", "testing")
_C_TEST = re.compile(r"(?:_test|_tests|_unittest|Test|Tests)\.(?:c|cc|cpp|cxx)$|(?:^|/)test_[^/]*\.(?:c|cc|cpp|cxx)$")

_CPP_HINT = re.compile(r"\b(?:class|namespace|template)\b|::")
_NS = re.compile(r"(?:^|[\s;}])(?:inline\s+)?namespace\b\s*([\w:]*)\s*(?:\[\[[^\]]*\]\]\s*)?$")
_EXTERN = re.compile(r'(?:^|\s)extern\s*"\s*"\s*$')
_KW_TYPE = re.compile(r"\b(class|struct|union|enum)\b")
_ACCESS = re.compile(r"^\s*(?:(?:public|protected|private|signals|slots|Q_SIGNALS|Q_SLOTS)(?:\s+slots)?\s*:(?!:)\s*"
                     r"|[A-Z_][A-Z0-9_]*[ \t]*\n\s*)+")
_ATTR = re.compile(r"\[\[[^\]]*\]\]|__attribute__\s*\(\([^()]*\)\)|__declspec\s*\([^()]*\)|alignas\s*\([^()]*\)")
_FN_TAIL = re.compile(r"^\s*(?:(?:const|volatile|noexcept|override|final|try|[A-Z_][A-Z0-9_]*)\b\s*|&&?\s*|"
                      r"(?:throw|noexcept)\s*\([^()]*\)\s*|__attribute__\s*\(\([^()]*\)\)\s*)*(?:->[^{};=]*)?$")
_FN_PRE = re.compile(r"^[\w\s:<>,*&~\[\]]*$")
_PURE = re.compile(r"=\s*(0|default|delete)\s*$")
_ID = re.compile(r"[A-Za-z_]\w*")
_NOT_FN = frozenset(("if", "for", "while", "switch", "catch", "return", "sizeof", "alignof", "decltype", "static_assert",
                     "defined", "else", "do", "new", "delete", "throw", "case", "goto", "typeof", "__typeof__",
                     "noexcept", "alignas", "operator"))
_PRE_BAD = frozenset(("return", "else", "new", "delete", "throw", "case", "goto", "using", "typedef", "friend"))
_BUILTIN = frozenset(("const", "static", "mutable", "volatile", "unsigned", "signed", "int", "char", "long", "short",
                      "float", "double", "bool", "void", "auto", "inline", "constexpr", "struct", "class", "enum",
                      "union", "std", "size_t", "typename", "virtual", "explicit", "extern", "register", "thread_local",
                      "wchar_t", "char16_t", "char32_t", "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t",
                      "uint16_t", "uint32_t", "uint64_t", "nullptr_t", "ptrdiff_t", "intptr_t", "uintptr_t"))


def fn_head(h, decl=False):
    """Function signature head -> {name, owner, params, ret, init, pure} or None.
    decl: a `;`-ended declaration (`= 0` / `= default` / `= delete` allowed). init: ctor init list follows `)`."""
    h = _skip_tmpl(_ATTR.sub(" ", h))
    pm = _PURE.search(h) if decl else None
    pure, h = (pm.group(1), h[:pm.start()]) if pm else (None, h)
    h0 = h
    h = re.sub(r"\boperator\s*(?:\(\s*\)|[^\w\s(]{1,3})\s*(?=\()", lambda x: "operator" + "@" * (len(x.group(0)) - 8), h)
    p = h.find("(")
    if p < 0:
        return None
    q = _qual_back(h[:p])
    if not q:
        return None
    segs, st = q
    name = segs[-1]
    if name == "operator" and h[st:p].rstrip().endswith("@"):
        name = "operator" + re.sub(r"\s", "", h0[h.rfind("operator", st, p) + 8:p])
    elif name in _NOT_FN or (decl and name.isupper() and not h[:st].strip()):
        return None                            # keywords; an ALLCAPS macro statement in a class body
    pre = h[:st]
    if not _FN_PRE.match(pre) or set(_ID.findall(pre)) & _PRE_BAD:
        return None
    z = _close_paren(h, p)
    if z < 0:
        return None
    rest = h[z + 1:]
    init = rest.lstrip()[:1] == ":" and rest.lstrip()[:2] != "::"
    if not init and not _FN_TAIL.match(rest[:C_HEAD_MAX]):
        return None
    return {"name": name, "owner": segs[-2] if len(segs) > 1 else "", "qual": "::".join(segs[:-2]),
            "params": h[p + 1:z], "ret": pre.strip(), "init": init, "pure": pure}


def _split_top(s):
    """Split on commas outside <> () []."""
    out, d, a = [], 0, 0
    for k, c in enumerate(s):
        d = max(0, d + (c in "<([") - (c in ">)]"))
        if c == "," and d == 0:
            out.append(s[a:k])
            a = k + 1
    out.append(s[a:])
    return [x.strip() for x in out if x.strip()]


def _cls_head(head):
    """class/struct/union/enum head -> (kw, name, [bases], typedef) or None. EXPORT_MACRO / attributes skipped."""
    h = _skip_tmpl(_ATTR.sub(" ", head))
    ms = list(_KW_TYPE.finditer(h))
    if not ms:
        return None
    m0 = ms[-1]
    pre, rest = h[:m0.start()], h[m0.end():]
    if not re.match(r"^(?:\s*(?:typedef|enum|export|static|const|inline)\b)*\s*$", pre):
        return None
    kw = "enum" if m0.group(1) == "enum" or re.search(r"\benum\s*$", pre) else m0.group(1)
    c = re.search(r"(?<!:):(?!:)", rest)
    namepart, bases = (rest[:c.start()], rest[c.end():]) if c else (rest, "")
    if re.search(r"[=(){};*&]", namepart):
        return None
    # ⚠`Name<...>` = a (partial) specialization of a primary template, not a new type: left unnamed (no node)
    toks = [] if "<" in namepart else [t for t in re.findall(r"[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*", namepart) if t != "final"]
    ext = []
    for b in ([] if kw == "enum" else _split_top(bases)):
        b = re.sub(r"\b(?:public|protected|private|virtual)\b", " ", b).strip()
        q = re.match(r"[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*", re.sub(r"<.*", "", b).strip().lstrip(":").strip())
        if q:
            ext.append(re.sub(r"\s+", "", q.group(0)))
    name = re.sub(r"\s+", "", toks[-1]).split("::")[-1] if toks else ""
    return kw, name, ext, bool(re.search(r"\btypedef\b", pre))


def _field(stmt):
    """Member statement -> [(name, type)] or [] (not a field)."""
    s = _split_top(re.split(r"=|\{", stmt, maxsplit=1)[0])
    if not s:
        return []
    first = re.sub(r"\[[^\]]*\]|:\s*\d+\s*$", " ", s[0]).strip()
    ids = list(_ID.finditer(first))
    if len(ids) < 2 or not re.match(r"^[\w\s:<>,*&]*$", first):
        return []
    ty = first[:ids[-1].start()].strip()
    out = [(ids[-1].group(0), ty)]
    for x in s[1:]:
        q = _ID.findall(x)
        if q:
            out.append((q[-1], ty))
    return out


def _member(e, stmt, line):
    """A `;`-ended statement directly in class body `e` -> method / field bookkeeping."""
    s = _skip_tmpl(_ACCESS.sub("", stmt)).strip()
    w = s.split(None, 1)[0] if s else ""
    if not s or w in ("using", "typedef", "friend", "static_assert", "class", "struct", "enum", "union", "namespace"):
        return
    f = fn_head(s, decl=True)
    if f:
        if not f["name"].startswith("~"):
            e["meths"].append({"m": f["name"], "line": line, "params": f["params"], "ret": f["ret"],
                               "pure": f["pure"] == "0", "body": None})
        return
    _fields(e, s)


def _fields(e, s):
    for nm, ty in _field(s):
        e["fields"][nm] = ty
        e["uses"] += [t for t in _ID.findall(ty) if t not in _BUILTIN][:8]


def _ns_path(stack):
    return "::".join(x["name"] for x in stack if x["k"] in ("ns", "cls") and x["name"])


def _open(head, stack, k, ln, pend):
    """Classify the `{` at k by its head -> stack entry; pend = [ctor waiting for its body] (mutated)."""
    tk = stack[-1]["k"] if stack else "ns"
    hs = k - len(head) + (len(head) - len(head.lstrip()))
    e = {"k": "blk", "name": "", "at": k, "hs": hs, "line": ln(hs)}
    if tk in ("fn", "blk", "init"):
        return e
    if pend and pend[-1][0] == len(stack):
        if re.search(r"[\w>]\s*$", head):
            return dict(e, k="init")           # another brace-initialised member of the ctor init list
        f = pend.pop()[1]
        return dict(f, k="fn", at=k)
    s = _ACCESS.sub("", head) if tk == "cls" else head
    m = _NS.search(s)
    if m:
        return dict(e, k="ns", name=m.group(1))
    if _EXTERN.search(s):
        return dict(e, k="ext")
    c = _cls_head(s)
    if c:
        return dict(e, k="cls", kw=c[0], name=c[1], ext=c[2], tdef=c[3], ns=_ns_path(stack), fields={}, meths=[],
                    uses=[])
    f = fn_head(s)
    if f:
        own = f["owner"] or (stack[-1]["name"] if tk == "cls" else "")
        ns = "::".join(x for x in (_ns_path([s for s in stack if s["k"] == "ns"]), f["qual"]) if x)
        fe = dict(e, k="fn", name=f["name"], owner=own, params=f["params"], ret=f["ret"], ns=ns, out=bool(f["owner"]))
        if f["init"] and re.search(r"[\w>]\s*$", head):
            pend.append((len(stack), fe))
            return dict(e, k="init")
        return fe
    if tk == "cls":
        _fields(stack[-1], s.strip())          # `std::vector<T> v_{};` — a brace-initialised field
    return e


def c_walk(m):
    """One pass over the masked text's `{` `;` `}` (braces paired once on a stack) -> (classes, functions, first ns)."""
    nl = [x.end() for x in re.finditer("\n", m)]
    ln = lambda i: bisect.bisect_right(nl, i) + 1     # noqa: E731
    stack, classes, funcs, pend, last, ns0 = [], [], [], [], 0, ""
    for t in re.finditer(r"[{};]", m):
        k, c = t.start(), t.group(0)
        head = m[max(last, k - C_HEAD_MAX):k]
        last = k + 1
        if c == "{":
            e = _open(head, stack, k, ln, pend)
            if e["k"] == "ns" and e["name"] and (not ns0 or _ns_path(stack).startswith(ns0)):
                ns0 = _ns_path(stack + [e])            # deepest namespace of the first chain
            stack.append(e)
        elif c == ";":
            if pend and pend[-1][0] == len(stack):
                pend.pop()
            if stack and stack[-1]["k"] == "cls":
                _member(stack[-1], head, ln(k - len(head) + len(head) - len(head.lstrip())))
        elif stack:
            e = stack.pop()
            e["close"], e["end"] = k, ln(k)
            if e["k"] == "cls":
                if e["tdef"] and not e["name"]:
                    q = re.match(r"\s*([A-Za-z_]\w*)\s*[;,\[]", m[k + 1:k + 1 + C_TMPL_MAX])
                    e["name"] = q.group(1) if q else ""
                if e["name"]:
                    classes.append(e)
            elif e["k"] == "fn":
                funcs.append(e)
                if stack and stack[-1]["k"] == "cls" and not e["name"].startswith("~"):
                    stack[-1]["meths"].append({"m": e["name"], "line": e["line"], "params": e["params"],
                                               "ret": e["ret"], "pure": False, "body": (e["at"], k)})
    return classes, funcs, ns0


def c_lang(rel, src, m=None):
    """"cpp" or "c"; a .h is cpp when it has class / namespace / template / `::`."""
    if rel.endswith(".h"):
        return "cpp" if _CPP_HINT.search(m if m is not None else c_mask(src)[0]) else "c"
    return "c" if rel.endswith(".c") else "cpp"


def c_scan(src):
    """Treemap cells: free and member functions [{name, lang, line, lines, h, owner?}]; members are `Foo::bar`."""
    m, _i = c_mask(src)
    lang = "cpp" if _CPP_HINT.search(m) else "c"
    out = []
    for f in c_walk(m)[1]:
        h = hashlib.md5(src[f["hs"]:f["close"] + 1].encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]
        out.append(dict({"name": (f["owner"] + "::" if f["owner"] else "") + f["name"], "lang": lang, "line": f["line"],
                         "lines": max(1, f["end"] - f["line"] + 1), "h": h}, **({"owner": f["owner"]} if f["owner"] else {})))
    return sorted(out, key=lambda r: r["line"])


lang_register("c", {"exts": C_EXTS, "lang": c_lang, "scan": c_scan, "test": _C_TEST, "test_dirs": C_TEST_DIRS,
                    "skip": C_SKIP, "gen": C_GEN})
