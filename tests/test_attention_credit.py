"""«Spending credits» attention signal (R3): a row with `credit.lastAt` within ATT_CREDIT_S, not gone/done."""
import unittest

from tests._load import sidereus
from tests._clock import NOW

att = sidereus("attention")


def row(last_ago, state="unknown"):
    return {"sid": "s1", "state": state, "ageSec": 0, "credit": {"lastAt": int(NOW - last_ago), "tok": 5}}


class TestCreditSignal(unittest.TestCase):
    def sigs(self, r):
        return [s for s in att._row_sigs(r, NOW) if s["k"] == "credit"]

    def test_recent_spend_listed(self):
        s = self.sigs(row(60))
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["pts"], s[0]["since"], s[0]["why"]), (80, int(NOW - 60), "60"))

    def test_stopped_spend_drops(self):
        self.assertEqual(self.sigs(row(400)), [])

    def test_gone_or_done_none(self):
        self.assertEqual(self.sigs(row(60, "gone")), [])
        self.assertEqual(self.sigs(row(60, "done")), [])

    def test_no_credit_none(self):
        self.assertEqual(self.sigs({"sid": "s1", "state": "unknown"}), [])


if __name__ == "__main__":
    unittest.main()
