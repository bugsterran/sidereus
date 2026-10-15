"""structure_img + GET /api/structure/img: inline Markdown images (R1-R4). Temp dirs only; allow list, ~/.claude and git patched."""
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse

from tests._load import sidereus

T = sidereus("structure_tree")
RS = sidereus("routes_struct")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"/>'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-img-"))
        self.root = os.path.join(self.tmp, "proj")
        self.claude = os.path.join(self.tmp, "home", ".claude")
        os.makedirs(self.root)
        os.makedirs(self.claude)
        T._tree_cache.clear()
        self.allowed = {self.root}
        self.listing = None    # None = no .git, walk listing
        roots = lambda p: (os.path.realpath(p) if p and os.path.realpath(p) in self.allowed else "")
        self.p = [mock.patch.object(T, "_struct_src_root", roots),
                  mock.patch.object(T, "_claude_dirs", lambda: {self.claude}),
                  mock.patch.object(T, "_tree_git_ls", lambda r: self.listing)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        T._tree_cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, rel, data=PNG, base=None):
        fp = os.path.join(base or self.root, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(data)
        return fp

    def img(self, rel, root=None):
        T._tree_cache.clear()
        return T.structure_img(root or self.root, rel)


class ImgTest(Base):
    def test_png_bytes_and_mime(self):    # R1/R3
        self.put("docs/a.png")
        self.assertEqual(self.img("docs/a.png"), (PNG, "image/png"))
        self.put("b.JPG")
        self.assertEqual(self.img("b.JPG")[1], "image/jpeg")

    def test_svg_mime(self):    # R4
        self.put("d.svg", SVG)
        self.assertEqual(self.img("d.svg"), (SVG, "image/svg+xml"))

    def test_refusals(self):    # R2
        self.put("a.png")
        self.put("n.txt", b"hello")
        self.put(".env.png")
        outside = self.put("o.png", base=self.tmp)
        for rel in ("../o.png", "/etc/x.png", outside, "n.txt", ".env.png", "missing.png", ""):
            out = self.img(rel)
            self.assertIsInstance(out, dict, rel)
            self.assertFalse(out["ok"], rel)
        self.assertTrue(self.img(".env.png").get("locked"))

    def test_symlink_targets(self):    # R2: ext and secret checked on the realpath
        os.symlink(self.put("o.png", base=self.tmp), os.path.join(self.root, "out.png"))
        os.symlink(self.put("notes.txt", b"text"), os.path.join(self.root, "t.png"))
        os.symlink(self.put("sub/id_rsa", b"k"), os.path.join(self.root, "k.png"))
        os.symlink(self.claude, os.path.join(self.root, "cl.png"))
        for rel in ("out.png", "t.png", "k.png", "cl.png"):
            out = self.img(rel)
            self.assertIsInstance(out, dict, rel)
            self.assertFalse(out["ok"], rel)
        self.assertTrue(self.img("k.png").get("locked"))

    def test_not_in_git_listing(self):    # R2/R3
        os.makedirs(os.path.join(self.root, ".git"))
        self.put("a.png")
        self.put("ignored.png")
        self.listing = ["a.png"]
        self.assertEqual(self.img("a.png")[1], "image/png")
        self.assertFalse(self.img("ignored.png")["ok"])

    def test_root_not_allowed(self):    # R2
        other = os.path.join(self.tmp, "other")
        self.put("a.png", base=other)
        self.assertFalse(self.img("a.png", root=other)["ok"])

    def test_size_cap(self):    # R2/R3
        self.put("big.png", PNG + b"\x00" * 10)
        with mock.patch.object(T, "IMG_MAX_BYTES", len(PNG)):
            out = self.img("big.png")
        self.assertIsInstance(out, dict)
        self.assertTrue(out.get("big"))
        with mock.patch.object(T, "IMG_MAX_BYTES", len(PNG) + 10):
            self.assertIsInstance(self.img("big.png"), tuple)


class _Stub(RS._StructRoutes):
    def __init__(self):
        self.code, self.headers_out, self.wfile, self.raw = None, [], io.BytesIO(), None

    def send_response(self, code):
        self.code = code

    def send_header(self, k, v):
        self.headers_out.append((k, v))

    def end_headers(self):
        # Mirrors Handler.end_headers (chat_server.py): nosniff on every response.
        self.send_header("X-Content-Type-Options", "nosniff")

    def _raw_json(self, code, out, cache=True):
        self.code, self.raw = code, json.loads(json.dumps(out))


class RouteTest(Base):
    def get(self, rel):
        T._tree_cache.clear()
        h = _Stub()
        h._g_structure_img(urlparse("/api/structure/img?path=%s&file=%s" % (self.root, rel)))
        return h

    def test_ok_headers(self):    # R3/R4
        self.put("d.svg", SVG)
        h = self.get("d.svg")
        hd = dict(h.headers_out)
        self.assertEqual(h.code, 200)
        self.assertEqual(hd["Content-Type"], "image/svg+xml")
        self.assertEqual(hd["Content-Length"], str(len(SVG)))
        self.assertEqual(hd["Cache-Control"], "no-store")
        self.assertIn("default-src 'none'", hd["Content-Security-Policy"])
        self.assertIn("sandbox", hd["Content-Security-Policy"])
        self.assertEqual(hd["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h.wfile.getvalue(), SVG)

    def test_error_is_404_json(self):    # R2/R3
        self.put("n.txt", b"hello")
        h = self.get("n.txt")
        self.assertEqual(h.code, 404)
        self.assertFalse(h.raw["ok"])
        self.assertEqual(h.wfile.getvalue(), b"")

    def test_registered_and_nosniff_in_handler(self):    # R3
        cs = __import__("tests._load", fromlist=["load"]).load()
        self.assertIs(cs.Handler._GET_ROUTES["/api/structure/img"], RS._StructRoutes._g_structure_img)
        import inspect
        self.assertIn("nosniff", inspect.getsource(cs.Handler.end_headers))


if __name__ == "__main__":
    unittest.main()
