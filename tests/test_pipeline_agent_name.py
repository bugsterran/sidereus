"""Stage agent names: built-in types are capitalised (Explore, Plan) and must validate; skills stay lowercase."""
import unittest

from sidereus.pipeline_schema import _AGENT, _SKILL


class AgentName(unittest.TestCase):
    def test_builtin_capitalised_ok(self):
        for n in ("Explore", "Plan", "general-purpose", "sidereus_x"):
            self.assertTrue(_AGENT.fullmatch(n), n)

    def test_bad_names_refused(self):
        for n in ("", "Bad Name", "-lead", "a/b", "x" * 61, "Explore\n"):
            self.assertFalse(_AGENT.fullmatch(n), repr(n))

    def test_skill_stays_lowercase(self):
        self.assertTrue(_SKILL.fullmatch("sidereus-ship"))
        self.assertFalse(_SKILL.fullmatch("Sidereus-ship"))


if __name__ == "__main__":
    unittest.main()
