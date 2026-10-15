"""CLI adapter contract (sidereus/adapter.py) over every registered adapter, on copies of tests/fixtures/adapters."""
import json
import os
import shutil
import socket
import tempfile
import types
import unittest
import urllib.request
from unittest import mock

from tests._load import sidereus

ad = sidereus("adapter")
st = sidereus("ext_store")      # importing it registers the adapters
gm = sidereus("plat_gemini")
cx = sidereus("plat_codex")
sidereus("state_v1")
from sidereus.state_v1 import load_schema, validate  # noqa: E402  (after the loader)

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "adapters")
FIX_DIR = {"gm": "gemini", "cx": "codex"}
CANARY = "CANARY-ADAPTER"
SMALL_MAX = 64 << 10


class _Home:
    """Fixture copy as the adapter's root(); one oversized record file added next to the real one."""

    def __init__(self, mod):
        self.mod = mod

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-adapter-")
        self.root = os.path.join(self.tmp, "home")
        shutil.copytree(os.path.join(FIX, FIX_DIR[self.mod.KEY]), self.root)
        self.files = []
        for d, _ds, fs in os.walk(self.root):
            self.files += [os.path.join(d, f) for f in fs if f.endswith(".jsonl")]
        src = self.files[0]
        with open(src, "rb") as f:
            lines = f.read().splitlines(True)
        # crafted noise: many text lines the readers must skip quickly
        noise = [json.dumps({"timestamp": "2026-10-05T01:00:09.000Z", "type": "response_item", "id": "n%d" % i,
                             "payload": {"type": "message", "text": CANARY + "-NOISE " + "x" * 200}}).encode() + b"\n"
                 for i in range(150)]
        with open(src, "wb") as f:
            f.write(b"".join(lines[:-1] + noise + lines[-1:]))
        big = os.path.join(os.path.dirname(src), os.path.basename(src).replace("-", "-big-", 1))
        with open(big, "wb") as f:
            f.write(b"".join(lines) + noise[0] * (SMALL_MAX // len(noise[0]) + 10))
        self.big = big
        self.p = [mock.patch.object(self.mod, "root", lambda: self.root),
                  mock.patch.object(self.mod, "SCAN_MAX", SMALL_MAX)]
        for p in self.p:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)


def _no_net(*a, **k):
    raise AssertionError("adapter touched the network")


class AdapterContract(unittest.TestCase):
    def test_registry(self):
        self.assertEqual(list(st.PLAT_MODS), ["gemini", "codex"])
        self.assertIs(st.PLAT_MODS["gemini"], gm)
        self.assertIs(st.PLAT_MODS["codex"], cx)
        for k, m in ad.ADAPTERS.items():
            self.assertIs(st.PLAT_MODS[m.PLAT], m)
            self.assertEqual(st.EXT_PLAT[m.PLAT], k)

    def test_required_keys(self):
        for m in ad.ADAPTERS.values():
            for k in ad.AD_REQUIRED:
                self.assertTrue(hasattr(m, k), "%s lacks %s" % (m.__name__, k))
            self.assertIsInstance(m.SCAN_MAX, int)

    def _rows(self, m, h, dt=0.5):
        clock = types.SimpleNamespace(monotonic=mock.Mock(side_effect=[0.0, dt]))   # fake clock, never the real one
        with mock.patch.object(socket, "socket", _no_net), mock.patch.object(urllib.request, "urlopen", _no_net), \
                mock.patch.object(ad, "time", clock):
            rows = ad.adapter_scan(m.KEY, 0.0)
            live = [m.session_msgs(p) for p in h.files] + [m.session_msgs(h.big)]
        return rows, live

    def test_scan_shape_no_text_fast_offline(self):
        for m in ad.ADAPTERS.values():
            with self.subTest(adapter=m.KEY), _Home(m) as h, mock.patch.object(ad, "warn_once") as w:
                rows, live = self._rows(m, h)
                w.assert_not_called()                       # no exception, within the time budget
                self.assertEqual(len(rows), 1)
                self.assertNotIn(h.big, [r["path"] for r in rows])     # over SCAN_MAX: skipped
                for r in rows:
                    for k in ad.AD_ROW_KEYS:
                        self.assertIn(k, r)
                    self.assertEqual(r["cwd"], "/tmp/demo-proj")
                    self.assertTrue(r["msgs"])
                    for v in r["msgs"].values():
                        self.assertEqual(len(v), 7)
                        self.assertTrue(all(isinstance(x, (int, float)) for x in v[:5]))
                        self.assertIsInstance(v[5], str)
                        self.assertTrue(v[6] is None or isinstance(v[6], float))
                    for t in r["acts"].values():
                        self.assertIsInstance(t, float)
                self.assertTrue(live[0])
                if m.KEY == "cx":
                    self.assertIsNone(live[-1])     # codex refuses big files; gemini tails them (TAIL_READ)
                self.assertNotIn(CANARY, json.dumps(rows, default=str))
                self.assertNotIn(CANARY, json.dumps(live, default=str))

    def test_slow_scan_warns_once(self):
        with _Home(gm) as h, mock.patch.object(ad, "warn_once") as w:
            rows, _live = self._rows(gm, h, dt=ad.AD_TIME_BUDGET_S + 1)
        self.assertEqual(len(rows), 1)                      # result kept, only a warning
        self.assertEqual(w.call_args[0][0], "adapter-slow-gm")

    def test_rows_conform_to_state_v1(self):
        v1, schema = sidereus("state_v1"), load_schema()
        for m in ad.ADAPTERS.values():
            with self.subTest(adapter=m.KEY), _Home(m):
                rows = ad.adapter_scan(m.KEY, 0.0)
                self.assertTrue(rows)
                sess = [v1._session({"sid": r["sid"], "id": r["sid"][:8], "plat": m.KEY, "project": r["project"],
                                     "cwd": r["cwd"], "kind": r["kind"], "state": "done",
                                     "model": max(r["msgs"].values(), key=lambda v: v[4])[5]}) for r in rows]
                obj = {"schema": "sidereus-state", "version": 1, "at": 0, "x": {}, "sessions": sess}
                self.assertEqual(validate(obj, schema), [])
                self.assertTrue(validate(dict(obj, sessions=[dict(sess[0], extra=1)]), schema))   # closed object

    def test_scan_exception_becomes_empty(self):
        bad = types.SimpleNamespace(KEY="zz", NAME="Bad", scan=mock.Mock(side_effect=RuntimeError("boom")))
        with mock.patch.dict(ad.ADAPTERS, {"zz": bad}), mock.patch.object(ad, "warn_once") as w:
            self.assertEqual(ad.adapter_scan("zz", 0.0), [])
            w.assert_called_once()
            self.assertNotIn("boom", str(w.call_args))
        self.assertEqual(ad.adapter_scan("nope", 0.0), [])

    def _fake(self, **kw):
        m = types.ModuleType("plat_fake")
        m.PLAT, m.KEY, m.NAME, m.CHILD_LABEL, m.SCAN_MAX = "fake", "fk", "Fake", "fake -p", 1 << 20
        m.root = lambda: "/nonexistent"
        m.path_ok = lambda p: False
        m.scan = lambda since=0.0: []
        m.session_msgs = lambda p: None
        for k, v in kw.items():
            if v is None:
                delattr(m, k)
            else:
                setattr(m, k, v)
        return m

    def test_register_rejects(self):
        with mock.patch.dict(ad.ADAPTERS):
            self.assertIs(ad.adapter_register(self._fake()), ad.ADAPTERS["fk"])
            for kw in ({"KEY": "gm"}, {"KEY": "cc"}, {"SCAN_MAX": None}, {"SCAN_MAX": "big"}, {"CHILD_LABEL": None}, {"scan": None},
                       {"NAME": ""}):
                with self.subTest(kw=kw), self.assertRaises(ValueError):
                    ad.adapter_register(self._fake(**kw))
            with self.assertRaises(ValueError):            # PLAT not in EXT_PLAT
                ad.adapter_register(self._fake(KEY="f2"), st.EXT_PLAT)
            self.assertIs(ad.adapter_register(gm, st.EXT_PLAT), gm)     # re-registering the same module is fine


if __name__ == "__main__":
    unittest.main()
