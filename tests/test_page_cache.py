"""sidereus/routes_get._page_reply — the static PAGE is gzip-served with an ETag and answers 304 on a match."""
import gzip
import unittest
from tests._load import sidereus

rg = sidereus("routes_get")
pg = sidereus("page")


class PageReply(unittest.TestCase):
    def test_plain_200_same_bytes(self):
        code, hdr, body = rg._page_reply(None, None)
        h = dict(hdr)
        self.assertEqual(code, 200)
        self.assertEqual(body, pg.PAGE.encode("utf-8"))
        self.assertNotIn("Content-Encoding", h)
        self.assertEqual(h["ETag"], '"%s"' % pg.PAGE_BUILD)
        self.assertEqual(h["Cache-Control"], "no-cache")

    def test_gzip_roundtrip_and_distinct_tag(self):
        code, hdr, body = rg._page_reply(None, "gzip, deflate, br")
        h = dict(hdr)
        self.assertEqual((code, h["Content-Encoding"]), (200, "gzip"))
        self.assertEqual(gzip.decompress(body), pg.PAGE.encode("utf-8"))
        self.assertLess(len(body), len(pg.PAGE.encode("utf-8")) // 2)
        self.assertEqual(h["ETag"], '"%s-gz"' % pg.PAGE_BUILD)

    def test_304_on_match_weak_or_list(self):
        for inm, ae in (('"%s-gz"' % pg.PAGE_BUILD, "gzip"),
                        ('W/"%s"' % pg.PAGE_BUILD, ""),
                        ('"old", "%s"' % pg.PAGE_BUILD, None)):
            code, hdr, body = rg._page_reply(inm, ae)
            self.assertEqual((code, body), (304, b""), inm)
            self.assertIn("ETag", dict(hdr))

    def test_anti_framing_headers_on_200_and_304(self):
        for inm in (None, '"%s"' % pg.PAGE_BUILD):
            h = dict(rg._page_reply(inm, "")[1])
            self.assertEqual(h["X-Frame-Options"], "DENY")
            self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
            self.assertIn("connect-src 'self'", h["Content-Security-Policy"])

    def test_other_build_or_encoding_is_200(self):
        self.assertEqual(rg._page_reply('"deadbeef0000"', "gzip")[0], 200)
        # plain tag does not validate the gzip representation
        self.assertEqual(rg._page_reply('"%s"' % pg.PAGE_BUILD, "gzip")[0], 200)


if __name__ == "__main__":
    unittest.main()
