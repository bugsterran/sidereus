"""Work-log peer check: is the client end of a loopback connection held by a process of the viewer's own UID?"""
import os
import subprocess
import time

from sidereus import config
from sidereus.memo import BoundedMemo

LSOF = "/usr/sbin/lsof"
PEER_TTL_S = 5.0
_peer_memo = BoundedMemo(64)   # client port -> monotonic time of the last allow (refusals are never stored)


def peer_ok(client_address):
    """True when another same-UID process owns the client socket; fail-closed on macOS, always True elsewhere."""
    if not config.IS_MAC:
        return True
    try:
        host, port = client_address[0], int(client_address[1])
    except Exception:
        return False
    if host != "127.0.0.1":
        return False   # ⚠::1 / non-loopback: the lsof filter below is IPv4-only, so refuse rather than guess
    now = time.monotonic()
    hit = _peer_memo.get(port)
    if hit is not None and now - hit < PEER_TTL_S:
        return True
    # ⚠Non-root lsof cannot see other users' sockets, so «no same-UID client end» also covers the other-user case;
    #   match only the client end (ignore the viewer's own accepted socket) and never cache a refusal.
    try:
        r = subprocess.run([LSOF, "-nP", "-a", "-iTCP@127.0.0.1:%d" % port, "-sTCP:ESTABLISHED", "-Fpn"],
                           timeout=1.5, capture_output=True, text=True)
    except Exception:
        return False
    if r.returncode != 0:
        return False
    want, me, pid = "127.0.0.1:%d->127.0.0.1:%d" % (port, config.PORT), os.getpid(), None
    for line in (r.stdout or "").splitlines():
        if line.startswith("p"):
            try:
                pid = int(line[1:])
            except ValueError:
                pid = None
        elif line.startswith("n") and pid is not None and pid != me and line[1:] == want:
            _peer_memo.put(port, now)
            return True
    return False
