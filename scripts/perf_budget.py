#!/usr/bin/env python3
"""Performance budgets: RSS · warm/cold /api/state · `claude agents` spawns per minute.

  perf_budget.py          own `--demo` server on a temp HOME (check.sh --full); exit 1 when any budget is over
  perf_budget.py --live   read-only probe of the running viewer on 127.0.0.1:8799 (release audit; never in check.sh/tests)

Last line: `perf_budget: N budgets, K over — rss 98MB/… · warm p90 12ms/… · cold 340ms/… · agents 1/min/2`.
Stdlib only, Python 3.9.
"""
import json
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_PORT = 8799
# Demo state is synthetic and cheap, so the live table would never trip on it ⇒ ~2x the worst of 3 demo runs.
# ★2026-10-25 demo x3 (macOS, load ~6/12 cpus): rss 65/66/65 MB · warm p90 2/5/2 ms · cold 6/11/6 ms · agents 1/1/1 per min
# ⚠Time budgets = max(2x worst, floor) with floors warm 50 ms · cold 250 ms: a busy machine below the load guard
#   must not trip a 2 ms measurement.
DEMO_FLOORS = {"warm": 50, "cold": 250}
DEMO_BUDGETS = {"rss": 130, "warm": max(2 * 5, DEMO_FLOORS["warm"]), "cold": max(2 * 11, DEMO_FLOORS["cold"]), "agents": 2}
# Live viewer budgets from the issue (#24); cold cannot be measured on an already-running server ⇒ skipped there.
LIVE_BUDGETS = {"rss": 200, "warm": 300, "cold": 2000, "agents": 2}
UNITS = {"rss": "MB", "warm": "ms", "cold": "ms", "agents": "/min"}
LABELS = {"rss": "rss", "warm": "warm p90", "cold": "cold", "agents": "agents"}
ORDER = ("rss", "warm", "cold", "agents")
WARM_DISCARD, WARM_N = 2, 20
READY_S = 15
LOAD_WAIT_S = 10
# ★2026-10-25: load1 hit 12-15 on 12 cpus while parallel agents ran; the 50/250 ms floors absorb that, so only 2x cpus blocks.
LOAD_FACTOR = 2


def p90(xs):
    """Nearest-rank 90th percentile: sorted[ceil(0.9n)-1]; None for an empty list."""
    s = sorted(xs)
    if not s:
        return None
    return s[max(0, math.ceil(0.9 * len(s)) - 1)]


def compare(values, budgets):
    """-> (N measured, [(name, value, limit)] over budget). A None value is skipped and not counted."""
    n, over = 0, []
    for k in ORDER:
        v = values.get(k)
        if v is None or k not in budgets:
            continue
        n += 1
        if v > budgets[k]:
            over.append((k, v, budgets[k]))
    return n, over


def _fmt_one(k, v, lim, labels=None):
    u = UNITS[k]
    lab = dict(LABELS, **(labels or {}))
    if k == "agents":
        return "%s %s/min/%s" % (lab[k], "skipped" if v is None else int(v), lim)
    if v is None:
        return "%s skipped/%s%s" % (lab[k], lim, u)
    return "%s %d%s/%s%s" % (lab[k], round(v), u, lim, u)


def last_line(values, budgets, notes=None, labels=None):
    """One summary line; `notes` = {name: reason} replaces «skipped» for that budget; `labels` overrides LABELS."""
    n, over = compare(values, budgets)
    parts = []
    for k in ORDER:
        if k not in budgets:
            continue
        s = _fmt_one(k, values.get(k), budgets[k], labels)
        if values.get(k) is None and notes and notes.get(k):
            s = "%s %s" % (dict(LABELS, **(labels or {}))[k], notes[k])
        parts.append(s)
    return "perf_budget: %d budgets, %d over — %s" % (n, len(over), " · ".join(parts))


def exit_code(values, budgets):
    n, over = compare(values, budgets)
    return 1 if (over or n == 0) else 0


