"""Ruby plug-in for the Structure view (`.rb`): treemap cells — pure, no I/O.

`rb_mask` blanks comments, =begin/=end, __END__, strings (with #{} holes), %-literals, heredocs and regex literals;
`rb_parse` walks the masked text once for class/module/def nesting and block `end`s. ⚠Every scan is linear or
window-bounded: pathological input must stay under a second. Metadata only: identifiers, constant paths, lines.
"""
import hashlib
import itertools
import re
from sidereus.structure_lex import _blank, _ln
from sidereus.structure_plug import lang_register

RB_DECLS_MAX = 2000            # class/module records kept per file
RB_HEAD_MAX = 2000             # chars a def parameter list may span
RB_REGEX_MAX = 400             # a /regex/ literal must close within this many chars on its own line
RB_CONST_MAX = 50000           # constant references read per file
RB_USES_MAX = 60               # distinct constants kept per class
RB_FN_LINES_MAX = 900          # treemap: longer functions are dropped (same rule as the other languages)
RB_SKIP = ("vendor", "tmp", "log", "node_modules")
RB_TEST_DIRS = ("spec", "test")
_RB_TEST = re.compile(r"(?:_spec|_test)\.rb$")
_RUN = re.compile(r"[\"'`#/%<?\n]")
_HOLE = re.compile(r"[{}\"'\\]")
_QBODY = dict((q, re.compile(r"[^%s\\]*(?:\\.[^%s\\]*)*" % (q, q), re.S)) for q in "\"'")
_PAIR = {"(": ")", "[": "]", "{": "}", "<": ">"}
_HEREDOC = re.compile(r"<<([~-]?)([\"'`]?)([A-Za-z_]\w*)\2")
_PCT, _NOINT = "wWiIqQrsx", "qwis"
_OPCH = frozenset("\n;(,[{=!~|&?:+-*%<>^")
_OPKW = frozenset(("if", "unless", "when", "while", "until", "and", "or", "not", "return", "then", "elsif", "else",
                   "do", "begin", "case", "in", "yield"))
_KW = re.compile(r"(?<![\w.:$@])(class|module|def|if|unless|while|until|case|begin|for|do|end|include|extend|prepend|"
                 r"belongs_to|has_many|has_one|has_and_belongs_to_many|attr_reader|attr_writer|attr_accessor)\b"
                 r"(?![?!]|:(?!:))")
_CPATH = r"(?:::)?[A-Z]\w*(?:::[A-Z]\w*)*"
_CLSH = re.compile(r"[ \t]+(" + _CPATH + r")(?:[ \t]*<[ \t]*(" + _CPATH + r"))?")
_SCLS = re.compile(r"[ \t]*<<[ \t]*\w+")
_DEFH = re.compile(r"[ \t]+(?:(self|[A-Z]\w*)[ \t]*\.[ \t]*)?([A-Za-z_]\w*[?!=]?|\[\]=?|[+\-*/%<>=!~^&|]+@?)")
_ENDLESS = re.compile(r"[ \t]*=(?![=~>])")
_MIXH = re.compile(r"[ \t]*\(?[ \t]*(" + _CPATH + r"(?:[ \t]*,[ \t]*" + _CPATH + r")*)")
_SYMS = re.compile(r":([a-z_]\w*)")
_CONST = re.compile(r"(?<![\w:@$])" + _CPATH)
_REQ = re.compile(r"(?m)^[ \t]*(require_relative|require|load)\b[ \t(]*(?=[\"'])")
_STR_AT = re.compile(r"([\"'])([^\"'\n]{1,300})\1")
_TOPREQ = re.compile(r"(?m)^[ \t]*(?:require_relative|require|load)\b[^\n;]*")


def _lit_rx(close, open_, interp, _c={}):
    k = (close, open_, interp)
    if k not in _c:                            # bounded: one entry per delimiter character
        _c[k] = re.compile("[" + "".join(re.escape(c) for c in sorted(set("\\" + close + open_ + "#" * interp))) + "]")
    return _c[k]


def _lit_end(s, j, close, open_="", interp=True, lim=None):
    """Index after the delimiter closing a literal whose body starts at s[j], or -1 when it is not closed before `lim`.
    `open_` nests (bracket delimiters); `#{...}` holes are skipped by brace depth, nested quotes as plain strings."""
    n = len(s) if lim is None else lim
    rx, depth, hole = _lit_rx(close, open_, interp), 0, 0
    while j < n:
        if hole:
            x = _HOLE.search(s, j, n)
            if not x:
                return -1
            j, c = x.start(), x.group(0)
            if c == "\\":
                j += 2
                continue
            if c in "\"'":
                j = _QBODY[c].match(s, j + 1, n).end()
            else:
                hole += 1 if c == "{" else -1
            j += 1
            continue
        x = rx.search(s, j, n)
        if not x:
            return -1
        j, c = x.start(), x.group(0)
        if c == "\\":
            j += 2
        elif c == "#" and c != close:
            hole, j = (1, j + 2) if s[j + 1:j + 2] == "{" else (0, j + 1)
        elif open_ and c == open_:
            depth, j = depth + 1, j + 1
        elif depth:
            depth, j = depth - 1, j + 1
        else:
            return j + 1
    return -1


