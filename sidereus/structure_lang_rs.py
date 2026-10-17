"""Structure plug-in for Rust (`.rs`): treemap cells from one masked pass. Metadata only. ⚠Best-effort: missing beats guessing wrong. ⚠Linear: one
masking pass, one brace pass, heads cut to RS_HEAD_MAX, generics within RS_GEN_MAX (macro_rules! bodies = opaque blocks).
"""
import bisect
import hashlib
import re
from sidereus.structure_plug import lang_register

RS_HEAD_MAX = 800              # chars of an item head looked at (its tail)
RS_GEN_MAX = 300               # chars a <...> generic list may span before it is left alone
RS_USE_MAX = 4000              # chars of one `use` tree
RS_MOD_DEPTH = 16              # inline `mod x {}` nesting followed (deeper = opaque: `mod a {` x 2e4 is quadratic)

_TOK = re.compile(r'(?<![\w#])[bc]?r#*"|//|/\*|"|\'')
_CMT = re.compile(r"/\*|\*/")
_STR_BODY = re.compile(r'[^"\\]*(?:\\.[^"\\]*)*', re.S)
_WTOK = re.compile(r"[{};]")
_ATTR = re.compile(r"#!?\s*\[(?:[^\[\]]|\[[^\[\]]*\])*\]")
_VIS = r"(?:pub\s*(?:\([^()]{0,80}\))?\s*)?"
_ITEM = re.compile(r"\s*" + _VIS + r"(?:(?:const|async|unsafe|default|auto|extern\s*(?:\"[^\"]*\")?)\s+)*"
                   r"(fn|mod|struct|enum|union|trait|type|impl|extern|use)\b\s*(?:r#)?([A-Za-z_]\w*)?")
_PATH = re.compile(r"(?:[A-Za-z_]\w*\s*::\s*)*[A-Za-z_]\w*")
_ITEM_CTX = frozenset(("mod", "impl", "trait", "ext"))


def _blank(s):
    return re.sub(r"[^\n]", " ", s)


def _str_end(src, k, n):
    """-> (end, closing delimiter length) of the literal or block comment opening at src[k] (unterminated: n)."""
    if src[k] == "/":
        d, j = 1, k + 2
        while d:                                        # nested block comments
            q = _CMT.search(src, j)
            if not q:
                return n, 0
            d, j = d + (1 if q.group(0) == "/*" else -1), q.end()
        return j, 0
    if src[k] != '"':                                   # raw: [bc]?r#*"
        q = src.index('"', k)
        h = q - src.index("r", k) - 1
        j = src.find('"' + "#" * h, q + 1)
        return (n, 0) if j < 0 else (j + 1 + h, 1 + h)
    j = _STR_BODY.match(src, k + 1).end()
    return (j + 1, 1) if j < n else (n, 0)


def rs_mask(src):
    """Comments and string/char contents become spaces; length, newlines and quotes kept (`'a` lifetimes untouched)."""
    out, n, i, at = [], len(src), 0, 0
    while True:
        t = _TOK.search(src, i)
        if not t:
            break
        k, s = t.start(), t.group(0)
        if s == "'":
            j = src.find("'", k + 3, k + 12) if src[k + 1:k + 2] == "\\" else \
                k + 2 if src[k + 2:k + 3] == "'" and src[k + 1:k + 2] not in ("", "\n") else -1
            if j < 0:
                i = k + 1                                # lifetime or label
                continue
            b, e, z = k + 1, j + 1, 1
        elif s == "//":
            j = src.find("\n", k)
            b, e, z = k, n if j < 0 else j, 0
        else:
            (e, z), b = _str_end(src, k, n), (k if s == "/*" else t.end())
        out += [src[at:b], _blank(src[b:e - z]), src[e - z:e]]
        i = at = e
    out.append(src[at:])
    return "".join(out)


def _skip_gen(s, p):
    """s[p] == "<": index after the matching `>` within RS_GEN_MAX chars (`->` ignored), or -1."""
    d, k, lim = 0, p, min(len(s), p + RS_GEN_MAX)
    while k < lim:
        c = s[k]
        d += (c == "<") - (c == ">" and s[k - 1] != "-")
        k += 1
        if d == 0:
            return k
    return -1


def _after_gen(rest):
    """Head text after a name -> (generic param names, text after `<...>`); text None when the list does not close."""
    r = rest.lstrip()
    if not r.startswith("<"):
        return set(), r
    g = _skip_gen(r, 0)
    return (set(re.findall(r"[<,]\s*([A-Z]\w*)", r[:g])), r[g:].lstrip()) if g > 0 else (set(), None)


