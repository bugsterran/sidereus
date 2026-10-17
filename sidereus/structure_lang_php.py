"""PHP plug-in for the Structure view (`.php`): treemap cells — pure, no I/O.

`php_mask` blanks inline HTML (outside `<?php … ?>`), comments (//, #, /* */), string contents ('', "", ``) and
heredoc/nowdoc bodies; `php_parse` is the shared scan (namespaces, use imports, types, members, functions).
⚠Every scan is linear or window-bounded: pathological input must stay under a second.
Metadata only: identifiers, type names, line numbers.
"""
import bisect
import hashlib
import re
from sidereus.structure_lex import _blank, _flat, _ln, _pairs
from sidereus.structure_plug import lang_register

PHP_DECLS_MAX = 2000           # type decls read per file
PHP_HEAD_MAX = 4000            # chars scanned for one declaration header
PHP_FLAT_BUDGET = 1 << 20      # chars flattened per file
PHP_FN_LINES_MAX = 900         # treemap: longer functions are dropped (same rule as the other languages)
PHP_NS_MAX = 200
_RUN = re.compile(r"""['"`#/]|<<<|\?>""")
_OPEN = re.compile(r"<\?(?:php(?!\w)|=)", re.I)
_HEREDOC = re.compile(r"<<<[ \t]*(['\"]?)([A-Za-z_]\w*)\1\r?\n")
_QRX = {"'": re.compile(r"[\\']"), '"': re.compile(r'[\\"]'), "`": re.compile(r"[\\`]")}
_NS = re.compile(r"(?<![\w$\\>:])namespace(?:\s+\\?([A-Za-z_][\w\\]*))?\s*([{;])")
_USE = re.compile(r"(?<![\w$\\>:])use\s+(?=[\\A-Za-z_])")
_DECL = re.compile(r"(?<![\w$\\>:])(class|interface|trait|enum)\s+([A-Za-z_]\w*)")
_FN = re.compile(r"(?<![\w$\\>:])function\s*(?:&\s*)?([A-Za-z_]\w*)\s*\(")   # ⚠`\s*&?\s*` splits a blank run: quadratic
_TUSE = re.compile(r"(?<![\w$\\>:])use\s+([\\\w][\\\w\s,]{0,500})")   # greedy, no lookahead: terminator checked after
_NAME = re.compile(r"\\?[A-Za-z_][\w\\]*")
_PMODS = frozenset(("public", "protected", "private", "var", "static", "readonly"))


def _qend(s, j, q):
    """Index after the closing quote of a string whose body starts at s[j] (len(s) when unterminated)."""
    rx, n = _QRX[q], len(s)
    while True:
        x = rx.search(s, j)
        if not x:
            return n
        if x.group(0) == "\\":
            j = x.start() + 2
            continue
        return x.start() + 1


def _here_end(s, j, ident):
    """Heredoc body from s[j] -> (body end, index after the closing identifier). The closer may be indented (7.3+)."""
    n, k = len(s), len(ident)
    while True:
        p = s.find(ident, j)
        if p < 0:
            return n, n                    # ⚠unterminated heredoc blanks to the end
        q = p
        while q > j and s[q - 1] in " \t":
            q -= 1
        if (q == j or s[q - 1] == "\n") and not (s[p + k:p + k + 1].isalnum() or s[p + k:p + k + 1] == "_"):
            return q, p + k
        j = p + 1


def php_mask(src):
    """`src` with inline HTML, comments, string contents and heredoc bodies blanked (same length, newlines kept)."""
    s, n = src, len(src)
    out, a, i, html = [], 0, 0, True

    def cut(x, y):
        out.append(s[a:x])
        out.append(_blank(s[x:y]))
        return y
    while i < n:
        if html:                           # inline HTML up to and including the open tag
            o = _OPEN.search(s, i)
            a = i = cut(i, o.end() if o else n)
            html = False
            continue
        mt = _RUN.search(s, i)
        if not mt:
            break
        k, t = mt.start(), mt.group(0)
        c2 = s[k + 1:k + 2]
        if t == "?>":
            i, html = k + 2, True          # ⚠`?>` also ends a // or # comment
        elif t == "#" and c2 == "[":
            i = k + 2                      # attribute, not a comment
        elif t == "/" and c2 == "*":
            j = s.find("*/", k + 2)
            a = i = cut(k, n if j < 0 else j + 2)
        elif t == "#" or t == "/" and c2 == "/":
            j = s.find("\n", k)
            j = n if j < 0 else j
            q = s.find("?>", k, j)
            a = i = cut(k, q if q >= 0 else j)
        elif t == "/":
            i = k + 1
        elif t == "<<<":
            h = _HEREDOC.match(s, k)
            if not h:
                i = k + 1
                continue
            e, z = _here_end(s, h.end(), h.group(2))
            a = cut(h.end(), e)
            i = z
        else:
            e = _qend(s, k + 1, t)
            a = cut(k + 1, e - 1 if e > k + 1 and s[e - 1] == t else e)
            i = e
    out.append(s[a:])
    return "".join(out)


