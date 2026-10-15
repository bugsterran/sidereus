"""Comments in web/ carry no Hangul (open-source audience); Korean stays only in string literals (UI text).

Scans web/js/*.js, web/app-head.js, web/css/*.css and the HTML comments of web/index.html.
Reads repo source files only. ⚠Literals are skipped by a small tokenizer (strings, templates with
${...} nesting, regex literals by the previous-token rule) — a comment marker inside a literal is not a comment.
"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")
# A '/' after one of these (or at the start) opens a regex literal, otherwise it is division.
_RX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_RX_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield", "await"}


def js_comments(src):
    """[(line, text)] for every // and /* */ comment in JS source, literals skipped."""
    out, i, n = [], 0, len(src)
    stack = []          # template nesting: brace depth per open ${
    prev = ""           # last significant char (or word) outside comments
    def line(at):
        return src.count("\n", 0, at) + 1
    while i < n:
        c = src[i]
        if stack and c == "}" and stack[-1] == 0:
            stack.pop()
            i = _template(src, i + 1, stack)
            prev = "`"
            continue
        if c == "/" and src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append((line(i), src[i:j]))
            i = j
            continue
        if c == "/" and src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append((line(i), src[i:j]))
            i = j
            continue
        if c in "'\"":
            i = _quoted(src, i + 1, c)
            prev = c
            continue
        if c == "`":
            i = _template(src, i + 1, stack)
            prev = "`"
            continue
        if c == "/" and (prev == "" or prev in _RX_PREV or prev in _RX_WORDS):
            i = _regex(src, i + 1)
            prev = "/"
            continue
        if c.isspace():
            i += 1
            continue
        if c.isalnum() or c in "_$":
            j = i
            while j < n and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            prev = src[i:j]
            i = j
            continue
        if stack:
            if c == "{":
                stack[-1] += 1
            elif c == "}":
                stack[-1] -= 1
        prev = c
        i += 1
    return out


def _quoted(src, i, q):
    n = len(src)
    while i < n and src[i] != q and src[i] != "\n":
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _template(src, i, stack):
    """Skip template text from i; stops after the closing ` or after a ${ (pushing a depth)."""
    n = len(src)
    while i < n:
        if src[i] == "\\":
            i += 2
            continue
        if src[i] == "`":
            return i + 1
        if src.startswith("${", i):
            stack.append(0)
            return i + 2
        i += 1
    return n


def _regex(src, i):
    n, cls = len(src), False
    while i < n and src[i] != "\n":
        ch = src[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "[":
            cls = True
        elif ch == "]":
            cls = False
        elif ch == "/" and not cls:
            return i + 1
        i += 1
    return i


def css_comments(src):
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"":
            i = _quoted(src, i + 1, c)
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append((src.count("\n", 0, i) + 1, src[i:j]))
            i = j
        else:
            i += 1
    return out


def html_comments(src):
    return [(src.count("\n", 0, m.start()) + 1, m.group(0)) for m in re.finditer(r"<!--.*?-->", src, re.S)]


def hits(path, finder):
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    rel = os.path.relpath(path, ROOT)
    return ["%s:%d: %s" % (rel, ln, txt.strip()[:120]) for ln, txt in finder(src) if HANGUL.search(txt)]


class TestNoHangulComments(unittest.TestCase):
    def test_tokenizer_skips_literals(self):
        src = "a = '// 가'; b = `x ${ {k: '/* 나 */'} } // 다`; c = /\\/\\/ 라/; d = e / f; // ok\n/* 마 */"
        self.assertEqual([t for _, t in js_comments(src)], ["// ok", "/* 마 */"])

    def test_web_comments_have_no_hangul(self):
        bad = []
        js = sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js"))) + [os.path.join(ROOT, "web", "app-head.js")]
        for p in js:
            bad += hits(p, js_comments)
        for p in sorted(glob.glob(os.path.join(ROOT, "web", "css", "*.css"))):
            bad += hits(p, css_comments)
        bad += hits(os.path.join(ROOT, "web", "index.html"), html_comments)
        self.assertEqual(bad, [], "Hangul in web/ comments (write them in English):\n" + "\n".join(bad[:40]))


if __name__ == "__main__":
    unittest.main()
