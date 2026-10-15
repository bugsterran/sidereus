"""C# plug-in for the Structure view (`.cs`): treemap cells — pure, no I/O.

`cs_mask` blanks comments, strings (@"", $"", raw), directives and inactive #if branches; `cs_parse` is the shared
scan (namespaces, usings, types, members, local functions). ⚠Every scan is linear or window-bounded: pathological input
must stay under a second. Metadata only: identifiers, type names, line numbers.
"""
import hashlib
import itertools
import re
from sidereus.structure_lex import _blank, _close, _degen, _flat, _ln, _pairs
from sidereus.structure_plug import lang_register

CS_DECLS_MAX = 2000            # type decls read per file
CS_HEAD_MAX = 4000             # chars scanned for one declaration header
CS_FLAT_BUDGET = 1 << 20       # chars flattened per file (nested bodies are re-walked once per enclosing type)
CS_FN_LINES_MAX = 900          # treemap: longer functions are dropped (same rule as the other languages)
_STR_RUN = re.compile(r'["\'/@$#\n]')
_NS = re.compile(r"(?<![\w.@])namespace\s+([A-Za-z_][\w.]*)\s*([{;])")
_USING = re.compile(r"(?m)^[ \t]*(global[ \t]+)?using[ \t]+(?:(static)[ \t]+)?(?:([A-Za-z_]\w*)[ \t]*=[ \t]*)?"
                    r"([A-Za-z_][\w.]*(?:<[^;\n]{0,200}>)?)[ \t]*;")
_DECL = re.compile(r"(?<![\w@.])(class|interface|record|struct|enum)\s+(?:(class|struct)\s+)?([A-Za-z_]\w*)")
_NOT_NAME = frozenset(("where", "new", "class", "struct", "unmanaged", "notnull", "default"))
_KW = frozenset(("if", "for", "foreach", "while", "switch", "catch", "using", "lock", "fixed", "return", "new",
                 "throw", "await", "typeof", "sizeof", "nameof", "default", "checked", "unchecked", "when", "else",
                 "do", "try", "base", "this", "is", "as", "in", "out", "ref", "var", "stackalloc", "operator",
                 "get", "set", "init", "add", "remove", "yield", "delegate", "event"))
_MODS = frozenset(("public", "private", "protected", "internal", "static", "virtual", "override", "abstract",
                   "async", "sealed", "new", "extern", "unsafe", "partial", "readonly", "required", "const",
                   "volatile", "file", "ref", "implicit", "explicit"))
_ID = re.compile(r"[A-Za-z_]\w*")
_TYPE_ID = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_ATTR = re.compile(r"\[[^\[\]]*\]")
_TOP = re.compile(r"(?:\b(?:public|internal|static|partial|sealed|abstract|readonly|file|unsafe|ref)\s+)*"
                  r"\b(?:namespace|class|struct|interface|enum|record|delegate)\b")


def _str_end(s, j, verb, interp):
    """Index after the closing quote of a non-raw string whose body starts at s[j] (n when unterminated)."""
    n, depth = len(s), 0
    while j < n:
        c = s[j]
        if depth:
            depth += (c == "{") - (c == "}")
            if c == '"':                       # nested plain string inside a hole
                k = j + 1
                while k < n and s[k] not in '"\n':
                    k += 2 if s[k] == "\\" else 1
                j = k
            j += 1
            continue
        if c == '"' and not (verb and s[j + 1:j + 2] == '"'):
            return j + 1
        if c == "\n" and not verb:
            return j                           # ⚠unterminated regular string: stop at the line end
        if (c == "\\" and not verb) or (c == '"') or (interp and c == "{" and s[j + 1:j + 2] == "{"):
            j += 2                             # escape · verbatim "" · literal {{
            continue
        depth = 1 if interp and c == "{" else 0
        j += 1
    return n


def _pp(s, i):
    """Line at s[i] -> (index of its newline, directive word or "")."""
    j = s.find("\n", i)
    j = len(s) if j < 0 else j
    ln = s[i:j].lstrip()
    return j, ((_ID.match(ln[1:].lstrip()) or [""])[0] if ln.startswith("#") else "")


