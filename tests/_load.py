"""Shared test loader: import chat_server once by path without running main().

main() sits behind `if __name__ == "__main__"`, so loading it as a module starts no
background threads and does not touch the running server.
"""
import importlib
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOD = None
# ⚠Never the live ~/.codex: Codex scans (sidereus/plat_codex.py) read CODEX_HOME at call time.
# ⚠Keep this outside the repo: a stray write under tests/ once turned it into a live Codex home.
os.environ["CODEX_HOME"] = os.path.join(os.devnull, "no-codex-home")
# ⚠No live processes: ext_hook.build() would otherwise walk real parents with `ps` (tests that need it fake `_ps`).
os.environ["SIDEREUS_HOOK_NO_PID"] = "1"
# ⚠Data dir set before any sidereus import: DATA_DIR and every path built from it (BUS, CARDS, rooms.json, ...)
# are copied by value into many modules, so only the env var reaches them all.
DATA_TMP = tempfile.mkdtemp(prefix="sidereus-data-")
os.environ["MAILBOX_DIR"] = DATA_TMP
with open(os.path.join(DATA_TMP, "config.local.json"), "w", encoding="utf-8") as _f:
    _f.write("{}\n")   # empty config = defaults, without the «not found» warning


def load():
    """Return the chat_server module, loaded once per process."""
    global _MOD
    if _MOD is None:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        spec = importlib.util.spec_from_file_location("cs", os.path.join(ROOT, "chat_server.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["cs"] = mod
        spec.loader.exec_module(mod)
        _MOD = mod
        # ⚠ext_rows() saves the registry: without this a test's fake row lands in the live ext-sessions.json.
        ext = importlib.import_module("sidereus.ext_store")   # owner of the path globals and their writers
        tmp = tempfile.mkdtemp(prefix="sidereus-test-")
        ext.EXT_FILE = os.path.join(tmp, "ext-sessions.json")
        ext.EXT_RUNS_FILE = os.path.join(tmp, "ext-runs.json")
        ext.EXT_HOOKTOK_FILE = os.path.join(tmp, "ext-hooktok.json")
        # ⚠The rail joins file owners (git_rail._rail_owners -> file_owner.index): without this it scans live transcripts.
        importlib.import_module("sidereus.file_owner").CLAUDE_PROJECTS = os.path.join(tmp, "no-projects")
        # ⚠Quota/burn writers: an unstubbed path once wrote a fake plan cut into the live burn-hist-cache.json.
        importlib.import_module("sidereus.burn_hist").HIST_CACHE = os.path.join(tmp, "burn-hist-cache.json")
        importlib.import_module("sidereus.burn").QB_LIM_CACHE = os.path.join(tmp, "qb-lim-cache.json")
        q = importlib.import_module("sidereus.quota")
        q.QUOTA_CACHE = os.path.join(tmp, "quota-cache.json")
        q.OMC_CACHE = os.path.join(tmp, "omc-usage-cache.json")
        q.OMC_CACHE5 = os.path.join(tmp, "omc-usage-cache-anthropic.json")
        importlib.import_module("sidereus.otel").OTEL_TDAY_FILE = os.path.join(tmp, "otel-tools.json")
        importlib.import_module("sidereus.otel_cache").OC_FILE = os.path.join(tmp, "otel-cache.json")
        importlib.import_module("sidereus.otel_hooks").OH_FILE = os.path.join(tmp, "otel-hooks.json")
        importlib.import_module("sidereus.otel_acct").OA_FILE = os.path.join(tmp, "otel-acct.json")
        # ⚠`from sidereus.x import PATH` copies the value at import (burn, burn_week, burn_hist read QUOTA_LOG):
        # redirect the owner and every copy, or tests that leave a reader unpatched read the live file.
        _redirect_copies("sidereus.quota", "QUOTA_LOG", os.path.join(tmp, "quota-log.jsonl"))
        _redirect_copies("sidereus.transcript", "CLAUDE_PROJECTS", os.path.join(tmp, "no-projects"))
        # ⚠Extra account roots: without this `~/.claude-*` in the live home would be scanned.
        cr = importlib.import_module("sidereus.claude_roots")
        cr.SCAN_HOME = os.path.join(tmp, "no-home")
        cr.ACCT_DIR = os.path.join(tmp, "no-acct")   # acct_of: never the live per-session account records
        cr._ACCT_MEMO.clear()
        importlib.import_module("sidereus.quota_roots").USER_HOME = os.path.join(tmp, "no-home")
    return _MOD


def _redirect_copies(owner, name, new):
    """Set owner.NAME and every sidereus.* module's NAME that still holds the owner's live value to `new`."""
    live = getattr(importlib.import_module(owner), name)
    for mn, m in list(sys.modules.items()):
        if (mn == owner or mn.startswith("sidereus.")) and m is not None and getattr(m, name, None) == live:
            setattr(m, name, new)


_JS_ALL = None
_JS_FN = {}


def js_all():
    """All web/js/*.js joined in name order - the same order `_load_page` uses."""
    # Memoised per process: re-reading web/js on every js_fn call nearly doubled the suite time.
    global _JS_ALL
    if _JS_ALL is None:
        import glob
        out = []
        for p in sorted(glob.glob(os.path.join(ROOT, "web", "js", "*.js"))):
            with open(p, encoding="utf-8", newline="") as fh:
                out.append(fh.read())
        _JS_ALL = "".join(out)
    return _JS_ALL


def js_fn(name):
    """Top-level `function name(...)` source, found by name across all web/js files.
    ⚠Looked up by name, not file, so splitting a JS file does not break the test."""
    if name in _JS_FN:
        return _JS_FN[name]
    import re
    src = js_all()
    m = re.search(r"^function " + name + r"\(.*$", src, re.M)
    if m is None:
        raise LookupError("web/js: no top-level function " + name)
    if m.group(0).count("{") == m.group(0).count("}"):   # one-liner
        out = m.group(0)
    else:
        out = re.compile(r"^function " + name + r"\(.*?^}", re.S | re.M).search(src, m.start()).group(0)
    _JS_FN[name] = out
    return out


def sidereus(name):
    """Return sidereus.<name> (after chat_server is loaded, so shared state is wired)."""
    load()
    return importlib.import_module("sidereus." + name)
