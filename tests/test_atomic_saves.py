"""Concurrent cache/log writes stay parseable (usage-cache, qb-lim-cache, quota-log trim).

All paths point into a temp dir; no live file is touched and no loop thread starts.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest

from tests import _load

u = _load.sidereus("usage")
b = _load.sidereus("burn")
q = _load.sidereus("quota")
bus = _load.sidereus("bus")


def _hammer(fn, n=16, rounds=20):
    """Run `fn(i)` from n threads at once, `rounds` times each."""
    go = threading.Event()

    def run(i):
        go.wait()
        for r in range(rounds):
            fn(i * rounds + r)
    ts = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    go.set()
    for t in ts:
        t.join()


class AtomicSaves(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sidereus-atomic-")
        self.saved = []

    def tearDown(self):
        for mod, k, v in reversed(self.saved):
            setattr(mod, k, v)
        shutil.rmtree(self.d, ignore_errors=True)

    def patch(self, mod, **kw):
        for k, v in kw.items():
            self.saved.append((mod, k, getattr(mod, k)))
            setattr(mod, k, v)

    def leftovers(self, keep):
        return [f for f in os.listdir(self.d) if f != keep]

    def test_usage_save_concurrent_valid(self):
        path = os.path.join(self.d, "usage-cache.json")
        self.patch(u, USAGE_CACHE=path)
        old = dict(u._usage)
        self.addCleanup(lambda: (u._usage.clear(), u._usage.update(old)))

        def save(i):
            with u._usage_lock:
                # alternate long/short payloads — a non-atomic "w" would leave the long tail behind
                u._usage["spark"] = [[i, j] for j in range(200 if i % 2 else 1)]
                u._usage["blockMax"] = i
            u._usage_save()
        _hammer(save)
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.assertIn("spark", d)
        self.assertEqual(self.leftovers("usage-cache.json"), [])

    def test_qb_lim_set_unique_tmp_and_valid(self):
        path = os.path.join(self.d, "qb-lim-cache.json")
        self.patch(b, QB_LIM_CACHE=path, _cc_account=lambda: "acct")
        self.addCleanup(lambda old=dict(b._qb_lim): (b._qb_lim.clear(), b._qb_lim.update(old)))   # ⚠stamp leaks otherwise
        names, real = [], bus.tempfile.mkstemp
        lock = threading.Lock()

        def rec(*a, **kw):
            r = real(*a, **kw)
            with lock:
                names.append(r[1])
            return r
        self.patch(bus.tempfile, mkstemp=rec)
        _hammer(lambda i: b._qb_lim_set(1000 + i, 1_800_000_000 + i))
        self.assertEqual(len(names), 16 * 20)
        self.assertEqual(len(set(names)), len(names))
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual(d["acct"], "acct")
        self.assertEqual(self.leftovers("qb-lim-cache.json"), [])

    def test_quota_log_trim_atomic_keeps_appends(self):
        path = os.path.join(self.d, "quota-log.jsonl")
        row = json.dumps({"t": 1, "at": 1, "src": "x", "h5": 1, "d7": 1, "reset5": "old"})
        with open(path, "w", encoding="utf-8") as f:
            f.write((row + "\n") * (400_000 // len(row) + 50))
        self.patch(q, QUOTA_LOG=path, _qlog_last=[None], _cc_account=lambda: "acct")

        def log(i):
            q._quota_log({"five_hour": {"pct": i, "resets_at": "r%d" % i},
                          "seven_day": {"pct": 0}}, 0, "t")
        _hammer(log, n=8, rounds=40)
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(ln) for ln in f.read().splitlines()]
        got = {r["h5"] for r in rows if r["reset5"] != "old"}
        self.assertEqual(got, set(range(8 * 40)))
        self.assertEqual(self.leftovers("quota-log.jsonl"), [])

    def test_quota_save_concurrent_valid_same_format(self):
        path = os.path.join(self.d, "quota-cache.json")
        self.patch(q, QUOTA_CACHE=path, _cc_account=lambda: "acct", _quota_log=lambda *a: None)
        old = dict(q._quota)
        self.addCleanup(lambda: (q._quota.clear(), q._quota.update(old)))

        def save(i):
            with q._quota_lock:
                # alternate long/short payloads — a non-atomic "w" would leave the long tail behind
                q._quota["data"] = {"five_hour": {"pct": i, "pad": "x" * (400 if i % 2 else 1)}}
                q._quota["at"] = i
            q._quota_save()
        _hammer(save)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        d = json.loads(raw)
        # format unchanged from the old json.dump(..., ensure_ascii=False): default separators, no newline
        self.assertEqual(raw, json.dumps({"data": d["data"], "at": d["at"], "acct": "acct"}, ensure_ascii=False))
        self.assertEqual(self.leftovers("quota-cache.json"), [])

    def test_quota_calibrate_uses_atomic_write(self):
        # ⚠The ANCHOR_FILE write sits behind the disabled `return` in _quota_calibrate, so it cannot run;
        #   pin only that the name is the shared helper (a revival then writes atomically).
        ql = _load.sidereus("quota_loop")
        self.assertIs(ql._atomic_write, bus._atomic_write)

    def test_saver_write_bytes_and_tmp_name(self):
        sv = _load.sidereus("saver")
        path = os.path.join(self.d, ".saver-force.json")
        seen, real = [], os.replace

        def rec(src, dst):
            seen.append((src, dst))
            return real(src, dst)
        self.patch(bus.os, replace=rec)
        sv._saver_write(path, {"mode": "on", "stage": 2, "note": "한"})
        with open(path, "rb") as f:
            self.assertEqual(f.read(), '{"mode":"on","stage":2,"note":"한"}\n'.encode("utf-8"))
        self.assertEqual(seen, [("%s.tmp.%d.%d" % (path, os.getpid(), threading.get_ident()), path)])
        self.assertEqual(self.leftovers(".saver-force.json"), [])

    def _fail_replace(self):
        def boom(src, dst):
            raise OSError("replace failed")
        self.patch(bus.os, replace=boom)

    def test_atomic_write_mode_and_like(self):
        p = os.path.join(self.d, "f.json")
        bus._atomic_write(p, b"1")
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
        bus._atomic_write(p, b"2", mode=0o644)
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o644)
        os.chmod(p, 0o640)
        bus._atomic_write(p, b"3", mode=0o644, like=p)    # like wins when the file exists
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o640)
        self.assertEqual(self.leftovers("f.json"), [])

    def test_prefs_write_keeps_mode_no_tmp(self):
        pr = _load.sidereus("prefs")
        p = os.path.join(self.d, "sub", "config.local.json")
        self.patch(pr, CONFIG_PATH=p)
        pr._write({"a": 1})
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o644)
        os.chmod(p, 0o640)
        pr._write({"a": 2})
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o640)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"a": 2})
        self.assertEqual(sorted(os.listdir(os.path.dirname(p))), ["config.local.json", "config.local.json.bak"])
        self._fail_replace()
        with self.assertRaises(OSError):
            pr._write({"a": 3})
        self.assertEqual(sorted(os.listdir(os.path.dirname(p))), ["config.local.json", "config.local.json.bak"])

    def test_arch_verify_write_unique_tmp_no_leftover(self):
        av = _load.sidereus("arch_verify")
        self.assertIs(av._atomic_write, bus._atomic_write)
        p = os.path.join(self.d, "verify.json")
        av._write(p, "{}\n")
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o644)
        self._fail_replace()
        with self.assertRaises(OSError):
            av._write(p, "{\"x\": 1}\n")
        self.assertEqual(self.leftovers("verify.json"), [])

    def test_pipeline_save_uses_atomic_write(self):
        pl = _load.sidereus("pipeline")
        self.assertIs(pl._atomic_write, bus._atomic_write)


if __name__ == "__main__":
    unittest.main()
