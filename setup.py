"""Wheel for `pipx install git+https://github.com/bugsterran/sidereus` / `uv tool install git+...` (stdlib only at runtime).

Code installs flat into site-packages (top-level modules + the `sidereus` package), so a wheel's CODE_DIR is site-packages.
Files the code reads through ASSET_DIR (web/, hooks/, docs/, ...) are copied into sidereus/_bundle/ by build_py below;
mailbox_config.asset_dir() picks that folder when CODE_DIR has no web/ (a clone keeps reading its own tree).
⚠The bundle is an explicit allow-list: never glob the repo root — it may hold live data (bus.jsonl, identity.json, config.local.json).
"""
import os
import re
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

SRC = os.path.dirname(os.path.abspath(__file__))

# (path relative to the repo root, recursive?) — each entry is read by the code via ASSET_DIR or run by path.
BUNDLE = (
    ("web", True),
    ("hooks", True),
    ("mcp/sidereus_mcp.py", False),
    ("features", True),
    ("scripts/pl_eval.py", False),
    ("scripts/pl_report.py", False),
    ("scripts/evidence_rec.py", False),   # imported by scripts/pl_eval.py
    ("docs/schema", True),
    ("docs/verdicts", True),          # Harness «Next step» guides (sidereus/verdict_guide.py)
    ("docs/HOOKS.md", False),
    (".claude/workflows/pipeline.js", False),
    ("config.example.json", False),
    ("plugin/hooks/hooks.json", False),
)
_SKIP_DIR = ("__pycache__",)
_SKIP_FILE = re.compile(r"(^\.|\.bak|\.pyc$|\.jsonl$|^identity\.json|^config\.local\.json)")   # ⚠backups and live data never ship


def bundle_files(src=SRC):
    """Relative paths of every bundled file under `src` (sorted)."""
    out = []
    for rel, deep in BUNDLE:
        p = os.path.join(src, rel)
        if not deep:
            if os.path.isfile(p):
                out.append(rel)
            continue
        for d, dirs, files in os.walk(p):
            dirs[:] = sorted(x for x in dirs if x not in _SKIP_DIR and not x.startswith("."))
            for f in sorted(files):
                if not _SKIP_FILE.search(f):
                    out.append(os.path.relpath(os.path.join(d, f), src))
    return sorted(out)


class BuildWithBundle(build_py):
    def run(self):
        build_py.run(self)
        dest = os.path.join(self.build_lib, "sidereus", "_bundle")
        for rel in bundle_files():
            t = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copy2(os.path.join(SRC, rel), t)


def version():
    """Latest released heading in CHANGELOG.md (`## [X.Y.Z]`) — the tag on main carries the same number."""
    try:
        with open(os.path.join(SRC, "CHANGELOG.md"), encoding="utf-8") as f:
            m = re.search(r"^## \[(\d+\.\d+\.\d+)\]", f.read(), re.M)
        return m.group(1) if m else "0.0.0"
    except OSError:
        return "0.0.0"


PY_MODULES = ["chat_server", "mailbox_config", "mailbox_core", "monitor_stream", "readcheck", "sidereus_cli", "watch_bus"]
PACKAGE_DATA = ["stage_catalog.json", "plat_TEMPLATE.py.txt"]

if __name__ == "__main__":   # build_meta and legacy setup.py both run it as __main__; tests import bundle_files() without building
    setup(
        name="sidereus",
        version=version(),
        description="Local viewer for several AI coding sessions: pipelines, timeline and structure on one screen.",
        url="https://github.com/bugsterran/sidereus",
        author="bugsterran",
        license="MIT",
        python_requires=">=3.9",
        packages=["sidereus"],
        package_data={"sidereus": PACKAGE_DATA},
        py_modules=PY_MODULES,
        entry_points={"console_scripts": ["sidereus=sidereus_cli:main"]},
        cmdclass={"build_py": BuildWithBundle},
        zip_safe=False,
    )
