"""C/C++ masking and declaration-head helpers for sidereus/structure_lang_c.py (pure, linear in the input).

⚠Not named structure_lang_*: structure_plug.plug_load imports every such file as a plug-in.
⚠Loaded while structure_scan is still importing: stdlib imports only.
"""
import re

C_HEAD_MAX = 600               # chars of a declaration head looked at (its tail)
C_TMPL_MAX = 200               # chars a template<...> parameter list may span before it is left alone

_TOK = re.compile(r'//|/\*|"|\'|\n|#')
_INC = re.compile(r'\s*#\s*include\s*([<"])([^<>"\n]{1,300})[>"]')
_DIR = re.compile(r"\s*#\s*(\w*)(.*)$", re.S)
_STR_BODY = {q: re.compile(r"(?:[^%s\\\n]|\\.)*" % q, re.S) for q in "\"'"}


def _blank(s):
    return s if not s else (" " * len(s) if "\n" not in s else re.sub(r"[^\n]", " ", s))


def _line_end(src, i):
    """End of the logical line starting before `i` (backslash-newline continues it)."""
    while True:
        j = src.find("\n", i)
        if j < 0 or not src[max(0, j - 2):j].rstrip("\r").endswith("\\"):
            return len(src) if j < 0 else j
        i = j + 1


def _directive(src, i, j, conds):
    """Update the #if stack for the directive src[i:j]; -> (spec kind, spec) for #include, else None.
    conds entries: 1 = branch active, 0 = `#if 0` branch (an #else/#elif may enable), 2 = done (rest skipped)."""
    d = _DIR.match(src, i, j)
    word = d.group(1) if d else ""
    expr = re.sub(r"/\*.*?\*/|//.*", "", (d.group(2) if d else "")[:C_HEAD_MAX]).strip()   # ⚠cut: unclosed /* rescans
    if word in ("if", "ifdef", "ifndef"):
        conds.append(0 if word == "if" and expr in ("0", "false") else 1)
    elif word in ("elif", "else", "elifdef", "elifndef") and conds:     # ⚠first branch only: braces stay balanced
        conds[-1] = (0 if word == "elif" and expr in ("0", "false") else 1) if conds[-1] == 0 else 2
    elif word == "endif" and conds:
        conds.pop()
    elif word == "include":
        m = _INC.match(src, i, j)
        if m:
            return m.group(1), m.group(2).strip()
    return None


def c_mask(src):
    """-> (masked text, [(kind '<' or '"', spec, line)]). Comments, strings, raw strings, char literals, directives
    (with continuations) and inactive #if branches become spaces; length and newlines are kept."""
    out, incs, conds = [], [], []
    n, i, at, line, bol, bad = len(src), 0, 0, 1, True, 0

    def emit(a, b, keep):
        out.append(src[a:b] if keep and not bad else _blank(src[a:b]))
    while True:
        m = _TOK.search(src, i)
        if not m:
            emit(at, n, True)
            break
        k, t = m.start(), m.group(0)
        if bol and src[i:k].strip():
            bol = False                        # ⚠slice from the last search point only: `a#a#a…` stays linear
        if t == "\n":
            emit(at, k + 1, True)
            line, bol, i, at = line + 1, True, k + 1, k + 1
            continue
        if t == "#":
            if not bol:
                i = k + 1
                continue
            emit(at, k, True)
            j = _line_end(src, k)
            n0, t0 = len(conds), (conds[-1] if conds else 1)
            got = _directive(src, k, j, conds)
            t1 = conds[-1] if conds else 1
            bad += (t1 != 1) if len(conds) > n0 else -(t0 != 1) if len(conds) < n0 else (t1 != 1) - (t0 != 1)
            if got and not bad:
                incs.append((got[0], got[1], line))
            out.append(_blank(src[k:j]))
            line += src.count("\n", k, j)
            i = at = j
            continue
        bol = False
        emit(at, k, True)
        if t == "//":
            j = _line_end(src, k)
        elif t == "/*":
            j = src.find("*/", k + 2)
            j = n if j < 0 else j + 2
        elif t == "'" and k > 0 and (src[k - 1].isalnum() or src[k - 1] == "_") and not _chr_prefix(src, k):
            emit(k, k + 1, True)               # digit separator (1'000)
            i = at = k + 1
            continue
        else:
            j = _str_end(src, k, t)
            out.append(src[k] if not bad else " ")
            out.append(_blank(src[k + 1:j - 1]))
            out.append((src[j - 1] if not bad else " ") if j - 1 > k else "")
            line += src.count("\n", k, j)
            i = at = j
            continue
        out.append(_blank(src[k:j]))
        line += src.count("\n", k, j)
        i = at = j
    return "".join(out), incs


def _chr_prefix(src, k):
    """`L'x'` / `u'x'` / `U'x'` / `u8'x'` (a char literal, not a digit separator)."""
    a = k - 2 if src[k - 2:k] == "u8" else k - 1
    return src[a:k] in ("L", "u", "U", "u8") and (a == 0 or not (src[a - 1].isalnum() or src[a - 1] == "_"))


def _str_end(src, k, q):
    """Index after the literal opening at src[k] (unterminated: end of line; raw: end of file)."""
    n = len(src)
    if q == '"' and k > 0 and src[k - 1] == "R" and (k < 2 or not (src[k - 2].isalnum() or src[k - 2] == "_")
                                                     or src[max(0, k - 3):k - 1] in ("u8", "u", "U", "L")):
        p = src.find("(", k + 1, k + 18)
        if p > 0 and not re.search(r"[\s\\)]", src[k + 1:p]):
            j = src.find(")" + src[k + 1:p] + '"', p + 1)
            return n if j < 0 else j + p - k + 1
    j = _STR_BODY[q].match(src, k + 1).end()
    return j + 1 if j < n and src[j] == q else j


def _skip_tmpl(h):
    """Drop leading `template<...>` lists (each within C_TMPL_MAX chars); a longer one is left as is."""
    while True:
        m = re.match(r"\s*template\s*<", h)
        if not m:
            return h
        d, k, lim = 1, m.end(), min(len(h), m.end() + C_TMPL_MAX)
        while k < lim and d:
            d += (h[k] == "<") - (h[k] == ">")
            k += 1
        if d:
            return h
        h = h[k:]


def _close_paren(h, p):
    d = 0
    for k in range(p, len(h)):
        d += (h[k] == "(") - (h[k] == ")")
        if d == 0:
            return k
    return -1


def _qual_back(s):
    """Qualified name at the end of `s` read backwards -> (segments, start) or None. Linear (no regex backtracking)."""
    k, segs = len(s.rstrip()), []
    while True:
        e = k
        while k > 0 and (s[k - 1].isalnum() or s[k - 1] in "_@"):
            k -= 1
        if k == e:
            return None
        seg = s[k:e]
        if k > 0 and s[k - 1] == "~":
            k -= 1
            seg = "~" + seg
        if seg[0].isdigit():
            return None
        segs.insert(0, seg.replace("@", ""))
        j = len(s[:k].rstrip())
        if j >= 2 and s[j - 2:j] == "::":
            j = len(s[:j - 2].rstrip())
            if j > 0 and s[j - 1] == ">":
                t = s.rfind("<", max(0, j - C_TMPL_MAX), j)
                if t < 0:
                    return None
                j = t
            k = j
            continue
        return segs, k
