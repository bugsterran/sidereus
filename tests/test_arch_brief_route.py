"""arch_map.brief_html + GET /api/arch/brief + /api/arch `brief` (arch-brief «Overview» link). Temp dirs only;
allow list, HEAD and the store dir patched on arch_map."""
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse, quote

from tests._load import sidereus

AM = sidereus("arch_map")
AV = sidereus("arch_verify")
RS = sidereus("routes_struct")
HEAD, OLD = "a" * 40, "b" * 40
HTML = b"<!doctype html><title>x</title><p>big picture</p>"
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-brief-"))
        self.repo = os.path.join(self.tmp, "repo")
        self.other = os.path.join(self.tmp, "other")
        os.makedirs(self.repo)
        os.makedirs(self.other)
        self.arch = os.path.join(self.tmp, "arch")
        roots = lambda p: (os.path.realpath(p) if p and os.path.realpath(p) == self.repo else "")
        self.p = [mock.patch.object(AM, "_struct_src_root", roots),
                  mock.patch.object(AM, "head_of", lambda r: HEAD),
                  mock.patch.object(AM, "ARCH_DIR", self.arch)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, commit, data=HTML, repo=None, ok=True):
        d = os.path.join(self.arch, AV.repo_key(repo or self.repo), commit)
        os.makedirs(d, exist_ok=True)
        fp = os.path.join(d, "brief.html")
        with open(fp, "wb") as f:
            f.write(data)
        if ok is True:
            ok = {"v": 1, "sha256": hashlib.sha256(data).hexdigest(), "commit": commit}
        if ok:
            with open(os.path.join(d, AV.BRIEF_OK), "w", encoding="utf-8") as f:
                json.dump(ok, f)
        return fp


class BriefHtml(Base):
    def test_ok_bytes(self):
        self.put(HEAD)
        self.assertEqual(AM.brief_html(self.repo, HEAD), HTML)

    def test_refusals(self):
        self.put(HEAD)
        for path, commit in ((self.repo, "../" + HEAD), (self.repo, "zz" * 20), (self.repo, HEAD[:7]), (self.repo, None),
                             (self.other, HEAD), ("/", HEAD), (self.repo, OLD)):   # bad id · outside allow list · missing file
            out = AM.brief_html(path, commit)
            self.assertIsInstance(out, dict, (path, commit))
            self.assertFalse(out["ok"])

    def test_symlinked_brief_refused(self):
        tgt = os.path.join(self.tmp, "elsewhere.html")
        with open(tgt, "wb") as f:
            f.write(HTML)
        d = os.path.join(self.arch, AV.repo_key(self.repo), HEAD)
        os.makedirs(d)
        os.symlink(tgt, os.path.join(d, "brief.html"))
        with open(os.path.join(d, AV.BRIEF_OK), "w", encoding="utf-8") as f:   # a valid marker: only the symlink refuses it
            json.dump({"v": 1, "sha256": hashlib.sha256(HTML).hexdigest(), "commit": HEAD}, f)
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)

    def test_symlinked_commit_dir_refused(self):
        real = os.path.join(self.tmp, "real")
        os.makedirs(real)
        with open(os.path.join(real, "brief.html"), "wb") as f:
            f.write(HTML)
        kd = os.path.join(self.arch, AV.repo_key(self.repo))
        os.makedirs(kd)
        os.symlink(real, os.path.join(kd, HEAD))
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)

    def test_gate_marker_required(self):
        self.put(HEAD, ok=False)   # no brief.ok.json: an agent-written page is never served
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)
        self.put(HEAD, ok={"v": 1, "sha256": "0" * 64, "commit": HEAD})   # page edited after the gate
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)
        self.put(HEAD, ok={"v": 1, "sha256": hashlib.sha256(HTML).hexdigest(), "commit": OLD})   # marker of another commit
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)
        self.assertIsNone(AM.load(self.repo)["brief"])
        self.put(HEAD)
        self.assertEqual(AM.brief_html(self.repo, HEAD), HTML)

    def test_symlinked_marker_refused(self):
        fp = self.put(HEAD)
        okp = os.path.join(os.path.dirname(fp), AV.BRIEF_OK)
        tgt = os.path.join(self.tmp, "ok.json")
        os.rename(okp, tgt)
        os.symlink(tgt, okp)
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)

    def test_symlinked_key_dir_refused(self):
        real = os.path.join(self.tmp, "realkey")
        self.put(HEAD)
        kd = os.path.join(self.arch, AV.repo_key(self.repo))
        os.rename(kd, real)
        os.symlink(real, kd)
        self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)
        self.assertIsNone(AM.load(self.repo)["brief"])

    def test_size_cap(self):
        self.put(HEAD, b"x" * 50)
        with mock.patch.object(AM, "BRIEF_MAX", 49):
            self.assertIsInstance(AM.brief_html(self.repo, HEAD), dict)
        with mock.patch.object(AM, "BRIEF_MAX", 50):
            self.assertEqual(AM.brief_html(self.repo, HEAD), b"x" * 50)


