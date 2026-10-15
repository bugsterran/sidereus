"""Usage-index readers iterate a snapshot of the hour buckets, not the live dicts a concurrent scan mutates."""
import unittest

from tests._load import sidereus, load

load()
U = sidereus("usage_index")
PC = sidereus("projcost")
H = sidereus("history")

FP = "/p/-slug/sid1.jsonl"


def _live():
    return {str(3600 * (10 ** 5 + k)): {"m": [10, 0, 0, 0]} for k in range(3)}


class UidxSnapshot(unittest.TestCase):
    def setUp(self):
        self.saved = dict(U._uidx["files"])
        self.live = _live()
        U._uidx["files"].clear()
        U._uidx["files"][FP] = {"h": self.live, "sl": "-slug", "mt": 1.0}
        self.n = 0

    def tearDown(self):
        U._uidx["files"].clear()
        U._uidx["files"].update(self.saved)

    def _scan(self):
        # What `_uidx_scan` does on another thread: open a new hour bucket and add a model to an old one.
        self.n += 1
        self.live[str(10 ** 9 + self.n)] = {"m": [1, 0, 0, 0]}
        next(iter(self.live.values()))["m%d" % self.n] = [1, 0, 0, 0]

    def _cost(self, mdl, v):
        self._scan()
        return 0.0

    def _patch(self, mod, **kw):
        old = {k: getattr(mod, k) for k in kw}
        for k, v in kw.items():
            setattr(mod, k, v)
        self.addCleanup(lambda: [setattr(mod, k, v) for k, v in old.items()])

    def test_snap(self):
        snap = U._uidx_snap(self.live)
        self._scan()
        self.assertEqual(len(snap), 3)
        self.assertEqual(list(snap["360000000"]), ["m"])
        self.assertEqual(U._uidx_snap(None), {})
        self.assertEqual(U._uidx_snap({"1": "bad"}), {"1": "bad"})

    def test_projcost_local(self):
        self._patch(PC, _uidx_refresh=lambda *a, **k: (0, 0), _cost4=self._cost)
        PC._projcost_local()
        self.assertEqual(self.n, 3)

    def test_history(self):
        self._patch(H, _uidx_refresh=lambda *a, **k: (0, 0), _cost4=self._cost, PLAT_MODS={},
                    _cwd_from_slug=lambda s: "", _cwd_probe=lambda s: "")
        H._hist_cache.clear()
        self.addCleanup(H._hist_cache.clear)
        now = int(H.time.time()) // 3600 * 3600      # history clamps days to HIST_MAX_DAYS ⇒ use recent buckets
        for i, k in enumerate(list(self.live)):
            self.live[str(now - 3600 * i)] = self.live.pop(k)
        out = H.history(days=1)
        self.assertGreater(self.n, 0)
        self.assertEqual(sum(d["tok"] for d in out["list"]), self.n * 10)

    def test_uidx_projects(self):
        self._patch(U, _uidx_refresh=lambda *a, **k: (0, 0), _cost4=self._cost)
        U._uidx_projects(36500)
        self.assertEqual(self.n, 3)

    def test_uidx_hours(self):
        t = self

        class V(list):
            def __iter__(self):          # `list(v)` inside the fold triggers the concurrent scan
                t._scan()
                return list.__iter__(self)

        for mm in self.live.values():
            mm["m"] = V(mm["m"])
        out = U._uidx_hours()
        self.assertEqual(len(out), 3)
        self.assertEqual(sum(v[0] for mm in out.values() for v in mm.values()), 30)


if __name__ == "__main__":
    unittest.main()
