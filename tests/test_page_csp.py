"""Page CSP: script-src is 'self' + sha256 hashes of the inline scripts (R1, R2); every other directive is unchanged (R4)."""
import base64
import gzip
import hashlib
import re
import unittest
from html.parser import HTMLParser
from tests._load import sidereus

rg = sidereus("routes_get")
pg = sidereus("page")

# The CSP before hashing; only script-src may differ from it (R4).
OLD_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
           "base-uri 'none'; form-action 'self'; object-src 'none'")


def _h(text):
    return "'sha256-%s'" % base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")


class _Scripts(HTMLParser):
    """Collects the text of each attribute-less <script> with the stdlib HTML parser (independent of page.py's regex)."""
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=False)
        self.bodies, self._cur = [], None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and not attrs:
            self._cur = []

    def handle_data(self, data):
        if self._cur is not None:
            self._cur.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._cur is not None:
            self.bodies.append("".join(self._cur))
            self._cur = None


def _directives(csp):
    return dict((d.split(" ", 1) + [""])[:2] for d in csp.split("; "))


def _served(accept):
    code, hdr, body = rg._page_reply(None, accept)
    h = dict(hdr)
    if h.get("Content-Encoding") == "gzip":
        body = gzip.decompress(body)
    return code, h["Content-Security-Policy"], body.decode("utf-8")


class PageCsp(unittest.TestCase):
    def test_r1_script_src_hashes_no_unsafe_inline(self):
        for accept in ("gzip", None):
            code, csp, _ = _served(accept)
            self.assertEqual(code, 200)
            src = _directives(csp)["script-src"].split(" ")
            self.assertEqual(src[0], "'self'")
            self.assertNotIn("'unsafe-inline'", src)
            self.assertEqual(len([s for s in src if s.startswith("'sha256-")]), 3, accept)
            self.assertEqual(len(src), 4, accept)

    def test_r2_every_served_inline_script_is_hashed(self):
        for accept in ("gzip", None):
            _, csp, body = _served(accept)
            src = _directives(csp)["script-src"].split(" ")
            p = _Scripts()
            p.feed(body.replace("\r\n", "\n").replace("\r", "\n"))
            p.close()
            self.assertEqual(len(p.bodies), 2, accept)
            for b in p.bodies:
                self.assertNotIn("<!--", b)   # would switch the HTML parser into script-escaped states
                self.assertIn(_h(b), src)

    def test_r2_issues_window_script_hashed(self):
        m = re.search(r'const ARCH_CW_JS = "([^"\\]*)";', pg.PAGE)
        self.assertIsNotNone(m)
        self.assertIn(_h(m.group(1)), _directives(rg.PAGE_CSP)["script-src"].split(" "))
        self.assertEqual(pg.PAGE_SCRIPT_HASHES[-1], _h(m.group(1)))

    def test_r2_hash_after_build_marker_replace(self):
        self.assertNotIn("__PAGE_BUILD__", pg.PAGE)

    def test_r2_crlf_hashes_like_lf(self):
        self.assertEqual(pg._csp_hash("a\r\nb\rc\n"), pg._csp_hash("a\nb\nc\n"))
        lf = "<script>x=1;\ny=2;</script><script>const ARCH_CW_JS = \"z\";</script>"
        self.assertEqual(pg._script_hashes(lf.replace("\n", "\r\n")), pg._script_hashes(lf))
        self.assertEqual(pg._script_hashes(lf), (_h("x=1;\ny=2;"), _h('const ARCH_CW_JS = "z";'), _h("z")))

    def test_r2_script_string_literal_not_counted(self):
        page = "<script src=/a.js></script><script>var s='<script>' + 'x' + '</' + 'script>';\nconst ARCH_CW_JS = \"q\";</script>"
        hs = pg._script_hashes(page)
        self.assertEqual(len(hs), 2)
        self.assertEqual(hs[0], _h("var s='<script>' + 'x' + '</' + 'script>';\nconst ARCH_CW_JS = \"q\";"))

    def test_r2_missing_or_escaped_popup_literal_raises(self):
        with self.assertRaises(RuntimeError):
            pg._script_hashes("<script>x</script>")
        with self.assertRaises(RuntimeError):
            pg._script_hashes('<script>const ARCH_CW_JS = "a\\"b";</script>')

    def test_r4_other_directives_unchanged(self):
        new, old = rg.PAGE_CSP.split("; "), OLD_CSP.split("; ")
        self.assertEqual(len(new), len(old))
        for n, o in zip(new, old):
            if o.startswith("script-src "):
                self.assertTrue(n.startswith("script-src 'self' "))
                continue
            self.assertEqual(n, o)


if __name__ == "__main__":
    unittest.main()