def _strip_attrs(t):
    return re.sub(r"#\[[^\[\]]{0,300}(?:\[[^\[\]]{0,300}\][^\[\]]{0,300})*\]", " ", t)


def _in_spans(spans, starts, i):
    k = bisect.bisect_right(starts, i) - 1
    return k >= 0 and spans[k][0] < i < spans[k][1]


def _supers(h):
    """Header after the name -> (extends names, implements names)."""
    ext, impl, mode = [], [], None
    for w in _NAME.finditer(h[:PHP_HEAD_MAX]):
        t = w.group(0)
        if t in ("extends", "implements"):
            mode = t
        elif mode:
            (ext if mode == "extends" else impl).append(t)
    return ext, impl


def _types(m, br, nss):
    out, budget = [], [PHP_FLAT_BUDGET]
    for d in _DECL.finditer(m):
        if len(out) >= PHP_DECLS_MAX:
            break
        name = d.group(2)
        if name in ("extends", "implements") or re.search(r"\bnew\s*$", m[max(0, d.start() - 12):d.start()]):
            continue                           # anonymous class
        lim = min(len(m), d.end() + PHP_HEAD_MAX)
        b = m.find("{", d.end(), lim)
        if b < 0 or ";" in m[d.end():b]:
            continue
        back = m[max(0, d.start() - 80):d.start()]
        cut = max(back.rfind(";"), back.rfind("{"), back.rfind("}"))
        ext, impl = _supers(m[d.end():b])
        close = br.get(b, -1)
        ns = next((nm for a, z, nm in reversed(nss) if a < d.start() < z), "")
        t = {"kind": d.group(1), "name": name, "at": d.start(), "head": d.start() - len(back) + cut + 1,
             "open": b, "close": close, "ext": ext, "impl": impl, "ns": ns, "flat": "",
             "mods": set(re.findall(r"[a-z]+", back[cut + 1:]))}
        if close > 0 and budget[0] > 0:
            t["flat"] = _flat(m, b + 1, close, br)
            budget[0] -= len(t["flat"])
        out.append(t)
    return out


def _fns(m, pr, br, flat, base, cls, out):
    """Named functions declared in a flattened region (methods of a class body, or top-level functions)."""
    for f in _FN.finditer(flat):
        p = base + f.end() - 1
        z = pr.get(p)
        if z is None:
            continue
        lim = min(len(m), z + 1 + 400)
        k = min([x for x in (m.find("{", z + 1, lim), m.find(";", z + 1, lim)) if x >= 0] or [-1])
        if k < 0:
            continue
        ret = m[z + 1:k].strip().lstrip(":").strip()
        out.append({"cls": cls, "name": f.group(1), "at": base + f.start(1), "hs": base + f.start(), "pa": p, "pz": z,
                    "ret": re.sub(r"\s+", " ", ret)[:120], "open": k if m[k] == "{" else -1,
                    "close": br.get(k, -1) if m[k] == "{" else -1})


def _props(flat):
    """Typed/untyped properties of a flattened class body -> [(name, type)]."""
    out = []
    for x in re.finditer(r"\$([A-Za-z_]\w*)", flat):
        w = flat[max(0, x.start() - 200):x.start()]
        toks = _strip_attrs(w[max(w.rfind(";"), w.rfind("{"), w.rfind("}")) + 1:]).split()
        if toks and toks[0] in _PMODS and all(t in _PMODS for t in toks[:-1]):
            out.append((x.group(1), "" if toks[-1] in _PMODS else toks[-1]))
    return out


def _use_items(txt):
    """Text after `use ` of one import statement -> [(fqcn, alias)]; function/const imports are skipped."""
    if re.match(r"(?:function|const)\b", txt):
        return []
    if "{" in txt:
        pre, _s, body = txt.partition("{")
        pre = pre.strip().rstrip("\\").strip()
        parts = [pre + "\\" + it.strip() for it in body.rsplit("}", 1)[0].split(",")
                 if it.strip() and not re.match(r"(?:function|const)\b", it.strip())]
    else:
        parts = [it.strip() for it in txt.split(",")]
    out = []
    for it in parts[:100]:
        bits = re.split(r"\s+as\s+", it.strip(), maxsplit=1, flags=re.I)
        fq = re.sub(r"\s+", "", bits[0]).lstrip("\\")
        if re.fullmatch(r"[A-Za-z_][\w\\]*", fq):
            al = bits[1].strip() if len(bits) > 1 else fq.rsplit("\\", 1)[-1]
            out.append((fq, al))
    return out