def cs_mask(src):
    """`src` with comments, string contents, directives and inactive #if branches blanked (same length, newlines kept).
    ⚠#if keeps the first branch only: symbols are unknown, and both branches together often do not parse."""
    s, n = src, len(src)
    out, a, i, bol, st = [], 0, 0, True, []

    def cut(x, y):
        out.append(s[a:x])
        out.append(_blank(s[x:y]))
        return y
    while i < n:
        mt = _STR_RUN.search(s, i)
        if not mt:
            break
        k = mt.start()
        if s[i:k].strip():
            bol = False
        i, c = k, s[k]
        if c == "\n":
            bol, i = True, i + 1
            continue
        if c == "#" and bol:
            j, w = _pp(s, i)
            hide = 0
            if w == "if":
                st.append(0)
            elif w in ("elif", "else") and st and st[-1] == 0:
                st[-1], hide = 1, len(st)
            elif w == "endif" and st:
                st.pop()
            a = i = cut(i, j)
            while hide and i < n and len(st) >= hide:    # inactive branch: whole lines until its #endif
                j, w = _pp(s, i + 1)
                if w == "if":
                    st.append(2)
                elif w == "endif":
                    st.pop()
                a = i = cut(i, j)
            continue
        bol = False
        if c == "/" and s[i + 1:i + 2] == "/":
            j = s.find("\n", i)
            j = n if j < 0 else j
            a = i = cut(i, j)
            continue
        if c == "/" and s[i + 1:i + 2] == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2          # ⚠unclosed block comment blanks to the end
            a = i = cut(i, j)
            continue
        if c == "'":
            j = i + 1
            while j < n and j < i + 12 and s[j] not in "'\n":
                j += 2 if s[j] == "\\" else 1
            if j < n and s[j] == "'":
                a = cut(i + 1, j)
                i = j + 1
            else:
                i += 1
            continue
        p = i
        while p < n and p < i + 8 and s[p] in "@$":
            p += 1
        if c == "/" or p >= n or s[p] != '"':
            i = max(p, i + 1)
            continue
        q = p
        while q < n and s[q] == '"':
            q += 1
        if q - p >= 3:                         # raw string: closes at the same run of quotes
            e = s.find('"' * (q - p), q)
            a = cut(q, n if e < 0 else e)
            i = n if e < 0 else e + q - p
        elif q - p == 2:
            i = q                              # empty ""
        else:
            e = _str_end(s, q, "@" in s[i:p], "$" in s[i:p])
            a = cut(q, e - 1 if e > q and s[e - 1] == '"' else e)
            i = e
    out.append(s[a:])
    return "".join(out)


def _split0(s):
    """Split on commas at paren/angle/bracket depth 0."""
    out, d, a = [], 0, 0
    for k, ch in enumerate(s):
        d += (ch in "(<[") - (ch in ")>]")
        if ch == "," and d == 0:
            out.append(s[a:k])
            a = k + 1
    return [x.strip() for x in out + [s[a:]] if x.strip()]


def _member(h, cls):
    """Member head (attributes allowed) -> ("method", name, ret, params, name offset) | ("field", name, type) | None."""
    h0 = _ATTR.sub(lambda x: " " * len(x.group(0)), h)
    ar = h0.find("=>")
    hh = h0 if ar < 0 else h0[:ar]
    words = re.findall(r"[A-Za-z_]\w*", hh[:200])
    if any(w in ("class", "struct", "interface", "enum", "record", "delegate", "namespace") for w in words[:6]):
        return None
    p, eq = hh.find("("), re.search(r"(?<![=!<>])=(?![=>])", hh)
    if p >= 0 and (not eq or eq.start() > p):
        pre = hh[:p].rstrip()
        if pre.endswith(">"):
            d, k = 0, len(pre) - 1
            while k >= 0:
                d += (pre[k] == ">") - (pre[k] == "<")
                if d == 0:
                    break
                k -= 1
            pre = pre[:max(k, 0)].rstrip()
        nm = re.search(r"(?<!\w)([A-Za-z_]\w*)$", pre)   # ⚠lookbehind: without it every start inside a long name is retried
        if not nm or nm.group(1) in _KW:
            return None
        lead = pre[:nm.start()].rstrip()
        if lead.endswith(("~", ".", "operator", "new")):
            return None
        z = _close(hh, p, "(", ")")
        if z < 0:
            return None
        ret = " ".join(w for w in lead.split() if w not in _MODS)
        if not ret and nm.group(1) != cls:
            return None                        # a call statement, not a declaration
        return "method", nm.group(1), ret, hh[p + 1:z], nm.start(1)
    body = hh[:eq.start()] if eq else hh
    bits = [w for w in body.replace("?", "? ").split() if w not in _MODS and w != "event"]
    if len(bits) >= 2 and _ID.fullmatch(bits[-1]) and bits[-1] not in _KW:
        return "field", bits[-1], " ".join(bits[:-1]).replace("? ", "?")
    return None