def _prev(s, i):
    """(last code char before s[i] past spaces, "" at the start · the word ending there unless it is `.x`/`:x`/`@x`).
    Bounded look-back."""
    j = i - 1
    while j >= 0 and s[j] in " \t" and i - j < 200:
        j -= 1
    if j < 0:
        return "", ""
    k = j
    while k >= 0 and _idc(s[k]) and j - k < 12:
        k -= 1
    return s[j], (s[k + 1:j + 1] if k < 0 or s[k] not in ".:@$" else "")


def _operand(s, i):
    """True when s[i] starts an operand (so `/` `%` `?` begin a literal there): after an operator, an opening bracket,
    a line start or a keyword."""
    c, w = _prev(s, i)
    return not c or c in _OPCH or w in _OPKW


def _bol(s, p):
    """At a line start: end of an =begin/=end block or of the file after __END__, else -1."""
    if s.startswith("=begin", p) and s[p + 6:p + 7] in ("", " ", "\t", "\r", "\n"):
        e = s.find("\n=end", p)
        e = -1 if e < 0 else s.find("\n", e + 5)
        return len(s) if e < 0 else e
    if s.startswith("__END__", p) and s[p + 7:p + 8] in ("", "\r", "\n"):
        return len(s)
    return -1


def _heredocs(s, p, hd):
    """Heredoc bodies starting at line start p, one per pending (id, indented) -> [(body start, body end)], next p."""
    n, out = len(s), []
    for ident, ind in hd:
        st = p
        while p < n:
            e = s.find("\n", p)
            e = n if e < 0 else e
            ln, p = s[p:e], e + 1
            if (ln.strip() if ind else ln.rstrip("\r")) == ident:
                out.append((st, e))            # the terminator line too (a bare constant otherwise)
                break
        else:
            out.append((st, n))                # ⚠unterminated heredoc blanks to the end
            return out, n
    return out, p


def rb_mask(src):
    """`src` with comments, literal contents and heredoc bodies blanked (same length, newlines kept)."""
    s, n = src, len(src)
    out, a, i, hd = [], 0, 0, []

    def cut(x, y):
        out.append(s[a:x])
        out.append(_blank(s[x:y]))
        return y
    e = _bol(s, 0)
    if e >= 0:
        a = i = cut(0, e)
    while i < n:
        mt = _RUN.search(s, i)
        if not mt:
            break
        i, c = mt.start(), mt.group(0)
        prev = s[i - 1] if i else ""
        if c == "\n":
            i += 1
            if hd:
                spans, nxt = _heredocs(s, i, hd)
                for x, y in spans:
                    a = cut(x, y)
                hd, i = [], max(i, nxt - 1) if nxt < n else n
                continue
            e = _bol(s, i)
            if e >= 0:
                a = i = cut(i, e)
            continue
        if prev == "$":                        # $" $' $/ $# globals
            i += 1
            continue
        if c == "#":
            e = s.find("\n", i)
            a = i = cut(i, n if e < 0 else e)
            continue
        if c in "\"'`":
            e = _lit_end(s, i + 1, c, "", c != "'")
            a = cut(i + 1, n if e < 0 else e - 1)
            i = n if e < 0 else e
            continue
        if c == "%":
            t = s[i + 1:i + 2]
            if t and t in _PCT and _delim(s[i + 2:i + 3]):
                d, b = s[i + 2], i + 3
            elif _delim(t) and t != "=" and _operand(s, i):
                d, b, t = t, i + 2, "Q"
            else:
                i += 1
                continue
            e = _lit_end(s, b, _PAIR.get(d, d), d if d in _PAIR else "", t not in _NOINT)
            a = cut(b, n if e < 0 else e - 1)
            i = n if e < 0 else e
            continue
        if c == "/" and _operand(s, i):
            le = s.find("\n", i)
            e = _lit_end(s, i + 1, "/", "", True, min(n if le < 0 else le, i + RB_REGEX_MAX))
            if e > 0:
                a = cut(i + 1, e - 1)
                i = e
                continue
        if c == "<":
            h = _HEREDOC.match(s, i)
            if h and (h.group(1) or h.group(2) or h.group(3)[0].isupper() and prev in ("", " ", "\t", "(", ",", "=")):
                hd.append((h.group(3), bool(h.group(1))))
                a = i = cut(h.start(2), h.end())
                continue
        if c == "?" and s[i + 1:i + 2] not in ("", " ", "\t", "\r", "\n") and not _idc(s[i + 2:i + 3]) \
                and _operand(s, i):
            a = cut(i + 1, i + 2)              # ?x character literal
            i += 2
            continue
        i += 1
    out.append(s[a:])
    return "".join(out)


