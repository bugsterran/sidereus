"""Mailbox bus files: atomic writes, messages, cursors, acks and presence."""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
from sidereus.config import BUS, CODE_DIR, DATA_DIR, viewer_ids
from sidereus.warn import warn_once

def _load(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default              # optional file missing or mid-write: caller's default


_ATOMIC_TRIES = 3         # ⚠on Windows `os.replace` raises PermissionError while the target is open — on Mac the first try succeeds, zero delay
_ATOMIC_WAIT = 0.05


def _atomic_write(path, data, tmp=None, prefix=".tmp-", mkdir=False, mode=None, like=None):
    """Write to tmp and swap in with `os.replace` — a crash midway never leaves a half file.

    ⚠`data` is **bytes**. Encoding and `json.dump` args (`ensure_ascii`, `indent`, `separators`)
      differ per call site and that difference IS the file format, so the wrapper must not absorb them — the caller builds the bytes.
    With `tmp`, that name is used; otherwise `mkstemp` in the target folder with `prefix`.
    On failure tmp is removed and the exception **re-raised** (never swallowed — that is the caller's policy).
    tmp is 0600; `like` (existing path) copies its mode, else `mode` (int) — for user-visible files that must stay 0644.
    """
    d = os.path.dirname(path) or "."
    if mkdir:
        os.makedirs(d, exist_ok=True)
    made = None
    try:
        if tmp is None:
            fd, tmp = tempfile.mkstemp(dir=d, prefix=prefix)
            made = tmp
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        else:
            made = tmp
            with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
                f.write(data)
            os.chmod(tmp, 0o600)    # ⚠a leftover tmp keeps its old mode through O_CREAT
        if like is not None and os.path.exists(like):
            mode = os.stat(like).st_mode & 0o7777
        if mode is not None:
            os.chmod(tmp, mode)
        for i in range(_ATOMIC_TRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if i == _ATOMIC_TRIES - 1:
                    raise
                time.sleep(_ATOMIC_WAIT)
    except BaseException:   # ⚠KeyboardInterrupt/SystemExit mid-write also left stray tmp files; SIGKILL still can (see .gitignore)
        if made:
            try:
                os.unlink(made)
            except OSError:
                pass                # tmp already gone; the original error is re-raised below
        raise


def _save_json(name, data):
    """Atomically write JSON in STORE — the MCP server reads the same file, so no half-written state."""
    path = os.path.join(DATA_DIR, name)
    _atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _save_json_bak(path, data):
    """Like `_save_json` for an absolute path, keeping the previous file as `<path>.bak` (one-step undo)."""
    if os.path.exists(path):
        shutil.copyfile(path, path + ".bak")
    _atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _open_append(path):
    """Text append handle; a newly created file is 0600 (data files are private). Existing files keep their mode."""
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a", encoding="utf-8")


def ensure_bus(path=None):
    """Create an empty bus.jsonl (0600) if missing. ⚠A fresh install has none, and a missing bus reads as a «bus» health warning."""
    path = path or BUS
    if os.path.exists(path):
        return
    try:
        _open_append(path).close()
    except OSError:
        pass            # data dir missing or read-only: messages() still warns once


def _bus_append(rec):
    """Append one line to the bus. Append-only log, so plain append suffices (several processes write)."""
    with _open_append(BUS) as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ★Parse cache for the append-only logs (2026-09-25): re-parsing bus.jsonl + acks.jsonl was ~85% of a warm
#   /api/state build. Key = (path, ino, mtime_ns, size) so a rewrite/replace misses.
# ⚠Only file-derived data goes in; `since` and `_ack_cut()` are applied per call. Never hand out cached objects.
_parse_lock = threading.Lock()
_parse_cache = {}


def _file_key(path):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return (path, None)          # fresh install: a missing file is its own (empty) state, not an error
    return (path, st.st_ino, st.st_mtime_ns, st.st_size)


def _cached(path, build):
    """build() result for path's current stat. Stat is taken before the read, so a stale key only causes a later miss."""
    key = _file_key(path)
    with _parse_lock:
        hit = _parse_cache.get(path)
        if hit and hit[0] == key:
            return hit[1]
    val = build()
    if val[-1] is None:              # last item = read error; a failed/partial read is never cached
        with _parse_lock:
            _parse_cache[path] = (key, val)
    return val


def _bus_parse():
    """([(t, raw line)] sorted by t (stable), unreadable-line count, read error). Raw lines so each call gets fresh objects."""
    rows, bad, err = [], 0, None
    try:
        with open(BUS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except Exception:
                    bad += 1        # ★never drop silently — a broken line is lost data
                    continue
                rows.append((int(m.get("t", 0)), line))
    except FileNotFoundError:
        rows = []                   # fresh install: no bus.jsonl yet = no messages, silent
    except Exception as e:
        err = e                     # ⚠keep the rows read so far, as the uncached reader did
    rows.sort(key=lambda r: r[0])
    return rows, bad, err


def messages(since=0):
    """Messages after since (t, ns). The parse is cached, but **the response is incremental**, so the screen is not redrawn wholesale."""
    out = []
    try:
        rows, bad, err = _cached(BUS, _bus_parse)
        out = [json.loads(line) for t, line in rows if t > since]
        if err is not None:
            raise err
        if bad:
            warn_once(f"badlines:{bad}", "bus.jsonl has {n} unreadable lines — they are missing from the screen.",
                      vars={"n": bad})
    except Exception as e:
        warn_once("bus", "Could not read bus.jsonl ({err}) — the chat looks empty.",
                  vars={"err": f"{type(e).__name__}: {e}"})
    return out


# ★First load (`since=0`) carried every body: 2,942,050B for 1013 posts (measured 2026-09-28). Only the newest
#   MSG_FIRST keep bodies; older posts go as `stub` rows (metadata, no `body`) so threads/counts/verdicts still see them.
# ⚠The feed fetches stub bodies on demand (`messages_range` via /api/messages) — never drop the stub rows themselves.
MSG_FIRST = 200
# ★/api/messages with no `n` returned the newest 1000 full posts (2,569,072B measured 2026-10-05).
#   ⇒ Without `n` the reply is the first-load body window (MSG_FIRST); MSG_RANGE_MAX = the feed's HYD_N (10-feed.js),
#   the hard cap for any caller. ⚠Lowering the cap below HYD_N breaks the feed's «truncated» floor (got.length >= HYD_N).
MSG_RANGE_DEFAULT = MSG_FIRST
MSG_RANGE_MAX = 1000


def messages_first(n=MSG_FIRST):
    """All posts; bodies only on the newest `n`, older ones as {..., "stub": 1} without `body`."""
    out = messages(0)
    cut = max(0, len(out) - n)
    for m in out[:cut]:
        m.pop("body", None)
        m["stub"] = 1
    return out


def messages_range(after=0, before=None, n=MSG_RANGE_DEFAULT):
    """Full posts with after < t < before, newest `n` of them (ascending) — the feed's «Earlier posts» body fetch."""
    out = [m for m in messages(after) if before is None or int(m.get("t", 0)) < before]
    return out[-max(1, min(int(n), MSG_RANGE_MAX)):]


def cursors():
    out = {}
    for p in glob.glob(os.path.join(DATA_DIR, "read-*.cursor")):
        who = os.path.basename(p)[len("read-"):-len(".cursor")]
        try:
            out[who] = int(open(p, encoding="utf-8", errors="replace").read().strip())
        except (OSError, ValueError):
            pass                    # vanished or half-written cursor: treat that reader as unread
    return out


ACK_NOTE_MAX = 60          # ★the UI (receipt()) only uses `note.slice(0,60)` — anything longer is discarded
# ★Only this recent window of acks is sent (2026-09-23). The file (`acks.jsonl`) is untouched — trimmed in the response only.
#   Measured: the full set, 251,128B (93% of the response), went out every 2.5 s ⇒ 7 days = 12,590B (-95%).
# ⚠Bubbles in the cut window are **"no record"**, not "unread" — `acksSince` is sent too so the UI
#   says so (receipt()). Widening grows the response again (30 days = 124,401B).
ACK_KEEP_S = 7 * 86400


def _ack_cut():
    """Ack records before this time (ns) are not sent — the UI gets the same value to choose its wording."""
    return time.time_ns() - ACK_KEEP_S * 10 ** 9


def ack_map():
    """Message id -> delivered/acked. Recording without **showing** leaves the trust problem as is.

    ★Fields the UI does not read are not sent (measured 2026-09-22): `acks` was 846,069B (98%) of an
      863,507B incremental response, `note` alone 711,810B. JS reads only `who`, `note` (60 chars), `delivered`;
      `at` is never used ⇒ drop `at` + cut note at 60 chars.
    ⚠If the UI starts using `at` (or text past 60 chars), restore it here."""
    try:
        if CODE_DIR not in sys.path:    # ⚠called per poll: an unconditional insert grew sys.path forever
            sys.path.insert(0, CODE_DIR)
        import mailbox_core
        # ⚠mailbox_core.acks() swallows read errors, so a partial parse stays cached until the file changes
        parsed, _ = _cached(mailbox_core.ACKS, lambda: (mailbox_core.acks() or {}, None))
        out = {}
        cut = _ack_cut()
        for mid, e in parsed.items():
            if int(e.get("t") or 0) <= cut:
                continue                       # outside the retention window — still in the file
            slim = []
            for a in (e.get("ack") or []):
                n = a.get("note")
                # no truncation marker (JS also cuts without ellipsis) — display unchanged
                slim.append({"who": a.get("who"),
                             "note": n[:ACK_NOTE_MAX] if isinstance(n, str) else n})
            out[mid] = {"delivered": list(e.get("delivered") or []), "ack": slim}   # copy: cached list
            if e.get("hooked"):   # only when present — keeps the incremental response small
                out[mid]["hooked"] = list(e["hooked"])
        return out
    except Exception as e:
        warn_once("ack-map", "ack map failed ({err}) — delivered/ack marks are missing",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return {}


def presence():
    """Id -> presence. mailbox_core is the source of truth (same rule as watcher and MCP)."""
    try:
        if CODE_DIR not in sys.path:    # ⚠called per poll: an unconditional insert grew sys.path forever
            sys.path.insert(0, CODE_DIR)
        from mailbox_core import presence as core_presence
        return core_presence()
    except Exception as e:
        warn_once("presence", "Could not read the presence log ({err}) — participant status on screen goes blank.",
                  vars={"err": f"{type(e).__name__}: {e}"})
        return {}


DM_MAX = 20_000            # work-log DMs are typed by hand; the chat tab's 200 KB cap is for pasted logs
RELAY_SID = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$")   # session id carried by a review/board relay


DM_THREAD = re.compile(r"^[\w가-힣][\w가-힣 .·:\-]{0,59}$")   # optional named thread: short label, no control chars


CODEX_ENV_ID = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_.-]{0,62}-codex$")   # launcher id `<basename>-codex`; no path separators
_codex_ok = None   # launcher ids judged sendable by ext.codex_env_dedupe on the last poll; ⚠None = no poll yet -> refuse


def codex_ok_set(ids):
    """Publish the sendable Codex launcher ids (owned here so dm_target_error needs no upward import)."""
    global _codex_ok
    _codex_ok = frozenset(i for i in ids if isinstance(i, str))


def codex_id_ok(mbox, ident=None):
    """Static checks on a Codex MCP launcher id (`MAILBOX_ME=<basename>-codex`, env source in the mailbox server):
    charset (no path separators / ``..``) and not an id a Claude session owns (non-`codex:` identity value, 2026-08-12 rule)."""
    if not isinstance(mbox, str) or not CODEX_ENV_ID.match(mbox) or ".." in mbox:
        return False
    if ident is None:
        ident = _load("identity.json", {})
    ident = ident if isinstance(ident, dict) else {}
    return mbox not in {v for k, v in ident.items() if not str(k).startswith("codex:")}


def codex_cursor(mbox):
    """`read-<id>.cursor` exists: the session has read this inbox at least once. Call only after codex_id_ok."""
    return os.path.isfile(os.path.join(DATA_DIR, "read-%s.cursor" % mbox))


def codex_env_ok(mbox, ident=None):
    """True when the last poll published `mbox` as sendable and it still passes the static checks.
    ⚠Not a folder guess: the reader proof (hook-fed row or read cursor) and uniqueness are judged in ext.codex_env_dedupe."""
    return _codex_ok is not None and mbox in _codex_ok and codex_id_ok(mbox, ident)


def dm_target_error(to, me):
    """None when `to` may receive a viewer DM, else the refusal text. Shared by dm_send and /api/say replies."""
    # ⚠Self first: while viewer_me is a default, «user» and «user» are both the viewer (config.viewer_ids).
    if to and to in viewer_ids(me):
        return "Sender and recipient are the same"
    ident = _load("identity.json", {})
    known = set(ident.values()) if isinstance(ident, dict) else set()
    # A Codex launcher id with a reader is declared by the launcher env, not guessed — checked here, never from mboxSrc.
    if to and to not in known and codex_env_ok(to, ident):
        return None
    if not to or to not in known:
        return "Not logged into the mailbox — cannot receive"
    return None


def dm_send(req, me):
    """Direct message from the viewer identity `me` to one mailbox id (work log compose, 2026-09-24).
    ⚠Only ids a session confirmed via `mailbox_login` (identity.json values) — never a folder-name guess (2026-08-12 incident)."""
    to = str((req or {}).get("to") or "").strip()
    body = str((req or {}).get("body") or "").strip()
    if not body:
        return {"ok": False, "error": "Empty posts are not sent"}
    if len(body) > DM_MAX:
        return {"ok": False, "error": "The message is too long"}
    bad = dm_target_error(to, me)
    if bad:
        return {"ok": False, "error": bad}
    relay = (req or {}).get("relay") is True
    sid = (req or {}).get("sid")
    if relay and sid is not None and (not isinstance(sid, str) or not RELAY_SID.match(sid)):
        return {"ok": False, "error": "Invalid session id"}
    th = (req or {}).get("thread")
    # A named thread groups relays (structure warnings)
    if th is not None and (not isinstance(th, str) or not DM_THREAD.match(th)):
        return {"ok": False, "error": "Invalid thread name"}
    mid =uuid.uuid4().hex[:8]
    msg = {"id": mid, "t": time.time_ns(), "from": me, "idSrc": "viewer", "to": to, "room": None,
           "subject": None, "thread": th or "wk:" + mid, "body": body}
    if relay:   # ⚠hooks/mailbox_stop.py delivers kind=relay + idSrc=viewer at the session's next Stop; plain DMs keep the old key set
        msg["kind"] = "relay"
        msg["sid"] = sid
    _bus_append(msg)
    return {"ok": True, "id": mid, "to": to}


THREAD_MAX = 200           # thread names are short labels; anything longer is not a real key
CLOSE_SUBJECT = "[마침] 정리"


def thread_close(req, me):
    """Viewer «Clear»: append a done-tag post to every open (room|dm, thread) key named `thread`, so thread_state reads it closed.
    Closing alone left stale threads with no way to clear them.
    ⚠The target room/recipient comes from the thread's own posts, never from the request — only the name is trusted."""
    th = (req or {}).get("thread") if isinstance(req, dict) else None
    if not isinstance(th, str) or not th.strip() or len(th) > THREAD_MAX or any(ord(c) < 32 or ord(c) == 127 for c in th):
        return {"ok": False, "error": "Invalid thread name"}
    th = th.strip()
    if CODE_DIR not in sys.path:    # ⚠called per poll: an unconditional insert grew sys.path forever
        sys.path.insert(0, CODE_DIR)
    import mailbox_core
    rows = [m for m in messages() if (m.get("thread") or "").strip() == th]
    if not rows:
        return {"ok": False, "error": "No such thread"}
    keys = [k for k, v in mailbox_core.thread_state(rows).items() if not v.get("closed")]
    ids = []
    for room, _t in sorted(keys):
        dm = room.startswith("dm:") and not any(m.get("room") == room for m in rows)
        to = room[3:] if dm else None
        mid = uuid.uuid4().hex[:8]
        _bus_append({"id": mid, "t": time.time_ns(), "from": me, "idSrc": "viewer",
                     "to": (None if to in (None, "None") else to), "room": None if dm else room,
                     "subject": CLOSE_SUBJECT, "thread": th, "body": "뷰어에서 방치 스레드를 정리했습니다."})
        ids.append(mid)
    return {"ok": True, "ids": ids, "closed": len(ids)}
