"""Pipelines agent rows carry a one-line frontmatter description (`desc`), never a path."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from sidereus import ctxsrc, demo_tools, pipeline, toolinv


def _md(d, fname, front):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
        f.write("---\n" + front + "---\nbody\n")


class AgentDesc(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.proj = os.path.join(self.d, "proj")
        self.home = os.path.join(self.d, "home")
        self.pa = os.path.join(self.proj, ".claude", "agents")
        self.ua = os.path.join(self.home, "agents")
        os.makedirs(self.pa)
        os.makedirs(self.ua)
        p = mock.patch.object(ctxsrc, "CLAUDE_DIR", self.home)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.d)

    def _rows(self):
        return {r["name"]: r for r in pipeline._agents(self.proj)}

    def test_desc_trimmed_and_capped(self):
        _md(self.pa, "a.md", "name: alpha\ndescription:   Does   the  thing \n")
        _md(self.pa, "b.md", "name: beta\ndescription: " + "x" * 200 + "\n")
        rows = self._rows()
        self.assertEqual(rows["alpha"]["desc"], "Does the thing")
        self.assertEqual(rows["beta"]["desc"], "x" * toolinv.AGENT_DESC_MAX + "…")

    def test_project_beats_user(self):
        _md(self.pa, "a.md", "name: alpha\ndescription: project one\n")
        _md(self.ua, "a.md", "name: alpha\ndescription: user one\n")
        _md(self.ua, "g.md", "name: gamma\ndescription: global\n")
        rows = self._rows()
        self.assertEqual(rows["alpha"], {"name": "alpha", "scope": "project", "desc": "project one"})
        self.assertEqual(rows["gamma"], {"name": "gamma", "scope": "user", "desc": "global"})

    def test_no_or_empty_description_has_no_key(self):
        _md(self.pa, "a.md", "name: alpha\n")
        _md(self.pa, "d.md", "name: delta\ndescription:\n")
        _md(self.pa, "e.md", "name: eps\ndescription: |\ntools: Read\n")
        rows = self._rows()
        for n in ("alpha", "delta", "eps"):
            self.assertEqual(rows[n], {"name": n, "scope": "project"})

    def test_block_scalar_description_is_folded(self):
        # Most agent files write `description: |` with an indented body; it must not read as the bare marker.
        _md(self.pa, "b.md", "name: beta\ndescription: |\n  multi\n  line\ntools: Read\n")
        _md(self.pa, "c.md", "name: gamma\ndescription: >-\n  folded\n")
        rows = self._rows()
        self.assertEqual(rows["beta"]["desc"], "multi line")
        self.assertEqual(rows["gamma"]["desc"], "folded")

    def test_no_path_in_payload(self):
        _md(self.pa, "a.md", "name: alpha\ndescription: hi\n")
        for r in pipeline._agents(self.proj):
            self.assertEqual(set(r) - {"name", "scope", "desc"}, set())
            self.assertNotIn(self.d, repr(r))


class DemoDesc(unittest.TestCase):
    def test_every_demo_agent_has_desc(self):
        code, body = demo_tools._demo_pipelines("/demo", "/demo")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["agents"]), 4)
        for a in body["agents"]:
            self.assertTrue(a.get("desc"), a["name"])
            self.assertEqual(a["scope"], "project")


if __name__ == "__main__":
    unittest.main()
