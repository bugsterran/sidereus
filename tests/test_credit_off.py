"""Row `credit` (chip + «Spending credits») is dropped only while quota.extra.on is explicitly False."""
import unittest

from tests._load import sidereus

st = sidereus("state")


def rows():
    return [{"sid": "a", "credit": {"lastAt": 1, "tok": 5}}, {"sid": "b"}]


class TestCreditOff(unittest.TestCase):
    def test_off_drops_credit(self):
        src = rows()
        out = st._credit_off(src, {"extra": {"on": False}})
        self.assertEqual([("credit" in r) for r in out], [False, False])
        self.assertIn("credit", src[0])   # cached snapshot rows are not mutated

    def test_on_keeps(self):
        out = st._credit_off(rows(), {"extra": {"on": True}})
        self.assertIn("credit", out[0])

    def test_unknown_keeps(self):
        for q in (None, {}, {"extra": None}, {"extra": {"on": None}}, {"extra": {}}):
            self.assertIn("credit", st._credit_off(rows(), q)[0], q)


if __name__ == "__main__":
    unittest.main()