def _walk(m):
    """One pass over the masked text's `{` `;` `}` -> item list (scopes are inline-mod segment tuples)."""
    nl = [x.end() for x in re.finditer("\n", m)]
    ln = lambda i: bisect.bisect_right(nl, i) + 1     # noqa: E731
    root = {"k": "mod", "mp": (), "test": False}
    st, items, last, i = [], [], 0, 0
    while True:
        t = _WTOK.search(m, i)
        if not t:
            break
        k, c = t.start(), t.group(0)
        hs = max(last, k - RS_HEAD_MAX)
        i = last = k + 1
        top = st[-1] if st else root
        if c == "}":
            if st:
                _closed(st.pop(), k, m, ln, items)
            continue
        if top["k"] not in _ITEM_CTX:
            if c == "{":
                st.append({"k": "blk"})
            continue
        head = m[hs:k]
        if c == ";" and (head.count("[") > head.count("]") or head.count("(") > head.count(")")):
            last = hs                                   # `[u8; 4]` in a signature: the head goes on
            continue
        attrs = " ".join(_ATTR.findall(head))
        body = _ATTR.sub(lambda x: _blank(x.group(0)), head)
        mt = _ITEM.match(body)
        kw, name = (mt.group(1), mt.group(2)) if mt else ("", None)
        sc = {"mp": top.get("mp", ()), "test": top.get("test", False) or "cfg(test)" in attrs.replace(" ", "")}
        at = hs + (mt.start(2) if mt and name else 0)
        if kw == "use":
            j = k if c == ";" else m.find(";", k, k + RS_USE_MAX)
            if j >= 0:
                items.append(dict(sc, k="use", tree=m[hs + mt.end(1):j]))
                i = last = j + 1
            elif c == "{":
                st.append({"k": "blk"})
            continue
        e = {"k": "blk"}
        if kw == "mod" and name and len(sc["mp"]) < RS_MOD_DEPTH:
            items.append(dict(sc, k="mod", name=name, line=ln(at)))
            e = dict(sc, k="mod", mp=sc["mp"] + (name,))
        elif kw in ("struct", "enum", "union", "trait", "type") and name and top["k"] == "mod":
            e = dict(sc, k=kw, name=name, line=ln(at), rest=body[mt.end(2):], attrs=attrs, at=k, fns=[], decl=[])
            if c == ";":
                _closed(e, k, m, ln, items)
                continue
        elif kw == "impl" and top["k"] == "mod":
            e = dict(sc, k="impl", rest=body[mt.end(1):], line=ln(hs + mt.start(1)), fns=[])
        elif kw == "fn" and name:
            own = top if top["k"] in ("impl", "trait") else None
            if c == ";":
                if own is not None and own["k"] == "trait":
                    own["decl"].append(name)
                continue
            e = dict(sc, k="fn", name=name, rest=body[mt.end(2):], own=own, line=ln(at), at=k, hs=hs + len(head)
                     - len(head.lstrip()))
        elif kw == "extern":
            e = dict(sc, k="ext")
        if c == "{":
            st.append(e)
    return items, ln


def _closed(e, k, m, ln, items):
    """Block `e` ends at m[k] (or a `;` item): record it."""
    if e["k"] in ("blk", "ext", "mod"):
        return
    e["end"] = ln(k)
    if e["k"] == "fn":
        e["close"] = k
        if e["own"] is not None:
            e["own"]["fns"].append(e)
    elif e["k"] in ("struct", "enum", "union") and e.get("at", k) < k:
        e["body"] = m[e["at"] + 1:k]
    items.append(e)


def rs_parse(src):
    """Masked text + items of one file (memoized on the last source)."""
    s0, g0 = _last[0]
    if s0 is not None and s0 == src:
        return g0
    m = rs_mask(src)
    items, ln = _walk(m)
    got = {"m": m, "items": items, "ln": ln}
    _last[0] = (src, got)                  # ⚠one tuple: a reader never sees one file's source with another's parse
    return got


_last = [(None, None)]


def _impl_head(rest):
    """`impl` head after the keyword -> (generic names, trait text, self type segments) or None."""
    gen, r = _after_gen(rest)
    if r is None:
        return None
    r = re.split(r"\bwhere\b", r, maxsplit=1)[0]
    tr, ty = "", r
    for f in re.finditer(r"\bfor\b", r):
        pre = r[:f.start()]
        if pre.count("<") - pre.count(">") + pre.count("->") == 0 and not re.match(r"\s*<", r[f.end():]):
            tr, ty = pre.strip().lstrip("!"), r[f.end():]
            break
    pm = _PATH.match(re.sub(r"^\s*(?:&\s*(?:'\w+\s*)?(?:mut\s+)?|dyn\s+)*", "", ty).strip())
    return (gen, tr, [s for s in re.split(r"\s*::\s*", pm.group(0)) if s]) if pm else None


def rs_scan(src):
    """Treemap cells: functions with a body [{name, lang, line, lines, h, owner?}]; methods are `Type::f`."""
    p = rs_parse(src)
    out = []
    for x in p["items"]:
        if x["k"] != "fn":
            continue
        on = _owner(x)
        h = hashlib.md5(src[x["hs"]:x["close"] + 1].encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]
        out.append(dict({"name": (on + "::" if on else "") + x["name"], "lang": "rust", "line": x["line"],
                         "lines": max(1, x["end"] - x["line"] + 1), "h": h}, **({"owner": on} if on else {})))
    return sorted(out, key=lambda r: r["line"])


def _owner(x):
    """Type a fn belongs to: its trait, its impl's self type, or "" (free fn)."""
    o = x["own"]
    return "" if o is None else o["name"] if o["k"] == "trait" else (_impl_head(o["rest"]) or ((), "", [""]))[2][-1]


lang_register("rust", {"exts": (".rs",), "scan": rs_scan,
                       "test": r"(?:_tests?|(?:^|/)tests?)\.rs$", "test_dirs": ("tests", "benches"), "skip": ("target",)})
