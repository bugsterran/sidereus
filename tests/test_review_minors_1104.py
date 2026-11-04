"""transcript._user_text tolerates a non-str text block; memo.serve_last surfaces a failing background refresh."""
import unittest
from unittest import mock

from tests._load import sidereus

tr = sidereus("transcript")
memo = sidereus("memo")


class UserTextTest(unittest.TestCase):
    def test_non_str_text_block_is_skipped(self):
        d = {"message": {"content": [{"type": "text", "text": {"x": 1}}, {"type": "text", "text": "/exit"}]}}
        self.assertEqual(tr._user_text(d), "/exit")


class ProbeFailureTest(unittest.TestCase):
    def test_failing_refresh_is_warned(self):
        def boom():
            raise ValueError("x")
        with mock.patch.object(memo._PROBE_BG, "spawn", memo.run_inline), \
                mock.patch("sidereus.warn.warn_once") as w:
            self.assertIsNone(memo.serve_last("t-fail", boom, lambda: (0.0, None), 5, lambda: 1.0))
        self.assertTrue(w.called)
        self.assertEqual(w.call_args[1]["vars"]["key"], "t-fail")
        memo.PROBE_ERR.pop("t-fail", None)


if __name__ == "__main__":
    unittest.main()