def _segments(flat, base):
    """Member heads of a depth-1 body text -> [(head start, head text, block open or -1, end)] (offsets from base)."""
    out, hs, pd, skip = [], 0, 0, -1
    for k, ch in enumerate(flat):
        if k <= skip:
            continue
        if ch == "(":
            pd += 1
        elif ch == ")":
            pd = max(0, pd - 1)
        elif ch == "{" and pd == 0 and "=>" in flat[hs:k]:
            skip = flat.find("}", k) % (len(flat) + 1)   # ⚠expression body (`=> x is { } o ? …;`): braces are not a block
        elif ch in ";{" and pd == 0:
            z = (flat.find("}", k) % (len(flat) + 1)) if ch == "{" else k      # nested block: its `}` (or the end)
            out.append((base + hs, flat[hs:k], base + k if ch == "{" else -1, base + z))
            hs = z + 1
        elif ch == "}" and pd == 0:
            hs = k + 1
    return [x for x in out if x[1].strip()]


def _head_end(m, a):
    """End of a type header from m[a]: index of `{` (body) or `;` (none) -> (index, has_body); bounded."""
    lim = min(len(m), a + CS_HEAD_MAX)
    b = m.find("{", a, lim)
    k = min(x for x in (b, m.find(";", a, lim), lim) if x >= 0)
    return k, k == b


def _supers(head):
    """Header after the name -> (primary ctor params text, [base names])."""
    h, ctor = head.lstrip(), ""
    if h.startswith("<") and _close(h, 0, "<", ">") > 0:
        h = h[_close(h, 0, "<", ">") + 1:].lstrip()
    z = _close(h, 0, "(", ")") if h.startswith("(") else -1
    if z > 0:
        ctor, h = h[1:z], h[z + 1:].lstrip()
    bases = []
    if h.startswith(":"):
        for ent in _split0(_degen(re.split(r"\bwhere\b", h[1:])[0])):
            t = _TYPE_ID.match(re.sub(r"\(.*", "", ent, flags=re.S).strip())
            if t:
                bases.append(t.group(0))
    return ctor, bases


def _mods(m, a):
    back = m[max(0, a - 300):a]
    cut = max(back.rfind(";"), back.rfind("{"), back.rfind("}"))
    return set(re.findall(r"[a-z]+", _ATTR.sub(" ", back[cut + 1:])))


def _types(m, br, nss):
    """Type declarations -> [dict] in source order."""
    out, budget = [], [CS_FLAT_BUDGET]
    for d in _DECL.finditer(m):
        if len(out) >= CS_DECLS_MAX:
            break
        name = d.group(3)
        if name in _NOT_NAME or d.group(1) == "class" and re.search(r":\s*$", m[max(0, d.start() - 40):d.start()]):
            continue                           # `where T : class`
        kw = d.group(1)
        kind = {"record": "struct" if d.group(2) == "struct" else "class"}.get(kw, kw)
        end, body = _head_end(m, d.end())
        ctor, bases = _supers(m[d.end():end])
        close = br.get(end, -1) if body else -1
        ns = ".".join(nm for a, z, nm in nss if a < d.start() < z)
        t = {"kw": kw, "kind": kind, "name": name, "at": d.start(), "name_at": d.start(3), "open": end if body else -1,
             "close": close, "ctor": ctor, "bases": bases, "ns": ns, "mods": _mods(m, d.start()), "flat": ""}
        if close > 0 and budget[0] > 0:
            t["flat"] = _flat(m, end + 1, close, br)
            budget[0] -= len(t["flat"])
        out.append(t)
    return out


