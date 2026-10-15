"""I18N.en is merged with Object.assign across web/js files concatenated in name order,
so a key defined twice silently takes the later file's translation for every caller.

Parses the repo's web/js/*.js (not live data) and fails on a key defined twice with different English.
"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPEN = re.compile(r"const I18N = \{ (?:en: \{\}, )?ko: \{|Object\.assign\(I18N\.(?:en|ko), \{")   # ko tables are keyed by English


def _tokens(src, i):
    """Yield (kind, value, pos) from src[i:] until the object literal opened just before i closes."""
    depth, n = 1, len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
        elif src.startswith("//", i):
            i = src.find("\n", i)
            i = n if i < 0 else i
        elif src.startswith("/*", i):
            i = src.index("*/", i) + 2
        elif c in "'\"`":
            j, buf = i + 1, []
            while src[j] != c:
                if src[j] == "\\":
                    e = src[j + 1]
                    buf.append(e if e in "'\"`\\" else src[j:j + 2]); j += 2
                else:
                    buf.append(src[j]); j += 1
            yield ("s", "".join(buf), i)
            i = j + 1
        elif c in "{[(":
            depth += 1; yield ("p", c, i); i += 1
        elif c in "}])":
            depth -= 1
            if depth == 0:
                return
            yield ("p", c, i); i += 1
        else:
            yield ("p", c, i); i += 1


def entries():
    """[(key, value, file, line)] for every top-level 'string': 'string' pair in I18N.en tables."""
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js"))):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for m in OPEN.finditer(src):
            toks = list(_tokens(src, m.end()))
            level = 0
            for k in range(len(toks)):
                kind, v, pos = toks[k]
                if kind == "p" and v in "{[(":
                    level += 1
                elif kind == "p" and v in "}])":
                    level -= 1
                if level or kind != "s" or k + 2 >= len(toks):
                    continue
                if toks[k + 1][:2] != ("p", ":") or (k and toks[k - 1][:2] != ("p", ",")):
                    continue
                # Value: a run of string literals joined with '+'; anything else is not a plain translation.
                j, val = k + 2, []
                while j < len(toks) and toks[j][0] == "s":
                    val.append(toks[j][1])
                    if j + 1 < len(toks) and toks[j + 1][:2] == ("p", "+"):
                        j += 2
                    else:
                        j += 1
                        break
                if val:
                    out.append((v, "".join(val), os.path.basename(path), src.count("\n", 0, pos) + 1))
    return out


class I18nDupes(unittest.TestCase):
    def test_parser_sees_tables(self):
        self.assertGreater(len(entries()), 500)

    def test_no_conflicting_duplicate_keys(self):
        seen, bad = {}, []
        for key, val, f, ln in entries():
            if key in seen and seen[key][0] != val:
                bad.append("%r: %s:%d %r vs %s:%d %r" % (key, seen[key][1], seen[key][2], seen[key][0], f, ln, val))
            seen.setdefault(key, (val, f, ln))
        self.assertEqual(bad, [], "\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