def _delim(c):
    return bool(c) and not (c.isalnum() or c in "_ \t\r\n")


def _idc(c):
    return bool(c) and (c.isalnum() or c == "_")


def _pairs(m):
    """{"(" index: matching ")" index} over masked m, one pass (a per-def scan is quadratic on `def a(` x n)."""
    st, out = [], {}
    for x in re.finditer(r"[()]", m):
        if x.group(0) == "(":
            st.append(x.start())
        elif st:
            out[st.pop()] = x.start()
    return out


def _stmt(m, i):
    """True when the keyword at m[i] starts a statement (so if/unless/while/until open a block, not a modifier)."""
    c, w = _prev(m, i)
    return not c or c in "\n;(=,[{|&!" or w in ("then", "else", "do", "begin", "return", "and", "or", "not", "in")


def _camel(sym, single):
    """`line_items` -> LineItem (single) · `user` -> User."""
    w = re.sub(r"(?<=.)ies$", "y", sym) if single else sym
    w = w[:-1] if single and w.endswith("s") and not w.endswith("ss") else w
    return "".join(p[:1].upper() + p[1:] for p in w.split("_") if p)


def _body_stmt(m, src, rec, kw, e):
    """include/extend/prepend, associations and attr_* directly in a class body -> rec fields."""
    le = m.find("\n", e)
    line = m[e:len(m) if le < 0 else le][:600]
    if kw in ("include", "extend", "prepend"):
        h = _MIXH.match(line)
        if h:
            rec["mix"] += [re.sub(r"\s+", "", x) for x in h.group(1).split(",")][:20]
            rec["concern"] |= "Concern" in h.group(1)
    elif kw.startswith("attr_"):
        rec["attrs"] += _SYMS.findall(line)[:40]
    else:
        sy = _SYMS.search(line)
        cn = re.search(r"class_name:[ \t]*([\"'])", line) or re.search(r":class_name[ \t]*=>[ \t]*([\"'])", line)
        sv = _STR_AT.match(src, e + cn.start(1)) if cn else None
        if sv:
            rec["assoc"].append(sv.group(2).lstrip(":"))
        elif sy:
            rec["assoc"].append(_camel(sy.group(1), kw in ("has_many", "has_and_belongs_to_many")))


def _open_class(m, kw, x, st, recs):
    """class/module keyword at x -> frame (record appended to recs) or None."""
    if kw == "class":
        sc = _SCLS.match(m, x.end())
        if sc:
            return {"k": "sclass"}
    h = _CLSH.match(m, x.end())
    if not h or len(recs) >= RB_DECLS_MAX:
        return {"k": "block"}                  # still consumes its `end`
    path = h.group(1)
    parent = st[-1]["ncls"]["rec"]["full"] if st and st[-1]["ncls"] else ""
    full = path[2:] if path.startswith("::") else (parent + "::" + path if parent else path)
    key, _s, name = full.rpartition("::")
    rec = {"kw": kw, "name": name, "key": key, "full": full, "at": x.start(), "name_at": h.start(1) + path.rfind(name),
           "close": -1, "super": (h.group(2) or "") if kw == "class" else "", "mix": [], "assoc": [], "attrs": [],
           "defs": 0, "concern": False, "top": not st, "uses": []}
    recs.append(rec)
    return {"k": "cls", "rec": rec}


def _open_def(m, x, st, defs, pr):
    """def keyword at x -> frame or None (endless def: recorded, closes on its line)."""
    h = _DEFH.match(m, x.end())
    if not h:
        return None
    r, params = h.end(), ""
    if m[r:r + 1] == "(":
        z = pr.get(r, -1)
        if 0 < z < r + RB_HEAD_MAX:
            params, r = m[r + 1:z], z + 1
    elif not _ENDLESS.match(m, r):
        le = m.find("\n", r)
        params = m[r:len(m) if le < 0 else le].split(";")[0][:RB_HEAD_MAX]
    cls = st[-1]["near"] if st else None
    owner = st[-1]["ncls"]["rec"] if st and st[-1]["ncls"] else None
    d = {"name": h.group(2), "at": h.start(2), "hs": x.start(), "body": r, "close": -1, "owner": owner,
         "single": bool(h.group(1)) or bool(cls and cls["k"] == "sclass"), "params": params}
    if owner is not None:
        owner["defs"] += 1
    defs.append(d)
    if _ENDLESS.match(m, r):
        le = m.find("\n", r)
        d["close"] = len(m) if le < 0 else le
        return None
    return {"k": "def", "d": d}


