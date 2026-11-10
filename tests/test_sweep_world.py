"""scripts/sweep_world.py: sandbox world for live sweeps. Temp dirs only, fixed `now`; no live file, clock or network."""
import importlib.util
import json
import ntpath
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._load import js_fn, sidereus
from tests._node import node_e
from tests.test_ident_slug import _fake_os
from tests.test_pl_start_checklist_r1_r2_js import STUBS

ident = sidereus("ident")
parse = sidereus("parse")
pipeline = sidereus("pipeline")
hook_connect = sidereus("hook_connect")
# plat_cursor/plat_copilot.root are stubbed by tests._load; their paths are covered through hook_connect._files
plats = [sidereus(n) for n in ("plat_codex", "plat_gemini")]
demo_data = sidereus("demo_data")
plat_pi = sidereus("plat_pi")
work = sidereus("work")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("sweep_world", os.path.join(ROOT, "scripts", "sweep_world.py"))
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)

NOW = 1767225600   # 2026-01-01T00:00:00Z
_TOP = {"cwd", "sessionId", "timestamp", "type", "uuid", "message", "permissionMode", "subtype", "data"}


def _tree(d):
    out = {}
    for base, _dirs, files in os.walk(d):
        for f in files:
            p = os.path.join(base, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d)] = fh.read()
    return out


