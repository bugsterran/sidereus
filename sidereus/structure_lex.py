"""Lexical helpers shared by the structure_lang_* plug-ins (C#, PHP, Ruby).

⚠Not named structure_lang_*: structure_plug.plug_load imports every such file as a plug-in.
⚠Loaded while structure_scan is still importing: stdlib imports only.
"""
import bisect
import re


def _blank(t):
    return re.sub(r"[^\n]", " ", t)


def _pairs(m, o, c):
    """{open index: close index} for matched o/c over m, one pass."""
    st, out = [], {}
    for x in re.finditer(re.escape(o) + "|" + re.escape(c), m):
        if x.group(0) == o:
            st.append(x.start())
        elif st:
            out[st.pop()] = x.start()
    return out


def _flat(m, a, b, br):
    """m[a:b] with nested blocks blanked (their braces kept)."""
    out, k = [], a
    while k < b:
        p = m.find("{", k, b)
        z = br.get(p) if p >= 0 else None
        if z is None or z >= b:
            out.append(m[k:p + 1] + _blank(m[p + 1:b]) if p >= 0 else m[k:b])
            break
        out.append(m[k:p + 1] + _blank(m[p + 1:z]) + "}")
        k = z + 1
    return "".join(out)


def _degen(s):
    """Drop generic arguments `<...>` (nested)."""
    prev = None
    while prev != s:
        prev, s = s, re.sub(r"<[^<>]*>", "", s)
    return s


def _close(s, i, o="(", c=")"):
    """Index of the `c` matching the `o` at s[i], or -1."""
    d = 0
    for k in range(i, len(s)):
        d += (s[k] == o) - (s[k] == c)
        if d == 0:
            return k
    return -1


def _ln(p, i):
    return bisect.bisect_left(p["lines"], i) + 1