def _top_kept(m, br, bk, nss, types, fns, uses):
    """Masked text with declarations blanked (namespace/use/declare, types, top functions, attributes)."""
    spans = [(t["head"], t["close"] + 1 if t["close"] > 0 else t["open"] + 1) for t in types]
    spans += [(f["hs"], (f["close"] if f["close"] > 0 else f["pz"]) + 1) for f in fns]
    spans += [(a, z) for a, z in uses]
    spans += [(x.start(), x.end()) for x in re.finditer(r"(?<![\w$\\>:])namespace\b[^;{]{0,300}[;{]", m)]
    spans += [(x.start(), x.end()) for x in re.finditer(r"(?<![\w$>])declare\s*\([^()]{0,300}\)\s*;?", m)]
    for x in re.finditer(r"#\[", m):
        z = bk.get(x.start() + 1)
        if z is not None:
            spans.append((x.start(), z + 1))
    keep, k = [], 0
    for a, z in sorted(spans):
        if a > k:
            keep.append(m[k:a])
        k = max(k, z)
    keep.append(m[k:])
    return "".join(keep)


def php_parse(src):
    """Shared scan of one PHP file (memoized on the last source)."""
    s0, g0 = _last[0]
    if s0 is not None and s0 == src:
        return g0
    m = php_mask(src)
    br, pr, bk = _pairs(m, "{", "}"), _pairs(m, "(", ")"), _pairs(m, "[", "]")
    nss, cur = [], None
    for x in _NS.finditer(m):
        if len(nss) >= PHP_NS_MAX:
            break
        if cur is not None:
            nss[cur] = (nss[cur][0], x.start(), nss[cur][2])
            cur = None
        if x.group(2) == "{":
            nss.append((x.start(), br.get(x.end() - 1, len(m)), x.group(1) or ""))
        else:
            nss.append((x.start(), len(m), x.group(1) or ""))
            cur = len(nss) - 1
    types = _types(m, br, nss)
    spans = sorted((t["open"], t["close"] if t["close"] > 0 else len(m)) for t in types)
    starts = [a for a, _z in spans]
    imports, binds, ustm = [], {}, []
    for u in _USE.finditer(m):
        if len(ustm) >= 500 or _in_spans(spans, starts, u.start()):
            continue                           # trait use (class body) — read per class below
        e = m.find(";", u.end(), u.end() + 3000)
        if e < 0:
            continue
        ustm.append((u.start(), e + 1))
        for fq, al in _use_items(src[u.end():e]):
            imports.append(fq)
            binds[al] = fq
    meths = []
    for i, t in enumerate(types):
        if t["flat"]:
            _fns(m, pr, br, t["flat"], t["open"] + 1, i, meths)
            t["props"] = _props(t["flat"])
            t["traits"] = [n for u in _TUSE.finditer(t["flat"]) if t["flat"][u.end():u.end() + 1] in (";", "{")
                           for n in _NAME.findall(u.group(1))][:30]
    top = _flat(m, 0, len(m), br)
    for a, z, _nm in nss[:20]:                 # braced namespaces: their bodies are top level too
        if z < len(m) and m[z] == "}":
            o = m.find("{", a, z)
            top = top[:o + 1] + _flat(m, o + 1, z, br) + top[z:]
    tops = []
    _fns(m, pr, br, top, 0, -1, tops)
    kept = _top_kept(m, br, bk, nss, types, tops, ustm)
    module = bool(re.search(r"[^\s;]", kept.replace("?>", " ")))
    lines = [x.start() for x in re.finditer("\n", m)]
    got = {"m": m, "br": br, "pr": pr, "bk": bk, "ns": nss, "imports": imports, "binds": binds, "types": types,
           "meths": meths + tops, "module": module, "lines": lines, "spans": spans, "starts": starts,
           "tops": len(tops)}
    _last[0] = (src, got)                  # ⚠one tuple: a reader never sees one file's source with another's parse
    return got


_last = [(None, None)]


def php_scan(src):
    """Treemap cells: methods and top-level functions with a block body."""
    p = php_parse(src)
    out = []
    for x in p["meths"]:
        if x["open"] < 0 or x["close"] < 0:
            continue
        a, b = _ln(p, x["at"]), _ln(p, x["close"])
        if b - a + 1 > PHP_FN_LINES_MAX:
            continue
        cls = p["types"][x["cls"]]["name"] + "." if x["cls"] >= 0 else ""
        body = src[x["at"]:x["close"] + 1]
        out.append({"name": cls + x["name"], "lang": "php", "line": a, "lines": b - a + 1,
                    "h": hashlib.md5(body.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()[:12]})
    return out


lang_register("php", {"exts": (".php",), "scan": php_scan, "test": r"Test\.php$", "test_dirs": ("tests",),
                      "skip": ("vendor", "storage"), "gen": r"(?:^|/)bootstrap/cache/|\.blade\.php$"})