class LoadBrief(Base):
    def test_head_brief_only(self):
        self.assertIsNone(AM.load(self.repo)["brief"])
        self.put(OLD)   # no map at OLD: an older commit's brief alone is never offered
        self.assertIsNone(AM.load(self.repo)["brief"])
        fp = self.put(HEAD)
        self.assertEqual(AM.load(self.repo)["brief"], {"commit": HEAD, "file": fp})

    def test_older_map_offers_its_own_brief(self):
        """A shown older map (newest map commit != HEAD) offers that commit's gate-passed brief; HEAD's wins when both exist."""
        d = os.path.join(self.arch, AV.repo_key(self.repo), OLD)
        os.makedirs(d, exist_ok=True)
        for n in ("map.json", "verify.json"):
            open(os.path.join(d, n), "w", encoding="utf-8").close()
        with mock.patch.object(AM, "schema_errors", lambda m, r, c: []), \
                mock.patch.object(AM, "read_json", lambda p: {"v": 2, "edges": [], "modules": [], "groups": []}), \
                mock.patch.object(AM, "render_md", lambda m, v: ""), mock.patch.object(AM, "behind_of", lambda r, c: 4), \
                mock.patch.object(AM, "load_flows", lambda *a: []), mock.patch.object(AM, "load_checks", lambda *a: None), \
                mock.patch.object(AM, "_prov", lambda *a: None), mock.patch.object(AM, "_brief_bytes", lambda r, c: (c + ".html", b"x") if c in self.has else None):
            self.has = ()
            self.assertIsNone(AM.load(self.repo)["brief"])
            self.has = (OLD,)
            out = AM.load(self.repo)
            self.assertTrue(out["stale"])
            self.assertEqual(out["brief"], {"commit": OLD, "file": OLD + ".html"})
            self.has = (OLD, HEAD)
            self.assertEqual(AM.load(self.repo)["brief"]["commit"], HEAD)

    def test_symlinked_head_brief_not_offered(self):
        tgt = os.path.join(self.tmp, "t.html")
        with open(tgt, "wb") as f:
            f.write(HTML)
        d = os.path.join(self.arch, AV.repo_key(self.repo), HEAD)
        os.makedirs(d)
        os.symlink(tgt, os.path.join(d, "brief.html"))
        self.assertIsNone(AM.load(self.repo)["brief"])


class BriefRuns(Base):
    """brief_runs = state `briefRun`: tracked from [pl:arch-brief/…] tags, ended by the gate's brief.ok.json."""
    NOW = 1_000_000.0

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "sidereus")
        os.makedirs(os.path.join(self.home, ".claude", "pipelines"))
        with open(os.path.join(self.home, ".claude", "pipelines", "arch-brief.json"), "w", encoding="utf-8") as f:
            json.dump({"stages": [{"title": "draft"}, {"title": "gate"}]}, f)
        for p in (mock.patch.object(AM, "SIDEREUS_ROOT", self.home), mock.patch.object(AM, "_BRIEF_SEEN", {}),
                  mock.patch.object(AM, "_RUN_SEEN", {}), mock.patch.object(AM, "_REQ_SRC", None)):
            p.start()
            self.p.append(p)

    def row(self, **kw):
        return dict({"sid": "s1", "state": "think", "cwd": self.repo, "repos": [self.repo, self.home], "sub": []}, **kw)

    def test_live_then_ended_by_marker(self):
        n = self.NOW
        pr = [{"name": "arch-brief", "end": 0, "cur": "gate", "t0": n - 20, "t1": n + 6}]
        s = self.row(plrun=pr)
        self.assertEqual(AM.brief_runs([s], n + 10), {self.repo: {"stage": "gate", "n": 2, "of": 2, "t0": n - 20, "sid": "s1"}})
        self.assertEqual(AM.runs([s], n + 10), {})   # arch-map untouched
        fp = self.put(HEAD)
        okp = os.path.join(os.path.dirname(fp), AV.BRIEF_OK)
        os.utime(okp, (n + 20, n + 20))
        self.assertEqual(AM.result_at(AM.BRIEF_PL, self.repo), n + 20)
        self.assertEqual(AM.brief_runs([s], n + 30), {})

    def test_state_piece(self):
        st = __import__("tests._load", fromlist=["sidereus"]).sidereus("state")
        self.assertIs(st.brief_runs, AM.brief_runs)
        import inspect
        src = inspect.getsource(st)   # built once as _brun: plReq reuses it for the arch-brief request row
        self.assertIn('_brun = _piece("briefRun", brief_runs', src)
        self.assertIn('"briefRun": _brun', src)


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


