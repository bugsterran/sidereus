"""Disabled credits are not absent: `extra` stays with `on: False` + reason; the page marks it «off» and drops the badge.

No live files, no network, no clock."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn, sidereus
from tests._node import node_e
from tests.test_saver_quota_js import i18n, jconst

qf = sidereus("quota_fetch")

T0 = 1_800_000_000


class _Clock:
    @staticmethod
    def time():
        return T0


class ParseKeepsDisabled(unittest.TestCase):
    def setUp(self):
        self.saved = qf.time
        qf.time = _Clock

    def tearDown(self):
        qf.time = self.saved

    def test_disabled_kept_with_reason(self):
        out = qf._qf_parse({"five_hour": None, "seven_day": None, "extra_usage": {
            "is_enabled": False, "monthly_limit": 60000, "used_credits": 60000, "utilization": 100.0,
            "currency": "USD", "disabled_reason": "out_of_credits"}})
        ex = out["extra"]
        self.assertIs(ex["on"], False)
        self.assertEqual(ex["why"], "out_of_credits")
        self.assertEqual((ex["used"], ex["limit"], ex["at"]), (60000, 60000, T0))

    def test_enabled_and_reason_filter(self):
        on = qf._qf_parse({"extra_usage": {"is_enabled": True, "used_credits": 5}})["extra"]
        self.assertEqual((on["on"], on["why"]), (True, None))
        bad = qf._qf_parse({"extra_usage": {"is_enabled": False, "disabled_reason": "<b>x</b>"}})["extra"]
        self.assertIsNone(bad["why"])
        self.assertIsNone(qf._qf_parse({"extra_usage": {"disabled_reason": "a" * 61}})["extra"]["why"])

    def test_absent_has_no_extra(self):
        self.assertNotIn("extra", qf._qf_parse({"five_hour": None}))
        self.assertNotIn("extra", qf._qf_parse({"extra_usage": None}))


STUBS = """
var document = {getElementById: () => null};
const gauge = p => '<g>', qcls = p => 'ok', ageU = s => String(s);
"""
FNS = ("fmtMoney", "creditExact", "creditPct", "creditRow", "creditInfo")


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PageMarksOff(unittest.TestCase):
    def run_js(self, body):
        src = STUBS + i18n() + "\nLANG = 'en';\n" + jconst("esc") + "\n" + "\n".join(js_fn(f) for f in FNS) + "\n" + body
        r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
        if r.returncode != 0:
            raise AssertionError(r.stderr)
        return json.loads(r.stdout)

    def test_off_row_and_no_badge(self):
        ex = "{on: false, why: 'out_of_credits', pct: 100, used: 60000, limit: 60000, seat: 'x_usage_based'}"
        row, ci = self.run_js("const QX = {five_hour: {pct: 100}, extra: " + ex + "};"
                              " process.stdout.write(JSON.stringify([creditRow(QX), creditInfo(QX)]));")
        self.assertIn(">off</b>", row)
        self.assertIn("out_of_credits", row)
        self.assertIn("$600.00/$600.00", row)
        self.assertIsNone(ci)

    def test_off_without_amounts_still_shows(self):
        row = self.run_js("process.stdout.write(JSON.stringify(creditRow({extra: {on: false, why: null}})));")
        self.assertIn(">off</b>", row)
        self.assertNotIn("?", row)
        self.assertEqual(self.run_js("process.stdout.write(JSON.stringify(creditRow({})));"), "")

    def test_undefined_on_means_on(self):
        row, ci = self.run_js("const QX = {five_hour: {pct: 100}, extra: {pct: 5, used: 100, limit: 60000}};"
                              " process.stdout.write(JSON.stringify([creditRow(QX), creditInfo(QX)]));")
        self.assertNotIn(">off</b>", row)
        self.assertTrue(ci)


if __name__ == "__main__":
    unittest.main()
