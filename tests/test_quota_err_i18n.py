"""Quota fetch errors are fixed I18N keys: every `QF_ERR_KEYS` entry has a Korean entry (page does T(q.err))."""
import os
import unittest

from tests._load import sidereus

qf = sidereus("quota_fetch")
WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "js")


class QuotaErrI18n(unittest.TestCase):
    def test_keys_have_english(self):
        src = "".join(open(os.path.join(WEB, f), encoding="utf-8").read()
                      for f in sorted(os.listdir(WEB)) if f.startswith(("05a-i18n", "06-i18n")))
        for k in qf.QF_ERR_KEYS:
            self.assertIn("'" + k + "':", src)   # I18N.ko key (English source)

    def test_lookup_off_stores_key(self):
        saved, saved_err = qf._quota_lookup_on, qf._quota.get("err")
        qf._quota_lookup_on = lambda: False
        try:
            self.assertFalse(qf._quota_fetch())
            self.assertEqual(qf._quota["err"], qf.QF_ERR_KEYS[0])
        finally:
            qf._quota_lookup_on = saved
            qf._quota["err"] = saved_err


if __name__ == "__main__":
    unittest.main()
