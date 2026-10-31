"""setup.py wheel: built offline from a staged copy, then imported from an unzipped site dir (no clone, no server, no port)."""
import hashlib
import importlib.util
import json
import os
import py_compile
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from unittest import mock

from tests._load import sidereus

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = "/usr/bin/python3"


def _has_build_tools():
    if not os.path.exists(PY):
        return False
    return subprocess.run([PY, "-c", "import setuptools, wheel"], capture_output=True).returncode == 0


def _setup_mod():
    spec = importlib.util.spec_from_file_location("sidereus_setup_under_test", os.path.join(REPO, "setup.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)   # setup() is guarded by __main__, so this only defines the lists
    return m


def _stage(dst):
    """Copy only what the build reads. ⚠Never build from the repo root: it holds live data next to the code."""
    s = _setup_mod()
    rels = ["setup.py", "pyproject.toml", "CHANGELOG.md"] + [m + ".py" for m in s.PY_MODULES]
    rels += ["sidereus/" + f for f in sorted(os.listdir(os.path.join(REPO, "sidereus")))
             if f.endswith(".py") or f in s.PACKAGE_DATA]
    rels += s.bundle_files(REPO)
    for rel in rels:
        t = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(t), exist_ok=True)
        shutil.copy2(os.path.join(REPO, rel), t)


PROBE = r"""
import hashlib, json, os
from sidereus import config, page
print(json.dumps({"code": os.path.realpath(config.CODE_DIR), "asset": os.path.realpath(config.ASSET_DIR),
                  "clone": config.IS_CLONE, "page": hashlib.sha256(page.PAGE.encode("utf-8")).hexdigest()}))
"""


@unittest.skipUnless(_has_build_tools(), "/usr/bin/python3 lacks setuptools/wheel")
@unittest.skipUnless(importlib.util.find_spec("setuptools"), "test interpreter lacks setuptools (_stage imports setup.py)")
class WheelBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sidereus-wheel-")
        src, dist = os.path.join(cls.tmp, "src"), os.path.join(cls.tmp, "dist")
        _stage(src)
        r = subprocess.run([PY, "-m", "pip", "wheel", "--no-build-isolation", "--no-deps", "--no-index",
                            "--disable-pip-version-check", "-q", "-w", dist, src],
                           capture_output=True, text=True, encoding="utf-8", cwd=cls.tmp, timeout=300)
        whl = [f for f in os.listdir(dist) if f.endswith(".whl")] if os.path.isdir(dist) else []
        cls.build_err = "" if r.returncode == 0 and len(whl) == 1 else (r.stdout + r.stderr)[-2000:]
        cls.whl = os.path.join(dist, whl[0]) if whl else ""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.assertEqual(self.build_err, "", "wheel build failed")

    def test_contents(self):
        with zipfile.ZipFile(self.whl) as z:
            names = z.namelist()
            ep = [n for n in names if n.endswith(".dist-info/entry_points.txt")]
            self.assertEqual(len(ep), 1)
            self.assertIn("sidereus = sidereus_cli:main", z.read(ep[0]).decode("utf-8"))
        base = [os.path.basename(n) for n in names]
        self.assertFalse([n for n in base if n.endswith(".jsonl") or n in ("identity.json", "config.local.json")])
        self.assertFalse([n for n in names if "__pycache__" in n or ".bak" in n])
        for want in ("chat_server.py", "sidereus_cli.py", "sidereus/stage_catalog.json",
                     "sidereus/_bundle/web/index.html", "sidereus/_bundle/config.example.json",
                     "sidereus/_bundle/mcp/sidereus_mcp.py", "sidereus/_bundle/docs/verdicts/dup.md", "sidereus/_bundle/plugin/hooks/hooks.json",
                     "sidereus/_bundle/ext-hooks/ext_hook.py", "sidereus/_bundle/ext-hooks/copilot-hooks-example.json"):
            self.assertIn(want, names)

    def test_installed_layout_resolves_bundle(self):
        site, data = os.path.join(self.tmp, "site"), os.path.join(self.tmp, "data")
        with zipfile.ZipFile(self.whl) as z:
            z.extractall(site)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": site, "MAILBOX_DIR": data,
               "HOME": self.tmp, "PYTHONDONTWRITEBYTECODE": "1"}
        r = subprocess.run([PY, "-c", PROBE], capture_output=True, text=True, encoding="utf-8", cwd=self.tmp, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        got = json.loads(r.stdout.strip().splitlines()[-1])
        real = os.path.realpath(site)
        self.assertEqual(got["code"], real)
        self.assertEqual(got["asset"], os.path.join(real, "sidereus", "_bundle"))
        self.assertFalse(got["clone"])
        clone = hashlib.sha256(sidereus("page").PAGE.encode("utf-8")).hexdigest()
        self.assertEqual(got["page"], clone)


@unittest.skipUnless(importlib.util.find_spec("setuptools"), "test interpreter lacks setuptools (setup.py imports it)")
class BundleShipsExtHooks(unittest.TestCase):
    """«Connect» reads ASSET_DIR/ext-hooks; a bundle without it reports «no ext-hooks» on every pipx/uv install."""

    def test_templates_in_bundle_and_resolve(self):
        hc = sidereus("hook_connect")
        rels = _setup_mod().bundle_files(REPO)
        want = ["ext-hooks/" + f for f in hc._TPL.values()] + ["ext-hooks/ext_hook.py"]
        self.assertEqual([w for w in want if w not in rels], [])
        self.assertFalse([r for r in rels if r.startswith("ext-hooks/") and ("__pycache__" in r or os.path.basename(r).startswith("."))])
        tmp = tempfile.mkdtemp(prefix="sidereus-bundle-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for rel in rels:
            t = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copy2(os.path.join(REPO, rel), t)
        with mock.patch.object(hc, "TPL_DIR", None), mock.patch.object(hc.config, "ASSET_DIR", tmp):
            for plat in hc._TPL:
                self.assertIsNotNone(hc._template(plat), plat)


class SetupCompiles(unittest.TestCase):
    def test_py_compile_39(self):
        if os.path.exists(PY):
            r = subprocess.run([PY, "-m", "py_compile", os.path.join(REPO, "setup.py")], capture_output=True, text=True, encoding="utf-8",
                               env=dict(os.environ, PYTHONPYCACHEPREFIX=tempfile.gettempdir()))
            self.assertEqual(r.returncode, 0, r.stderr)
        else:
            py_compile.compile(os.path.join(REPO, "setup.py"), cfile=os.path.join(tempfile.mkdtemp(), "s.pyc"), doraise=True)


if __name__ == "__main__":
    unittest.main()
