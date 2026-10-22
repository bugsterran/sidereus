"""Web app manifest + icons: same-origin routes, content types, PNG sizes, CSP unchanged, demo serves them."""
import io
import json
import struct
import unittest
from tests._load import load, sidereus

cs = load()
pg = sidereus("page")
rg = sidereus("routes_get")
feat = sidereus("features")
demo = sidereus("demo")

PATHS = {"/manifest.webmanifest": "application/manifest+json", "/icon.svg": "image/svg+xml",
         "/icon-192.png": "image/png", "/icon-512.png": "image/png"}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'self'; object-src 'none'")


class _U:
    def __init__(self, path):
        self.path = path
        self.query = ""


def _get(routes, path):
    h = cs.Handler.__new__(cs.Handler)
    sent = []
    h.headers = {}
    h.wfile = io.BytesIO()
    h.send_response = lambda code: sent.append(("code", code))
    h.send_header = lambda k, v: sent.append((k, v))
    h.end_headers = lambda: None
    routes[path](h, _U(path))
    return dict(sent), h.wfile.getvalue()


class PwaManifest(unittest.TestCase):
    def test_manifest_fields(self):
        m = json.loads(pg.MANIFEST.decode("utf-8"))
        self.assertEqual((m["name"], m["short_name"]), ("Sidereus", "Sidereus"))
        self.assertEqual((m["start_url"], m["scope"], m["display"]), ("/", "/", "standalone"))
        sizes = {i["sizes"]: i for i in m["icons"]}
        self.assertEqual(set(sizes), {"any", "192x192", "512x512"})
        for i in m["icons"]:
            self.assertIn(i["src"], cs.Handler._GET_ROUTES)

    def test_icon_bytes(self):
        self.assertTrue(pg.ICON_SVG.startswith(b"<svg"))
        for n, b in pg.ICON_PNG.items():
            self.assertEqual(b[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(b[12:16], b"IHDR")
            self.assertEqual(struct.unpack(">II", b[16:24]), (n, n))

    def test_routes_serve_types(self):
        for p, ctype in PATHS.items():
            hdr, body = _get(cs.Handler._GET_ROUTES, p)
            self.assertEqual(hdr["code"], 200, p)
            self.assertEqual(hdr["Content-Type"], ctype, p)
            self.assertEqual(hdr["Cache-Control"], "no-cache", p)
            self.assertEqual(hdr["X-Content-Type-Options"], "nosniff", p)
            self.assertEqual(body, pg.PWA_FILES[p][0], p)

    def test_page_links_manifest_and_csp_unchanged(self):
        self.assertIn("<link rel=manifest href=/manifest.webmanifest>", pg.PAGE)
        self.assertEqual(rg.PAGE_CSP, CSP)

    def test_core_routes(self):
        for p in PATHS:
            self.assertIsNone(feat.route_feature(p), p)

    def test_demo_serves_them(self):
        class H:
            _GET_ROUTES = dict(cs.Handler._GET_ROUTES)
            _POST_ROUTES = {}
        demo.install(H, "b")
        for p, ctype in PATHS.items():
            hdr, _ = _get(H._GET_ROUTES, p)
            self.assertEqual((hdr["code"], hdr["Content-Type"]), (200, ctype), p)


if __name__ == "__main__":
    unittest.main()
