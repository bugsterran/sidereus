"""boot_time caches a failed read too: a failing sysctl runs once, not on every call."""
import unittest

from tests._load import load, sidereus

load()
ag = sidereus("agents")


class BootTimeCache(unittest.TestCase):
    def test_failure_is_cached(self):
        saved = (ag._BOOT[0], ag.IS_MAC, ag.subprocess.run)
        calls = []

        def boom(*a, **k):
            calls.append(a)
            raise OSError("no sysctl")

        try:
            ag._BOOT[0] = None
            ag.IS_MAC = True
            ag.subprocess.run = boom
            self.assertEqual(ag.boot_time(), 0.0)
            self.assertEqual(ag.boot_time(), 0.0)
            self.assertEqual(len(calls), 1)
        finally:
            ag._BOOT[0], ag.IS_MAC, ag.subprocess.run = saved


if __name__ == "__main__":
    unittest.main()
