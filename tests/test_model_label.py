"""Model label keeps family + full version; drops claude- prefix, [tags], provider wrappers and dates."""
import unittest

from tests._load import sidereus, load

load()
T = sidereus("transcript")


class ModelLabel(unittest.TestCase):
    def test_labels(self):
        cases = {"claude-sonnet-4-5": "sonnet-4-5", "claude-sonnet-4-5-20250929": "sonnet-4-5",
                 "claude-opus-5-5[1m]": "opus-5-5", "claude-opus-5[1m]": "opus-5",
                 "claude-fable-5-1": "fable-5-1", "claude-haiku-4-5-20251001": "haiku-4-5",
                 "claude-3-5-haiku-20241022": "3-5-haiku", "claude-opus-4-20250514": "opus-4",
                 "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "sonnet-4-5",
                 "claude-haiku-4-5@20251001": "haiku-4-5", "": "", None: ""}
        for m, want in cases.items():
            self.assertEqual(T._model_label(m), want, m)


if __name__ == "__main__":
    unittest.main()
