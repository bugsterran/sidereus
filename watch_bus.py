#!/usr/bin/env python3
"""Mailbox watcher (launchd, always on) — **exits immediately** when a new post for me arrives, waking the session.

Why this way: MCP inbox is visible only when I call it (no push). Background commands are notified **on exit**,
  so "new post = process exit" makes the exit itself the alert. Dying is normal; `watch_loop.sh` restarts it.

Split roles — both watchers must run **together**:
  ①launchd (role=daemon)  : always on, independent of sessions/reboots. Owns loss prevention (cursor).
  ②session Monitor (monitor_stream.py): one line = one alert. Wakes my session immediately.

★Routing lives only in `mailbox_core` — four separate implementations caused incidents via **a fix applied to one side only** (see core comments).
★The cursor is **t (time)**. With line counts, a shrinking file (cleanup/rotation) leaves the baseline behind and silently skips new posts
  (measured: after deleting 2 test lines, alerts were dead for 6 min).
★Posts that arrived while the watcher was dead are announced first as a **gap report** — silently skipping them caused the earlier loss incident.

Usage: WATCH_TIMEOUT=28800 python3 <repo>/watch_bus.py
       WATCH_FORCE=1 cleans up a live watcher and takes over.
Exit codes: 0=new post/gap report/timeout · 3=another watcher already alive (dedupe)
"""
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mailbox_core import HOME, latest_t, my_rooms, new_for_me, rows, where  # noqa: E402
from sidereus.config import pid_alive  # noqa: E402

ROLE = os.environ.get("WATCH_ROLE", "daemon")
SUFFIX = "" if ROLE == "daemon" else f".{ROLE}"
CURSOR = os.path.join(HOME, f".watch-cursor{SUFFIX}")      # content = last seen t
PIDFILE = os.path.join(HOME, f".watch{SUFFIX}.pid")
TIMEOUT_S = int(os.environ.get("WATCH_TIMEOUT", "28800"))  # default 8h — effectively wakes "only on new posts"
POLL_S = int(os.environ.get("WATCH_POLL", "3"))


def alive(pid):
    return pid_alive(pid) is True       # ⚠not os.kill(pid, 0): on Windows that terminates the process


def report(new, prefix):
    print(f"\n★{prefix} {len(new)}건 — 읽어야 한다", flush=True)
    for r in new:
        print(f"  from={r.get('from')} {where(r)} thread={r.get('thread')}", flush=True)
        print(f"  제목: {r.get('subject')}", flush=True)


# ── Single instance — two running means multiple wakes per post and confusion over which one is alive ──
old = None
try:
    old = int(open(PIDFILE).read().strip())
except Exception:
    pass
if old and old != os.getpid() and alive(old):
    if os.environ.get("WATCH_FORCE"):
        try:
            os.kill(old, signal.SIGTERM)
            print(f"기존 감시(PID {old}) 정리 후 새로 시작합니다.", flush=True)
        except OSError:
            pass
    else:
        print(f"이미 감시가 살아 있습니다(PID {old}) — 중복 실행하지 않습니다."
              f" 강제로 잡으려면 WATCH_FORCE=1 로 실행하세요.", flush=True)
        sys.exit(3)
open(PIDFILE, "w").write(str(os.getpid()))

# ── Cursor (t): first check posts that arrived while dead ──
cur = rows()
try:
    seen_t = int(open(CURSOR).read().strip())
except Exception:
    seen_t = latest_t(cur)        # first run — don't re-read the whole past
gap = new_for_me(seen_t, cur)
open(CURSOR, "w").write(str(latest_t(cur)))
if gap:
    report(gap, "감시 공백 중 도착한 글")
    print("(알림 후 종료합니다 — 처리하고 감시를 다시 띄우세요)", flush=True)
    sys.exit(0)

seen_t = latest_t(cur)
print(f"감시 시작[{ROLE}] — bus {len(cur)}줄 · 기준 t={seen_t} · 방 {sorted(my_rooms()) or '없음'}"
      f" · {POLL_S}초 간격 · 만료 {TIMEOUT_S}초 · PID {os.getpid()}", flush=True)
t0 = time.time()
while time.time() - t0 < TIMEOUT_S:
    time.sleep(POLL_S)
    cur = rows()
    new = new_for_me(seen_t, cur)
    seen_t = max(seen_t, latest_t(cur))
    open(CURSOR, "w").write(str(seen_t))     # persist the seen point (next start knows the gap)
    if new:
        report(new, "새 글")
        sys.exit(0)                          # exit = session notification
print("감시 시간 만료 — 재기동 필요(새 글 없었음)", flush=True)
sys.exit(0)