class Ask(Base):
    """R2: /api/arch `ask` = {dir, commit, fmt} at HEAD with a finished map, None without (never an empty path)."""
    def setUp(self):
        super().setUp()
        for obj, k, v in ((AV, "ARCH_DIR", self.arch), (RS, "_struct_src_root", AM._struct_src_root),
                          (RS, "arch_load", lambda p: {"ok": True, "head": HEAD})):
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def put_map(self, commit=HEAD):
        m = {"v": 2, "repo": self.repo, "commit": commit, "groups": [{"id": "g", "name": "G"}],
             "modules": [{"id": "a", "name": "A", "path": "a", "kind": "module", "layer": "api", "group": "g"},
                         {"id": "b", "name": "B", "path": "b", "kind": "module", "layer": "service", "group": "g"}],
             "edges": [{"from": "a", "to": "b", "kind": "call", "label": "", "evidence": [{"file": "a/x.py", "line": 1, "symbol": "f"}]}]}
        self.assertEqual(AV.schema_errors(m, self.repo, commit), [])
        d = AV.store_dir(self.repo, commit)
        os.makedirs(d, exist_ok=True)
        for name, doc in (("map.json", m), ("verify.json", {"commit": commit, "edges": [{"i": 0, "ok": True}]})):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(doc, f)
        return d

    def ask(self, path=None):
        h = _Stub()
        h._g_arch(urlparse("/api/arch?path=%s" % quote(path or self.repo)))
        self.assertEqual(h.code, 200)
        return h.raw

    def test_r2_ask_at_head_with_map(self):
        d = self.put_map()
        a = self.ask()["ask"]
        self.assertEqual((a["dir"], a["commit"]), (d, HEAD))
        sb2, sal = sidereus("arch_brief_v2"), sidereus("arch_brief_layout")
        self.assertEqual(a["fmt"], sb2.FORMAT + sal.FORMAT)
        self.assertIn("brief.json v2", a["fmt"])
        self.assertIn("layout?", a["fmt"])

    def test_r2_no_map_is_none(self):
        self.assertIsNone(self.ask()["ask"])
        self.put_map(OLD)   # an older commit's map does not answer HEAD
        self.assertIsNone(self.ask()["ask"])

    def test_r2_no_head_is_none(self):
        self.put_map()
        with mock.patch.object(RS, "arch_load", lambda p: {"ok": True, "head": ""}):
            self.assertIsNone(self.ask()["ask"])

    def test_r2_symlinked_store_dir_refused(self):
        real = os.path.join(self.tmp, "real")
        with mock.patch.object(AV, "ARCH_DIR", real):
            d = self.put_map()
        kd = os.path.join(self.arch, AV.repo_key(self.repo))
        os.makedirs(kd)
        os.symlink(d, os.path.join(kd, HEAD))
        self.assertIsNone(self.ask()["ask"])

    def test_r2_failed_load_has_no_ask(self):
        with mock.patch.object(RS, "arch_load", lambda p: {"ok": False, "msg": "x"}):
            self.assertNotIn("ask", self.ask())


class Route(Base):
    def get(self, path, commit):
        h = _Stub()
        h._g_arch_brief(urlparse("/api/arch/brief?path=%s&commit=%s" % (quote(path), quote(commit))))
        return h

    def test_ok_headers(self):
        self.put(HEAD)
        h = self.get(self.repo, HEAD)
        hd = dict(h.headers_out)
        self.assertEqual(h.code, 200)
        self.assertEqual(hd["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(hd["Content-Security-Policy"], CSP)
        self.assertEqual(hd["Cache-Control"], "no-store")
        self.assertEqual(hd["Content-Length"], str(len(HTML)))
        self.assertEqual(hd["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h.wfile.getvalue(), HTML)

    def test_refusal_is_404_json(self):
        self.put(HEAD)
        for path, commit in ((self.repo, "nothex"), (self.other, HEAD), (self.repo, OLD)):
            h = self.get(path, commit)
            self.assertEqual(h.code, 404)
            self.assertFalse(h.raw["ok"])
            self.assertEqual(h.wfile.getvalue(), b"")

    def test_registered(self):
        cs = __import__("tests._load", fromlist=["load"]).load()
        self.assertIs(cs.Handler._GET_ROUTES["/api/arch/brief"], RS._StructRoutes._g_arch_brief)


if __name__ == "__main__":
    unittest.main()
