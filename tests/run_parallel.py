"""Run tests/test_*.py in N parallel unittest processes and print one combined result.

Groups are balanced greedily by tests/durations.json (per-file seconds; unknown files get the median).
Each process gets its own MAILBOX_DIR / temp dirs from tests/_load.py, so groups share no paths.
Output keeps the serial format check.sh parses: «FAIL:/ERROR:» lines, «Ran N tests», «OK» / «FAILED (...)».
Refresh the timing table: python3 tests/run_parallel.py --measure
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUR = os.path.join(ROOT, "tests", "durations.json")
PY = os.environ.get("PYTHON", "/usr/bin/python3")


def _mods():
    return sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "tests", "test_*.py")))


def _groups(mods, n):
    try:
        with open(DUR, encoding="utf-8") as f:
            dur = json.load(f)
    except (OSError, ValueError):
        dur = {}
    known = sorted(dur.values())
    dflt = known[len(known) // 2] if known else 0.3
    groups = [[0.0, []] for _ in range(n)]
    for m in sorted(mods, key=lambda m: -dur.get(m, dflt)):
        g = min(groups, key=lambda g: g[0])
        g[0] += dur.get(m, dflt)
        g[1].append(m)
    return [sorted(g[1]) for g in groups if g[1]]


def _workers():
    n = os.environ.get("TESTS_JOBS")
    if n and n.isdigit() and int(n) > 0:
        return int(n)
    return max(2, min(8, (os.cpu_count() or 4) * 2 // 3))   # 12-core Mac: 6 jobs 20 s, 8 jobs 16.5 s


def _measure():
    out = {}
    for m in _mods():
        t = time.time()
        subprocess.run([PY, "-m", "unittest", "-q", "tests." + m], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out[m] = round(time.time() - t, 2)
    with open(DUR, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join('"%s": %.2f' % kv for kv in sorted(out.items())) + "\n}\n")
    print("wrote %s (%d files, %.1f s)" % (DUR, len(out), sum(out.values())))


def _run_group(mods):
    """One group process: load each module on its own so one import error cannot hide the rest."""
    import traceback
    import unittest
    sys.path[0] = ROOT   # same import root as `python -m unittest` from ROOT
    for st in (sys.stdout, sys.stderr):   # ⚠the parent reads the log as UTF-8; cp1252 stdio cannot print every test name
        st.reconfigure(encoding="utf-8", errors="backslashreplace")
    loader, suite = unittest.TestLoader(), unittest.TestSuite()
    for m in mods:
        try:
            suite.addTests(loader.loadTestsFromName("tests." + m))
        except Exception:
            tb = traceback.format_exc()

            def test_import(self, tb=tb):
                raise ImportError("module failed to import:\n" + tb)
            cls = type("ImportFailure", (unittest.TestCase,), {"test_import": test_import})
            cls.__module__ = "tests." + m   # ⚠ERROR line must name the module
            suite.addTest(cls("test_import"))
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if res.wasSuccessful() else 1


def main():
    if "--measure" in sys.argv:
        return _measure()
    if sys.argv[1:2] == ["--group"]:
        return _run_group(sys.argv[2:])
    sys.stdout.reconfigure(errors="backslashreplace")   # a console codec without a test's characters must not crash the summary
    t0 = time.time()
    groups = _groups(_mods(), _workers())
    tmp = tempfile.mkdtemp(prefix="sidereus-tests-")
    procs = []
    for i, g in enumerate(groups):
        log = open(os.path.join(tmp, "g%d.log" % i), "w+", encoding="utf-8", errors="replace")
        p = subprocess.Popen([PY, os.path.abspath(__file__), "--group"] + g,
                             cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        procs.append((p, log, g))
    ran = fails = errors = skipped = 0
    bad = []
    for i, (p, log, g) in enumerate(procs):
        rc = p.wait()
        log.seek(0)
        text = log.read()
        log.close()
        print("=== group %d/%d (%d files) exit %d ===" % (i + 1, len(procs), len(g), rc))
        print(text.rstrip("\n"))
        m = re.search(r"^Ran (\d+) tests?", text, re.M)
        ran += int(m.group(1)) if m else 0
        tail = text[m.end():] if m else ""
        fs = re.search(r"failures=(\d+)", tail)
        es = re.search(r"errors=(\d+)", tail)
        ss = re.search(r"skipped=(\d+)", tail)
        fails += int(fs.group(1)) if fs else 0
        errors += int(es.group(1)) if es else 0
        skipped += int(ss.group(1)) if ss else 0
        bad += re.findall(r"^(?:FAIL|ERROR): .*$", text, re.M)
        if rc != 0 and not (fs or es):
            # ⚠A group that crashed before its summary (import error, killed) still has to fail the run.
            errors += 1
            bad.append("ERROR: group %d exited %d without a summary (%s ...)" % (i + 1, rc, " ".join(g[:3])))
    shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 70)
    if bad:
        print("Failing tests:")
        for b in bad:
            print("  " + b)
    print("Ran %d tests in %.3fs (%d parallel groups)" % (ran, time.time() - t0, len(procs)))
    sk = ", skipped=%d" % skipped if skipped else ""
    if fails or errors:
        print("FAILED (failures=%d, errors=%d%s)" % (fails, errors, sk))
        return 1
    print("OK" + (" (skipped=%d)" % skipped if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
