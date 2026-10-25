"""Test package bootstrap: pin the host locale that leaks into child processes.

⚠Node >= 21 exposes navigator.language from LC_ALL / LC_MESSAGES / LANG (none set -> 'en-US'), and web/js/05-i18n.js
picks the UI language from it when nothing is saved. JS tests expect the 'ko' default, so they passed or failed with the
caller's shell (28 failures under `env -i`, or any en_* locale). Every tests.* module imports this package first, so
pinning here covers tests/run.sh, run_parallel.py groups and single-file runs alike; tests that need 'en' set it
explicitly (mbLang / LANG inside the node source).
"""
import os
import tempfile

for _k in ("LC_ALL", "LC_MESSAGES"):
    os.environ.pop(_k, None)
os.environ["LANG"] = "ko_KR.UTF-8"

# ⚠Isolation env lives here, not only in tests/_load.py: a test module doing `from sidereus import x` before
# `from tests._load import ...` froze sidereus.config.DATA_DIR on the live ~/.mailbox-mcp for its whole process,
# and ext_store._ext_load() then read the live ext-sessions.json at import.
# ⚠Never the live ~/.codex: Codex scans (sidereus/plat_codex.py) read CODEX_HOME at call time.
# ⚠Keep this outside the repo: a stray write under tests/ once turned it into a live Codex home.
os.environ["CODEX_HOME"] = os.path.join(os.devnull, "no-codex-home")
# ⚠No live processes: ext_hook.build() would otherwise walk real parents with `ps` (tests that need it fake `_ps`).
os.environ["SIDEREUS_HOOK_NO_PID"] = "1"
# ⚠DATA_DIR and every path built from it (BUS, CARDS, rooms.json, ...) are copied by value into many modules,
# so only the env var set before any sidereus import reaches them all.
DATA_TMP = tempfile.mkdtemp(prefix="sidereus-data-")
os.environ["MAILBOX_DIR"] = DATA_TMP
with open(os.path.join(DATA_TMP, "config.local.json"), "w", encoding="utf-8") as _f:
    _f.write("{}\n")   # empty config = defaults, without the «not found» warning
