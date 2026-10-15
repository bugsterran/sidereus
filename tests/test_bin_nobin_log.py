"""agent_view on a missing `claude` binary drops the cached path and says so (not «느립니다»);
tests never write to the live viewer.err."""
import contextlib
import io
import os
import unittest

from tests._load import ROOT, sidereus

lp = sidereus("live_probe")
ident = sidereus("ident")
warn = sidereus("warn")


class NoBinary(unittest.TestCase):
    def setUp(self):
        g = lp.agent_view.__globals__
        self.saved = {k: g[k] for k in ("warn_once", "subprocess")}
        self.cache = dict(ident._BIN_CACHE)
        self.av = list(lp._av_cache), list(lp._av_fail)
        self.warns = []
        g["warn_once"] = lambda key, msg, **kw: self.warns.append((key, msg))

        class _Sub:
            TimeoutExpired = lp.subprocess.TimeoutExpired

            @staticmethod
            def run(*a, **kw):
                raise FileNotFoundError(2, "No such file", a[0][0])
        g["subprocess"] = _Sub
        lp._av_fail[0] = 0.0

    def tearDown(self):
        lp.agent_view.__globals__.update(self.saved)
        ident._BIN_CACHE.clear()
        ident._BIN_CACHE.update(self.cache)
        lp._av_cache[:], lp._av_fail[:] = self.av
        lp._stale_clear("agents")

    def test_cache_dropped_and_message(self):
        ident._BIN_CACHE["claude"] = "/gone/claude"
        lp._av_cache[:] = [0.0, None]
        self.assertIsNone(lp.agent_view(ttl=0))
        self.assertNotIn("claude", ident._BIN_CACHE)
        self.assertEqual([k for k, _ in self.warns], ["agents-nobin"])
        self.assertIn("claude executable not found", self.warns[0][1])
        self.assertNotIn("slow", self.warns[0][1])

    def test_keeps_last_value_when_fresh(self):
        ident._BIN_CACHE["claude"] = "/gone/claude"
        prev = {"1": {"pid": 1}}
        lp._av_cache[:] = [lp.time.time() - 20, prev]
        self.assertIs(lp.agent_view(ttl=0), prev)
        self.assertNotIn("claude", ident._BIN_CACHE)


class LiveLogUntouched(unittest.TestCase):
    def test_warn_once_does_not_reach_viewer_err(self):
        live = os.path.join(ROOT, "viewer.err")
        if not os.path.exists(live):
            self.skipTest("no live viewer.err")
        # ⚠If this process's stderr were the live log (inherited from launchd), every warning in tests would land there.
        st = os.fstat(2)
        lv = os.stat(live)
        self.assertFalse((st.st_dev, st.st_ino) == (lv.st_dev, lv.st_ino), "test stderr is the live viewer.err")
        size = lv.st_size
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            warn.warn_once("test-live-log-probe", "테스트 경고", en="test warning")
        warn._warned.discard("test-live-log-probe")
        warn._WARN_LOG[:] = [w for w in warn._WARN_LOG if w.get("key") != "test-live-log-probe"]
        self.assertIn("test warning", buf.getvalue())
        # ⚠The running server appends too, so only a lower bound is safe: our line must not be in the growth.
        with open(live, "rb") as f:
            f.seek(size)
            self.assertNotIn(b"test warning", f.read())


if __name__ == "__main__":
    unittest.main()
