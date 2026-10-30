"""#27 «Next step» guides (sidereus/verdict_guide.py, docs/verdicts/): R1 every verdict id the server emits has a guide
with the four fields; R3 refixed names sidereus-bugfix; R4 owner guides say when to ignore. Fork files go in a tmp VG_DIR."""
import os
import re
import shutil
import tempfile
import unittest

from tests._load import ROOT, load, sidereus

load()
VG = sidereus("verdict_guide")
DOCS = os.path.join(ROOT, "docs", "verdicts")
INCIDENT = ("refixed", "reverted", "unchecked")


def _src(name):
    with open(os.path.join(ROOT, "sidereus", name + ".py"), encoding="utf-8") as f:
        return f.read()


def _emitted():
    """Verdict ids harness_verdict can emit: every ("bad"|"check", "<id>", ...) literal."""
    return set(re.findall(r'"(?:bad|check)", "([a-z_]+)"', _src("harness_verdict")))


GUIDE = """# {id}

## Meaning
m

## Why it matters
w

## Who acts
{who}

## Next step
n
"""


class _Dir(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._old = VG.VG_DIR
        VG.VG_DIR = self.d
        VG._VG_CACHE.clear()

    def tearDown(self):
        VG.VG_DIR = self._old
        VG._VG_CACHE.clear()
        shutil.rmtree(self.d, ignore_errors=True)

    def put(self, name, text):
        with open(os.path.join(self.d, name), "w", encoding="utf-8") as f:
            f.write(text)


class TestShippedGuides(unittest.TestCase):
    def setUp(self):
        self._old = VG.VG_DIR
        VG.VG_DIR = DOCS   # repo docs, not live user data
        VG._VG_CACHE.clear()

    def tearDown(self):
        VG.VG_DIR = self._old
        VG._VG_CACHE.clear()

    def test_r1_emitted_ids_are_known(self):
        ids = _emitted()
        for v in ("hook_missing", "mcp_fail", "ref_missing", "never_ran", "idle", "dup", "slow_block", "rule_big"):
            self.assertIn(v, ids)
        trail = _src("harness_trail")
        for st in INCIDENT:
            self.assertIn('"%s"' % st, trail)
        self.assertIn('"skipgate"', _src("harness_flow"))

    def test_r1_every_id_has_en_and_ko_file(self):
        for vid in sorted(_emitted() | set(INCIDENT) | {"skipgate", "runtime-behind"}):
            for suf in (".md", ".ko.md"):
                self.assertTrue(os.path.isfile(os.path.join(DOCS, vid + suf)), "missing guide docs/verdicts/%s%s" % (vid, suf))

    def test_r1_every_file_parses_with_four_fields(self):
        names = [f for f in os.listdir(DOCS) if f.endswith(".md")]
        self.assertTrue(names)
        for f in names:
            with open(os.path.join(DOCS, f), encoding="utf-8") as fh:
                text = fh.read()
            g = VG.parse(text)
            self.assertIsNotNone(g, f)
            self.assertIn(g["who"], ("self", "ai", "owner"), f)
            for k in ("meaning", "why", "next"):
                self.assertTrue(g[k], (f, k))
            if not f.endswith(".ko.md"):
                self.assertFalse(re.search("[가-힣]", text), "Hangul in English guide " + f)

    def test_r4_owner_guides_say_when_to_ignore(self):
        en = VG.load("en")
        owners = [k for k, g in en.items() if g["who"] == "owner"]
        self.assertEqual(sorted(owners), ["idle", "never_ran", "reverted", "skipgate", "slow_block"])
        for k in owners:
            self.assertTrue(en[k]["ignore"], k)

    def test_r2_self_guides_name_a_command_or_setting(self):
        en = VG.load("en")
        self.assertEqual(sorted(k for k, g in en.items() if g["who"] == "self"),
                         ["dup", "hook_missing", "mcp_fail", "runtime-behind", "unchecked"])
        for k, g in en.items():
            if g["who"] == "self":
                self.assertIn("`", g["next"], k)

    def test_r3_ai_guides_and_bugfix_pipeline(self):
        en = VG.load("en")
        self.assertEqual(sorted(k for k, g in en.items() if g["who"] == "ai"), ["ref_missing", "refixed", "rule_big"])
        self.assertEqual(en["refixed"]["pipeline"], "sidereus-bugfix")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, ".claude", "pipelines", "sidereus-bugfix.json")))

    def test_ko_differs_and_keeps_shape(self):
        en, ko = VG.load("en"), VG.load("ko")
        self.assertEqual(set(en), set(ko))
        self.assertNotEqual(en["dup"]["meaning"], ko["dup"]["meaning"])
        self.assertEqual(en["dup"]["who"], ko["dup"]["who"])


class TestLoad(_Dir):
    def test_fork_file_shows(self):
        self.put("my_verdict.md", GUIDE.format(id="my_verdict", who="ai") + "\n## Pipeline\nmy-fix\n")
        g = VG.load("en")["my_verdict"]
        self.assertEqual((g["meaning"], g["why"], g["who"], g["next"], g["ignore"], g["pipeline"]),
                         ("m", "w", "ai", "n", "", "my-fix"))

    def test_bad_id_missing_field_bad_who_skipped(self):
        self.put("Bad.md", GUIDE.format(id="Bad", who="self"))
        self.put("no_next.md", GUIDE.format(id="no_next", who="self").replace("## Next step\nn\n", ""))
        self.put("who_bad.md", GUIDE.format(id="who_bad", who="anyone"))
        self.put("own.md", GUIDE.format(id="own", who="owner"))   # owner without «Safe to ignore when»
        self.put("ok.md", GUIDE.format(id="ok", who="self"))
        self.assertEqual(sorted(VG.load("en")), ["ok"])

    def test_field_capped(self):
        self.put("long.md", GUIDE.format(id="long", who="self").replace("\nm\n", "\n" + "x" * 900 + "\n"))
        self.assertEqual(len(VG.load("en")["long"]["meaning"]), VG.VG_FIELD_MAX)

    def test_ko_falls_back_to_en_per_id(self):
        self.put("a.md", GUIDE.format(id="a", who="self"))
        self.put("b.md", GUIDE.format(id="b", who="self"))
        self.put("a.ko.md", GUIDE.format(id="a", who="self").replace("\nm\n", "\nko-m\n"))
        ko = VG.load("ko")
        self.assertEqual((ko["a"]["meaning"], ko["b"]["meaning"]), ("ko-m", "m"))
        self.assertEqual(VG.load("xx")["a"]["meaning"], "m")   # unknown lang reads as en

    def test_cached_once(self):
        self.put("a.md", GUIDE.format(id="a", who="self"))
        self.assertIn("a", VG.load("en"))
        os.remove(os.path.join(self.d, "a.md"))
        self.assertIn("a", VG.load("en"))

    def test_missing_dir_is_empty(self):
        VG.VG_DIR = os.path.join(self.d, "nope")
        self.assertEqual(VG.load("en"), {})


if __name__ == "__main__":
    unittest.main()