class SweepWorld(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-sweep-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = os.path.join(self.tmp, "w")
        self.lines = sw.build(self.out, 8899, NOW)
        self.p = sw.paths(self.out)

    def test_manifest_paths_exist(self):
        with open(os.path.join(ROOT, "tests", "fixtures", "sweep", "manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
        self.assertEqual([c["id"] for c in man["cases"]], ["a", "b", "c", "e", "f"])
        for c in man["cases"]:
            self.assertTrue(os.path.exists(os.path.join(self.out, c["path"])), c["id"])

    def test_env_and_launch_lines(self):
        o = os.path.realpath(self.out)
        for k, sub in (("HOME", "home"), ("CLAUDE_CONFIG_DIR", "cc"), ("MAILBOX_DIR", "data"), ("SIDEREUS_USER_HOME", "home")):
            self.assertIn("export %s=%s" % (k, shlex.quote(os.path.join(o, sub))), self.lines)   # Windows paths get quoted
        self.assertTrue(self.lines[-1].endswith(" start --port 8899"), self.lines[-1])
        self.assertIn("sidereus_cli.py", self.lines[-1])   # quoted on Windows: ...sidereus_cli.py' start

    def test_refuses_non_empty_and_tool_dirs(self):
        with self.assertRaises(ValueError):
            sw.build(self.out, 8899, NOW)
        for h in sw._homes():
            for d in (".claude", ".codex", ".cursor", ".gemini", ".copilot"):
                self.assertIn("inside", sw.check_out(os.path.join(h, d, "sweep")))
        self.assertEqual(sw.check_out(os.path.join(self.tmp, "fresh")), "")

    def test_deterministic(self):
        a = _tree(self.out)
        shutil.rmtree(self.out)
        sw.build(self.out, 8899, NOW)
        self.assertEqual(a, _tree(self.out))

    def test_metadata_only(self):
        sw.append_ask(self.out, NOW)
        n = 0
        for base, _d, files in os.walk(os.path.join(self.out, "cc", "projects")):
            for f in files:
                with open(os.path.join(base, f), encoding="utf-8") as fh:
                    for ln in fh:
                        d = json.loads(ln)
                        n += 1
                        self.assertLessEqual(set(d), _TOP, f)
                        self.assertEqual(d.get("data", {}), {})
                        c = (d.get("message") or {}).get("content")
                        if isinstance(c, str):
                            self.assertEqual(c, "")
                        for x in c if isinstance(c, list) else ():
                            for k in ("text", "thinking", "content"):
                                self.assertIn(x.get(k, ""), ("", None), f)
                            if x.get("type") == "tool_use":
                                self.assertEqual(x["input"], {})
        self.assertGreater(n, 1000)

    def test_a_only_invalid_pipeline_reads_red_false(self):
        proj = os.path.join(self.p["proj"], "onlybad")
        self.assertEqual(pipeline._names(proj), ["broken"])
        row = pipeline._row(proj, "broken")
        self.assertFalse(row["ok"])
        if not shutil.which("node"):
            self.skipTest("node not installed")
        data = {proj: {"ok": True, "pipelines": [row]}}
        code = STUBS + js_fn("plStartSteps") + "\nconsole.log(JSON.stringify(plStartSteps(true, %s, %s).map(s => s.done)));" % (
            json.dumps({"ok": True, "projects": [{"path": proj, "n": 1}]}), json.dumps(data))
        r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertIs(json.loads(r.stdout)[3], False)   # red step: false, not unknown

    def test_b_incremental_equals_fresh_after_answer(self):
        fp = self.p["ask"]
        self.assertGreater(os.path.getsize(fp), 400_000)
        saved = dict(parse._HUMAN_SEEN)
        self.addCleanup(lambda: (parse._HUMAN_SEEN.clear(), parse._HUMAN_SEEN.update(saved)))
        parse._HUMAN_SEEN.pop(fp, None)
        before = parse._human_deep(fp)
        self.assertEqual(parse._HUMAN_SEEN[fp][2], (sw.ASK_ID,))
        sw.append_ask(self.out, NOW)
        inc = parse._human_deep(fp)
        parse._HUMAN_SEEN.pop(fp, None)
        fresh = parse._human_deep(fp)
        self.assertEqual(inc, fresh)
        self.assertEqual(inc, NOW - 30)
        self.assertGreater(inc, before)

    def test_c_slugs(self):
        uni = os.path.join(self.p["proj"], sw.UNICODE_DIR)
        folder = os.path.join(self.p["cc"], "projects", ident._slug(uni))
        self.assertTrue(os.path.isfile(os.path.join(folder, sw.SLUG_SID + ".jsonl")))
        self.assertTrue(ident._slug(uni).isascii())
        self.assertTrue(os.path.isdir(os.path.join(self.p["cc"], "projects", sw.WIN_SLUG)))
        old = ident.os
        ident.os = _fake_os("nt", ntpath, {"C:\\Users", "C:\\Users\\demo", "C:\\Users\\demo\\app"})
        self.addCleanup(setattr, ident, "os", old)
        self.assertEqual(ident._cwd_from_slug(sw.WIN_SLUG), sw.WIN_CWD)

    def test_f_pi_session_parsed_under_sandbox_home(self):
        home = self.p["home"]
        cwd, fp = sw.pi_path(self.out, NOW)
        self.assertTrue(os.path.isfile(fp))
        self.assertTrue(os.path.isdir(cwd))                               # cwd exists in the world
        self.assertTrue(fp.startswith(os.path.realpath(self.out) + os.sep))
        root = os.path.join(home, ".pi", "agent")                          # plat_pi.root() default under SIDEREUS_USER_HOME
        self.assertTrue(fp.startswith(os.path.join(root, "sessions") + os.sep))
        self.assertIn("PI_CODING_AGENT_DIR", self.lines[0])               # unset, so the sandbox home wins
        self.addCleanup(plat_pi._cache.clear)
        with mock.patch.object(plat_pi, "root", lambda: root):          # ⚠tests._load stubs root(); patch, not env
            row = plat_pi.one(sw.PI_SID)
            self.assertIsNotNone(row)
            self.assertEqual((row["path"], row["cwd"]), (fp, cwd))
            self.assertEqual([n for _t, n in row["tools"]], ["bash"])
            self.assertTrue(row["msgs"])
            self.assertEqual(work._pi_file(sw.PI_SID), fp)
            sc, err = work._work_scan(work._pi_lines(fp, cwd, {}), cwd)
        self.assertFalse(err)
        steps, says = sc[0], sc[1]
        self.assertEqual([st["tool"] for st in steps], ["Bash"])
        self.assertEqual([x["text"] for x in says], ["sample step", "sample reply"])

    def test_e_hook_paths_under_sandbox_home(self):
        home = self.p["home"]
        env = {"SIDEREUS_USER_HOME": home}
        with mock.patch.dict(os.environ, env), mock.patch.object(hook_connect, "HC_FILES", None):
            for k in ("CODEX_HOME", "GEMINI_CLI_HOME", "COPILOT_HOME"):
                os.environ.pop(k, None)
            files = hook_connect._files()
            roots = [m.root() for m in plats] + [ident._real_home()]
        self.assertEqual(sorted(files), ["codex", "copilot", "cursor", "gemini"])
        self.assertEqual(roots[-1], home)
        for p in list(files.values()) + roots[:-1]:
            self.assertTrue(p.startswith(home + os.sep), p)
        for p in files.values():
            self.assertTrue(os.path.isfile(p), p)


class DemoSlug(unittest.TestCase):
    def test_demo_memory_dir_matches_ident_slug(self):
        cwd = "/home/demo/\ud55c\uae00-caf\u00e9"
        got = demo_data._WorldPanels.session_context(mock.Mock(a=0), cwd)["memory"]["dir"]
        self.assertEqual(got, "/home/demo/.claude/projects/" + ident._slug(cwd) + "/memory")


if __name__ == "__main__":
    unittest.main()
