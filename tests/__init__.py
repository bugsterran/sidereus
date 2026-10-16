"""Test package bootstrap: pin the host locale that leaks into child processes.

⚠Node >= 21 exposes navigator.language from LC_ALL / LC_MESSAGES / LANG (none set -> 'en-US'), and web/js/05-i18n.js
picks the UI language from it when nothing is saved. JS tests expect the 'ko' default, so they passed or failed with the
caller's shell (28 failures under `env -i`, or any en_* locale). Every tests.* module imports this package first, so
pinning here covers tests/run.sh, run_parallel.py groups and single-file runs alike; tests that need 'en' set it
explicitly (mbLang / LANG inside the node source).
"""
import os

for _k in ("LC_ALL", "LC_MESSAGES"):
    os.environ.pop(_k, None)
os.environ["LANG"] = "ko_KR.UTF-8"
