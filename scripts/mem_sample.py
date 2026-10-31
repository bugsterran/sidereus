#!/usr/bin/env python3
"""Viewer memory sampler with a fixed protocol, so runs on different days compare.

  mem_sample.py [--pid N] [--minutes 40] [--step 120]

Samples the viewer listening on 127.0.0.1:8799 (or --pid) every --step seconds for --minutes.
Each line: time · process age · footprint MB · RSS MB. Last line: footprint min/median/max and RSS median.
Stdlib only, Python 3.9. Read-only: never restarts or signals the process.

Why two metrics: RSS leaves out compressed and swapped pages, so on macOS it read about half of the
footprint (the Activity Monitor «Memory» value) for the same process — 104 vs 218 MB at 25 min after a
restart. Comparing an RSS number with a footprint number made every run look different.
Report the footprint median of the window, together with the process age the window covers.
"""
import argparse
import re
import statistics
import subprocess
import sys
import time

PORT = 8799


def parse_footprint(text):
    """MB from `footprint <pid>` output («Footprint: 218 MB»), or None."""
    m = re.search(r"Footprint:\s*([\d.]+)\s*(KB|MB|GB)", text or "")
    if not m:
        return None
    return float(m.group(1)) * {"KB": 1 / 1024, "MB": 1, "GB": 1024}[m.group(2)]


def _run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def viewer_pid():
    """PID listening on PORT (lsof), or None."""
    out = _run(["lsof", "-nP", "-t", "-iTCP:%d" % PORT, "-sTCP:LISTEN"]).split()
    return int(out[0]) if out else None


def sample(pid):
    """(etime, footprint MB or None, RSS MB) or None when the process is gone."""
    ps = _run(["ps", "-o", "rss=,etime=", "-p", str(pid)]).split()
    if len(ps) < 2:
        return None
    # `footprint` is macOS only; elsewhere only RSS is reported.
    return ps[1], parse_footprint(_run(["footprint", str(pid)])), int(ps[0]) / 1024


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pid", type=int)
    ap.add_argument("--minutes", type=float, default=40)
    ap.add_argument("--step", type=float, default=120)
    a = ap.parse_args(argv)
    pid = a.pid or viewer_pid()
    if not pid:
        print("mem_sample: no process listening on %d" % PORT)
        return 2
    n = int(a.minutes * 60 // a.step) + 1
    fps, rss = [], []
    for i in range(n):
        s = sample(pid)
        if s is None:
            print("mem_sample: pid %d exited" % pid)
            break
        etime, fp, rs = s
        if fp is not None:
            fps.append(fp)
        rss.append(rs)
        print("%s age=%s footprint_mb=%s rss_mb=%.0f" % (time.strftime("%H:%M:%S"), etime,
                                                        "-" if fp is None else "%.0f" % fp, rs), flush=True)
        if i < n - 1:
            time.sleep(a.step)
    if not rss:
        return 1
    fp_s = ("footprint min/median/max %.0f/%.0f/%.0f MB" % (min(fps), statistics.median(fps), max(fps))
            if fps else "footprint n/a")
    print("mem_sample: pid %d · %d samples · %s · rss median %.0f MB" % (pid, len(rss), fp_s, statistics.median(rss)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
