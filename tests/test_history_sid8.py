"""Shared short session id (sidereus/ident.py _sid8): file-stem sids must not collapse to «session-»."""
import unittest

from tests._load import sidereus

H = sidereus("ident")


class Sid8(unittest.TestCase):
    def test_uuid_unchanged(self):
        self.assertEqual(H._sid8("dd44dd44-1111-2222-3333-444455556666"), "dd44dd44")

    def test_gemini_stem(self):
        self.assertEqual(H._sid8("session-2026-09-24T05-24-3254b261"), "3254b261")

    def test_codex_stem(self):
        self.assertEqual(H._sid8("rollout-2026-09-24T05-24-33-0199aaaa-bbbb-cccc-dddd-eeeeffff0000"), "0199aaaa")

    def test_prefix_without_ts(self):
        self.assertEqual(H._sid8("session-abcdef1234"), "abcdef12")

    def test_empty(self):
        self.assertEqual(H._sid8(""), "")
        self.assertEqual(H._sid8(None), "")


if __name__ == "__main__":
    unittest.main()