def _local_fns(m, br, a, b, owner, out, seen):
    """Local functions: blocks inside m[a:b] whose head declares `Type Name(params)`."""
    for x in re.finditer(r"\{", m[a:b]):
        p = a + x.start()
        z = br.get(p)
        if z is None or p in seen:
            continue
        w = m[max(a, p - 2000):p]
        hs = max(w.rfind(";"), w.rfind("{"), w.rfind("}")) + 1
        got = _member(w[hs:], "\x00")
        if got and got[0] == "method" and got[2]:
            seen.add(p)
            out.append({"cls": owner, "name": got[1], "ret": got[2], "params": got[3], "at": p - len(w) + hs + got[4],
                        "open": p, "close": z, "local": 1})


def cs_parse(src):
    """Shared scan of one C# file (memoized on the last source)."""
    s0, g0 = _last[0]
    if s0 is not None and s0 == src:
        return g0
    m = cs_mask(" " + src[1:] if src[:1] == "\ufeff" else src)     # ⚠a BOM hides the first `using` from ^-anchors
    br = _pairs(m, "{", "}")
    nss = [(x.start(), br.get(x.end() - 1, len(m)) if x.group(2) == "{" else len(m), x.group(1))
           for x in itertools.islice(_NS.finditer(m), 200)]
    usings, binds = [], {}
    for u in _USING.finditer(m):
        tgt = re.sub(r"\s+", "", src[u.start(4):u.end(4)])
        if u.group(3):
            binds[u.group(3)] = tgt
        else:
            usings.append(tgt)             # a global using also counts here; elsewhere the unique-name fallback covers it
    types = _types(m, br, nss)
    meths, seen = [], set()
    for i, t in enumerate(types):
        if not t["flat"] or t["kind"] == "enum":
            continue
        for hs, head, o, e in _segments(t["flat"], t["open"] + 1):
            got = _member(head, t["name"])
            if got and got[0] == "method":
                z = br.get(o, -1) if o >= 0 else -1
                meths.append({"cls": i, "name": got[1], "ret": got[2], "params": got[3], "at": hs + got[4],
                              "hs": hs, "open": o, "close": z, "end": e, "ctor": got[1] == t["name"]})
                if o >= 0:
                    seen.add(o)
            elif got:
                t.setdefault("fields", []).append((got[1], got[2]))
    top = re.sub(r"(?m)^[ \t]*(?:global[ \t]+)?using\b[^;\n]*;|\bextern\s+alias\b[^;]*;", "",
                 _ATTR.sub(" ", _flat(m, 0, len(m), br)))
    cut = _TOP.search(top)
    module = bool(re.search(r"[;)]", top[:cut.start()] if cut else top))
    locs = []
    for x in list(meths):
        if x["open"] >= 0 and x["close"] > 0:
            _local_fns(m, br, x["open"] + 1, x["close"], x["cls"], locs, seen)
    if module:
        span = min([t["at"] for t in types] + [a for a, _z, _n in nss] + [len(m)])
        _local_fns(m, br, 0, span, -1, locs, seen)
    lines = [x.start() for x in re.finditer("\n", m)]
    got = {"m": m, "br": br, "ns": nss, "usings": usings, "binds": binds, "types": types,
           "meths": meths + locs, "module": module, "lines": lines, "fnat": set(x["at"] for x in locs)}
    _last[0] = (src, got)                  # ⚠one tuple: a reader never sees one file's source with another's parse
    return got


_last = [(None, None)]


def cs_scan(src):
    """Treemap cells: methods, constructors and local functions with a block body."""
    p = cs_parse(src)
    out = []
    for x in p["meths"]:
        if x["open"] < 0 or x["close"] < 0:
            continue
        a, b = _ln(p, x["at"]), _ln(p, x["close"])
        if b - a + 1 > CS_FN_LINES_MAX:
            continue
        cls = p["types"][x["cls"]]["name"] + "." if x["cls"] >= 0 else ""
        body = src[x["at"]:x["close"] + 1]
        out.append({"name": cls + x["name"], "lang": "cs", "line": a, "lines": b - a + 1,
                    "h": hashlib.md5(body.encode("utf-8", "replace")).hexdigest()[:12]})
    return out


lang_register("cs", {"exts": (".cs",), "scan": cs_scan, "test": r"Tests?\.cs$", "test_dirs": r"\.(?:Unit|Integration)?Tests?$",
                     "skip": ("bin", "obj", "packages"), "gen": r"(?:\.g|\.Designer)\.cs$|(?:^|/)AssemblyInfo\.cs$"})