def _push(st, f):
    """Push frame f carrying its nearest class/sclass (`near`) and class (`ncls`) frames.
    ⚠Inherited, not searched: walking the stack per keyword is quadratic on `class A` x n."""
    top = st[-1] if st else {"near": None, "ncls": None}
    f["near"] = f if f["k"] in ("cls", "sclass") else top["near"]
    f["ncls"] = f if f["k"] == "cls" else top["ncls"]
    st.append(f)


def _walk(m, src):
    """One keyword pass -> (class/module records, def records)."""
    st, recs, defs, pr = [], [], [], _pairs(m)
    for x in _KW.finditer(m):
        kw = x.group(1)
        if kw in ("class", "module"):
            f = _open_class(m, kw, x, st, recs)
            if f:
                _push(st, f)
        elif kw == "def":
            f = _open_def(m, x, st, defs, pr)
            if f:
                _push(st, f)
        elif kw in ("if", "unless", "while", "until", "case", "begin", "for"):
            if kw in ("case", "begin", "for") or _stmt(m, x.start()):
                le = m.find("\n", x.end())
                _push(st, {"k": "loop" if kw in ("while", "until", "for") else "block", "line": len(m) if le < 0 else le})
        elif kw == "do":
            top = st[-1] if st else None
            if top and top["k"] == "loop" and top.get("line", -1) > x.start():
                top["line"] = -1               # `while x do`: the loop's own optional `do`
            else:
                _push(st, {"k": "block"})
        elif kw == "end":
            if st:
                f = st.pop()
                if f["k"] == "cls":
                    f["rec"]["close"] = x.end()
                elif f["k"] == "def":
                    f["d"]["close"] = x.end()
        elif st and st[-1]["k"] == "cls":
            _body_stmt(m, src, st[-1]["rec"], kw, x.end())
    for f in st:                               # unclosed at EOF: classes run to the end, defs stay -1 (no cell)
        if f["k"] == "cls":
            f["rec"]["close"] = len(m)
    return recs, defs


def _uses(m, recs):
    """Constant references -> rec["uses"] of the innermost enclosing class/module (one sweep over nested spans)."""
    order = sorted(recs, key=lambda r: r["at"])
    act, k = [], 0
    for c in itertools.islice(_CONST.finditer(m), RB_CONST_MAX):
        p = c.start()
        while k < len(order) and order[k]["at"] <= p:
            while act and act[-1]["close"] < order[k]["at"]:
                act.pop()
            act.append(order[k])
            k += 1
        while act and act[-1]["close"] < p:
            act.pop()
        if act:
            r, t = act[-1], c.group(0)
            if len(r["uses"]) < RB_USES_MAX and "_" not in t and t not in r["uses"]:
                r["uses"].append(t)


def _module_code(m, recs):
    """True when code outside top-level class/module bodies remains (requires excluded)."""
    a, rest = 0, []
    for r in sorted((r for r in recs if r["top"]), key=lambda r: r["at"]):
        if r["at"] >= a:
            rest.append(m[a:r["at"]])
            a = r["close"]
    rest.append(m[a:])
    return any(_TOPREQ.sub("", t).strip() for t in rest)


def rb_parse(src):
    """Shared scan of one Ruby file (memoized on the last source)."""
    s0, g0 = _last[0]
    if s0 is not None and s0 == src:
        return g0
    m = rb_mask(src)
    recs, defs = _walk(m, src)
    _uses(m, recs)
    reqs = []
    for r in itertools.islice(_REQ.finditer(m), 500):
        sv = _STR_AT.match(src, r.end())
        if sv:
            reqs.append(("rr:" if r.group(1) == "require_relative" else "r:") + sv.group(2))
    got = {"m": m, "recs": recs, "defs": defs, "reqs": reqs, "lines": [x.start() for x in re.finditer("\n", m)],
           "code": _module_code(m, recs)}
    _last[0] = (src, got)                  # ⚠one tuple: a reader never sees one file's source with another's parse
    return got


_last = [(None, None)]


def rb_scan(src):
    """Treemap cells: methods (`Cls.meth`) and top-level defs with their `end`."""
    p = rb_parse(src)
    out = []
    for d in p["defs"]:
        if d["close"] < 0:
            continue
        a, b = _ln(p, d["hs"]), _ln(p, d["close"])
        if b - a + 1 > RB_FN_LINES_MAX:
            continue
        cls = d["owner"]["name"] if d["owner"] else ""
        body = src[d["hs"]:d["close"]]
        out.append({"name": (cls + "." if cls else "") + d["name"], "lang": "rb", "line": a, "lines": b - a + 1,
                    "h": hashlib.md5(body.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]})
    return out


lang_register("rb", {"exts": (".rb",), "scan": rb_scan, "test": _RB_TEST, "test_dirs": RB_TEST_DIRS,
                     "skip": RB_SKIP})
