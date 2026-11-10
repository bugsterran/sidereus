#!/usr/bin/env python3
"""pi mail waiter: a child of the Sidereus pi extension that tells it when to start one «[mailbox]» turn.

Spawned by ext-hooks/pi-extension.ts (argv: session_id cwd; stdin/stdout pipes). hooks/mail_wait.py
WAKE["pi"] == "extension-turn".
Protocol (one JSON line out, then exit):
- {"wake": "<decide() line>"} when mail arrives; the extension answers "ok" (it called pi.sendUserMessage) or "no".
  Only "ok" within ACK_S marks the mail surfaced (shared read cursor with the turn-end line), else it stays unread.
- {"end": "timeout"} after LIFE_S: the extension re-arms without a model turn.
- {"end": "off"} when this session has no usable id (Claude-id clash) or watch.sh already watches it.
- argv[3] "quiet" (re-arm after a refused wake): mail already pending at the first hit only sets a floor; only mail
  newer than it wakes. ⚠Without it the refused mail (still unmarked) would fire again within FIRST_S, a loop.
- Nothing when the slot is busy/lost or stdin closed (extension gone, session busy, shutdown).
Rules:
- ⚠The wake text is decide()'s line only (ids, room names, a count): never a subject or body, never extension input.
- ⚠Waiting costs no model call: hooks/mail_wait.wait polls bus.jsonl; one waiter per session id (lock slot).
- ⚠SIGTERM (extension kill) raises SystemExit so mail_wait's finally frees the lock slot; a stale slot would make
  the next re-arm read «busy» for STALE_S and drop that waiter.
- Never raises; Python 3.9 syntax.
"""
import json
import os
import queue
import signal
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "hooks"))
sys.path.insert(0, _HERE)
import mailbox_stop as ms  # noqa: E402
import mail_wait as mw  # noqa: E402
import gemini_mail_stop as gms  # noqa: E402

LIFE_S = 6 * 3600
FIRST_S = 1.0
ACK_S = 10.0


class _Gone(Exception):
    pass


def _reader(stream, acks, gone):
    try:
        for line in iter(stream.readline, ""):
            acks.put(line.strip())
    except Exception:
        pass
    gone.set()
    acks.put(None)


def _emit(out, obj):
    out.write(json.dumps(obj, ensure_ascii=False) + "\n")
    out.flush()


def _ack(acks, wait_s, clock):
    """True only when the extension answered "ok" within wait_s."""
    end = clock() + wait_s
    while True:
        left = end - clock()
        if left <= 0:
            return False
        try:
            a = acks.get(timeout=left)
        except queue.Empty:
            return False
        if a is None or a == "no":
            return False
        if a == "ok":
            return True


def run(sid, cwd, store=None, stdin=None, stdout=None, sleep=time.sleep, clock=time.monotonic, ack_s=ACK_S, quiet=False):
    """Return a short outcome tag (for tests); never raises."""
    try:
        out = stdout or sys.stdout
        if not sid or not all(c.isalnum() or c in "-_" for c in sid) or not cwd:
            return "bad-args"
        gms.set_platform("pi")
        store = store or ms.data_dir()
        me = gms.gemini_id(cwd, ms.load(os.path.join(store, "identity.json"), {}))
        if not me or ms.watch_alive(store, me):
            _emit(out, {"end": "off"})
            return "off"
        acks, gone = queue.Queue(), threading.Event()
        t = threading.Thread(target=_reader, args=(stdin or sys.stdin, acks, gone))
        t.daemon = True
        t.start()
        inp = {"session_id": sid, "cwd": cwd}
        hold = {}
        floor = [None]

        def check():
            if gone.is_set():
                return "gone"
            gms.T0 = time.monotonic()      # ⚠decide() gives up after BUDGET_S from T0
            hold.clear()
            # ⚠hold: mark surfaced only after the extension acks the turn, else the mail would be lost.
            got = gms.decide(inp, store=store, hold=hold)
            if quiet and floor[0] is None:
                # ⚠Floor from the first check, mail or not: a floor taken at a later first hit would swallow new mail.
                floor[0] = hold["newest"] if got else 0
                return None
            if got and quiet and hold["newest"] <= floor[0]:
                return None
            return got

        def nap(s):
            if gone.is_set():
                raise _Gone()
            sleep(s)
            if gone.is_set():
                raise _Gone()
        try:
            got, val = mw.wait(store, sid, me, check, LIFE_S, first_s=FIRST_S, sleep=nap, clock=clock,
                               retry_s=mw.RETRY_S)
        except _Gone:
            return "gone"
        if got == "timeout":
            _emit(out, {"end": "timeout"})
            return "timeout"
        if got != "hit":
            return got
        if val == "gone":
            return "gone"
        _emit(out, {"wake": val})
        if not _ack(acks, ack_s, clock):
            return "rejected"
        gms.mark_surfaced(ms.state_path(store, gms.KEY_PREFIX + sid), hold["newest"], hold["me"], hold["at"])
        return "fired"
    except BaseException:
        return "error"


def _term(_sig, _frame):
    raise SystemExit(0)


if __name__ == "__main__":
    for _s in (sys.stdin, sys.stdout):   # ⚠Windows pipes default to the ANSI codepage
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        signal.signal(signal.SIGTERM, _term)
    except Exception:
        pass
    a = sys.argv[1:] + [""] * 3
    run(a[0], a[1], quiet=(a[2] == "quiet"))
    sys.exit(0)