# ---- measuring -------------------------------------------------------------
def rss_mb(pid):
    """Resident set size in MB, or None (Windows / unreadable)."""
    if os.name == "nt":
        return None
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout
        if out.strip():
            return int(out.split()[0]) / 1024.0
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        with open("/proc/%d/status" % pid, encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("VmRSS:"):
                    return int(ln.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None


def _get_ms(url, timeout=60):
    t0 = time.perf_counter()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        r.read()
    return (time.perf_counter() - t0) * 1000.0


def warm_p90(url):
    for _ in range(WARM_DISCARD):
        _get_ms(url)
    return p90([_get_ms(url) for _ in range(WARM_N)])


def load_guard():
    """None when the machine is quiet enough, else a «load X>Y» reason. Never used to retry a measurement."""
    if os.name == "nt" or not hasattr(os, "getloadavg"):
        return None
    cpus = (os.cpu_count() or 1) * LOAD_FACTOR
    end = time.time() + LOAD_WAIT_S
    while True:
        l1 = os.getloadavg()[0]
        if l1 <= cpus:
            return None
        if time.time() >= end:
            return "load %.1f>%d" % (l1, cpus)
        time.sleep(1)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_tcp(port, secs):
    end = time.time() + secs
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def simulate_agents(lv, cfg_dir, seconds=60.0, tick=2.5, per_tick=3, on_tick=None):
    """Count `claude agents --json` spawns while agent_view() runs `per_tick` times per poll over `seconds`.

    Clock, spawner, accounts and caches are swapped on `lv` (sidereus.live_probe) and restored after.
    `on_tick(t)` runs before each poll (tests change the registry there)."""
    clock, calls = [1000.0], [0]

    class _T(object):
        @staticmethod
        def time():
            return clock[0]

    class _R(object):
        stdout = "[]"

    class _S(object):
        TimeoutExpired = subprocess.TimeoutExpired

        @staticmethod
        def run(*a, **k):
            calls[0] += 1
            return _R()
    names = ("time", "subprocess", "_av_accounts", "bin_path", "rich_env", "warn_once")
    saved = {k: getattr(lv, k) for k in names}
    saved_state = (list(lv._av_cache), list(lv._av_fail), dict(lv._av_sigs))
    try:
        lv.time, lv.subprocess = _T, _S
        lv._av_accounts = lambda: [("", cfg_dir, True)]
        lv.bin_path = lambda n: n
        lv.rich_env = lambda: {}
        lv.warn_once = lambda *a, **k: None
        lv._av_cache[:] = [0.0, None]
        lv._av_fail[:] = [0.0]
        lv._av_sigs.clear()
        t = 0.0
        while t < seconds:
            clock[0] = 1000.0 + t
            if on_tick:
                on_tick(t)
            for _ in range(per_tick):
                lv.agent_view()
            t += tick
    finally:
        for k, v in saved.items():
            setattr(lv, k, v)
        lv._av_cache[:], lv._av_fail[:] = saved_state[0], saved_state[1]
        lv._av_sigs.clear()
        lv._av_sigs.update(saved_state[2])
    return calls[0] * 60.0 / seconds


def _agents_child(cfg_dir):
    sys.path.insert(0, ROOT)
    from sidereus import live_probe
    os.makedirs(os.path.join(cfg_dir, "sessions"), exist_ok=True)
    with open(os.path.join(cfg_dir, "sessions", "%d.json" % os.getpid()), "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "sessionId": "perf-budget", "cwd": cfg_dir}, f)
    print(simulate_agents(live_probe, cfg_dir))


def _agents_per_min(env, cfg_dir):
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--agents-child", cfg_dir],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("agents child failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    return float(r.stdout.strip().splitlines()[-1])


# ⚠ SIGKILL of this process skips `finally` ⇒ the child also exits on stdin EOF (same as scripts/screen_check.mjs).
_WATCHDOG = ("import os,sys,threading,runpy\n"
             "threading.Thread(target=lambda: (sys.stdin.buffer.read(), os._exit(0)), daemon=True).start()\n"
             "sys.argv = sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name='__main__')\n")


def run_demo():
    why = load_guard()
    if why:
        return None, why + ", not measured"
    tmp = tempfile.mkdtemp(prefix="sidereus-perf.")
    proc = None
    try:
        home = os.path.join(tmp, "home")
        data = os.path.join(home, "data")
        cfg = os.path.join(home, ".claude")
        os.makedirs(data)
        env = dict(os.environ, HOME=home, MAILBOX_DIR=data, CLAUDE_CONFIG_DIR=cfg)
        port = _free_port()
        kw = {"start_new_session": True} if os.name != "nt" else {}
        proc = subprocess.Popen([sys.executable, "-c", _WATCHDOG, os.path.join(ROOT, "chat_server.py"),
                                 "--demo", "--no-open", "--port", str(port)],
                                cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, **kw)
        if not _wait_tcp(port, READY_S):
            return None, "demo server not listening after %ds" % READY_S
        url = "http://127.0.0.1:%d/api/state" % port
        vals = {"cold": _get_ms(url, timeout=120)}
        vals["warm"] = warm_p90(url)
        vals["rss"] = rss_mb(proc.pid)
        vals["agents"] = _agents_per_min(env, cfg)
        return vals, None
    finally:
        if proc is not None:
            try:
                if os.name != "nt":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except OSError:
                pass
            proc.wait()
        shutil.rmtree(tmp, ignore_errors=True)


def _listen_pid(port):
    try:
        out = subprocess.run(["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN", "-t"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[0]) if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def run_live():
    """Read-only: GET /api/state on the running viewer and the RSS of its listener. Writes nothing."""
    url = "http://127.0.0.1:%d/api/state" % LIVE_PORT
    vals = {"warm": warm_p90(url), "cold": None, "agents": None}
    pid = _listen_pid(LIVE_PORT)
    vals["rss"] = rss_mb(pid) if pid else None
    return vals


def main(argv):
    if argv[:1] == ["--agents-child"]:
        _agents_child(argv[1])
        return 0
    t0 = time.time()
    if "--live" in argv:
        vals = run_live()
        notes = {"cold": "skipped (running server)", "agents": "skipped (live)"}
        if vals["rss"] is None:
            notes["rss"] = "skipped (Windows)" if os.name == "nt" else "skipped (no listener pid)"
        # ⚠A plain GET /api/state is answered from the server's cache ⇒ live warm p90 is informational only.
        print(last_line(vals, LIVE_BUDGETS, notes, {"warm": "warm p90 (cached)"}))
        return exit_code(vals, LIVE_BUDGETS)
    vals, why = run_demo()
    if vals is None:
        print("perf_budget: 0 budgets, 0 over — FAIL %s" % why)
        return 1
    notes = {"rss": "skipped (Windows)"} if vals.get("rss") is None and os.name == "nt" else {}
    print("perf_budget: measured in %.1fs" % (time.time() - t0))
    print(last_line(vals, DEMO_BUDGETS, notes))
    return exit_code(vals, DEMO_BUDGETS)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
