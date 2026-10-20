#!/usr/bin/python3
"""Measure whether one mailbox session reacts to a DM without human input, and how fast.

usage: mail_react_probe.py --to <id> [--timeout 600] [--from probe-sender] [--poll 1] [--dry-run]
Sends one DM `[probe] <nonce>` from a throwaway sender, then watches read-only:
  read  = the target's read-<id>.cursor reaches the probe's t (time = cursor file mtime),
  reply = a bus row containing the nonce, not the probe itself and not from the sender (time = row t).
Prints one line: target platform sent_at read_after_s reply_after_s (a missing one = TIMEOUT).
Exit 0 when a reply arrived, 1 on timeout, 2 on bad arguments.
Test harness only: it writes one bus row and never touches a CLI, a terminal or a hook config.
"""
import argparse
import datetime
import json
import os
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
from sidereus.bus import _open_append  # noqa: E402  same 0600 single-line O_APPEND writer the viewer uses
import mailbox_stop as MS  # noqa: E402  same tail/cursor readers the Stop hooks use

BUS_TAIL = 2 * 1024 * 1024     # the reply lands after the probe, so the tail always covers it
SENDER_PREFIX = "probe-"       # ⚠the sender must be a throwaway id: replies go to it and nobody reads it


def data_dir():
    return MS.data_dir()


def make_probe(to, sender, nonce, now_ns):
    """Same key set as the mailbox MCP server's _post() (projects/mailbox-mcp server.py), so every reader parses it."""
    return {"id": uuid.uuid4().hex[:8], "t": now_ns, "from": sender, "idSrc": "probe", "to": to, "room": None,
            "subject": "[probe] %s" % nonce, "thread": "probe:%s" % nonce,
            "body": ("Mailbox reaction probe. Reply now with mailbox_send(to=\"%s\", body=\"PONG %s\"). "
                     "Nothing else is needed." % (sender, nonce))}


def send(store, msg):
    with _open_append(os.path.join(store, "bus.jsonl")) as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


def platform_of(store, who):
    """claude | codex | gemini | unknown — identity.json key prefix first, then the launcher's `-<cli>` suffix."""
    ident = MS.load(os.path.join(store, "identity.json"), {})
    keys = [k for k, v in ident.items() if v == who] if isinstance(ident, dict) else []
    for k in keys:
        for p in ("codex", "gemini"):
            if k.startswith(p + ":"):
                return p
    if keys:
        return "claude"
    for p in ("codex", "gemini"):
        if who.endswith("-" + p):
            return p
    return "unknown"


def read_at(store, who, probe_t):
    """Epoch seconds the cursor passed the probe (file mtime), or None."""
    p = os.path.join(store, "read-%s.cursor" % who)
    if MS.read_int(p) < probe_t:
        return None
    try:
        return os.path.getmtime(p)
    except OSError:
        return None


def reply_t(store, probe, nonce):
    """t (ns) of the first reply row carrying the nonce, or None."""
    for m in MS.tail_rows(os.path.join(store, "bus.jsonl"), BUS_TAIL):
        try:
            t = int(m.get("t") or 0)
        except Exception:
            continue
        if (t > probe["t"] and m.get("id") != probe["id"] and m.get("from") != probe["from"]
                and nonce in str(m.get("body") or "")):
            return t
    return None


def watch(store, probe, nonce, timeout, poll=1.0, clock=time.time, sleep=time.sleep):
    """Poll until a reply or the timeout. Returns {read_s, reply_s} (None = not seen)."""
    sent_s = probe["t"] / 1e9
    read_s = reply_s = None
    while True:
        if read_s is None:
            r = read_at(store, probe["to"], probe["t"])
            if r is not None:
                read_s = max(0.0, r - sent_s)
        if reply_s is None:
            t = reply_t(store, probe, nonce)
            if t is not None:
                reply_s = (t - probe["t"]) / 1e9
                if read_s is None:
                    read_s = reply_s      # posting proves reading; the cursor write may lag the bus row
        if reply_s is not None or clock() - sent_s >= timeout:
            return {"read_s": read_s, "reply_s": reply_s}
        sleep(poll)


def line(to, platform, probe, res):
    def f(v):
        return "TIMEOUT" if v is None else "%.1f" % v
    sent = datetime.datetime.fromtimestamp(probe["t"] / 1e9).isoformat(timespec="seconds")
    return "target=%s platform=%s sent_at=%s read_after_s=%s reply_after_s=%s" % (
        to, platform, sent, f(res["read_s"]), f(res["reply_s"]))


def main(argv=None, store=None):
    ap = argparse.ArgumentParser(description="Mailbox reaction probe")
    ap.add_argument("--to", required=True)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--from", dest="sender", default="probe-sender")
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not a.sender.startswith(SENDER_PREFIX):
        print("--from must start with %r (throwaway sender)" % SENDER_PREFIX, file=sys.stderr)
        return 2
    if a.to == a.sender:
        print("--to equals --from", file=sys.stderr)
        return 2
    store = store or data_dir()
    nonce = uuid.uuid4().hex[:10]
    probe = make_probe(a.to, a.sender, nonce, time.time_ns())
    platform = platform_of(store, a.to)
    if a.dry_run:
        print(json.dumps(probe, ensure_ascii=False))
        print("dry-run: target=%s platform=%s store=%s (nothing written)" % (a.to, platform, store))
        return 0
    send(store, probe)
    res = watch(store, probe, nonce, a.timeout, a.poll)
    print(line(a.to, platform, probe, res))
    return 0 if res["reply_s"] is not None else 1


if __name__ == "__main__":
    sys.exit(main())
