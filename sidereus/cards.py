"""Task-complete cards store, read marks, session state and recent transcripts."""
import json
import os
import threading
import time
from datetime import datetime
from sidereus.config import DATA_DIR
from sidereus import claude_roots
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write, _open_append
from sidereus.memo import BoundedMemo
from sidereus.transcript import CLAUDE_PROJECTS, _tail_lines, iso_epoch
from sidereus.ident import _slug
from sidereus.live import _sid_transcript, agent_view


# ★Source of the session row's "leftover N" badge — cwd -> count of uncommitted wreckage files.
#   ⚠Never call `wreckage()` from a request thread (cold 0.93 s · warm 0.015 s, measured 2026-09-23).
#   `_fail_loop` (60 s) already warms the same data, so compute it **there, once** ⇒ zero polling cost.
_WRECK_BY_CWD = {}


# ── task-complete cards ───────────────────────────────────────────────────────
#   Requested 2026-08-19: task-complete messages as card alerts on the page.
#   This takes over from the retired external messenger notifications — **they accumulate instead of passing by**; look when you look.
#
#   Two paths:
#     (1) automatic — the moment a session goes from `tool/think` → `done·waiting on question·interrupted` (where a turn ended)
#     (2) explicit — a session leaves one itself via `card.sh "title" "body"` (milestone summary)
#   ⚠Automatic cards carry **a one-line summary only** (last human instruction·tool name·project). Response bodies are not copied.
CARDS = os.path.join(DATA_DIR, "cards.jsonl")
_prev_state = BoundedMemo(600)   # session key -> last state seen
# ★Lock dedicated to card dedup (2026-09-07). `_note_transition` is a **read-modify**
#   decision on `_prev_state[key]` — if two threads see the same «previous state» they leave the same card twice.
#   Previously `state()` called `sessions()` while holding `_lock`, so polls happened to be serialized.
#   Narrowing that lock (cause 4) removes that accident, so **a dedicated lock at the decision point**.
#   ⚠This lock wraps only «decision + one card line append» — never put a slow scan inside.
#   ⚠Ordering rule: do not take this while holding `_lock`·`_sess*` locks (the only place that takes it is the tail of `sessions()`).
_note_lock = threading.Lock()
# ⚠Shared by the append in `_card_add` and the daily trim's rewrite — without it an append between read and replace is lost.
_cards_lock = threading.Lock()
# Cards older than this are dropped from cards.jsonl once a day (⚠must exceed every `_recent_card` within_s window).
CARD_KEEP_S = 7 * 86400
CARD_TRIM_EVERY_S = 86400
_TRIM = {"at": 0.0}
# Auto-expire: past these ages a card counts as read (server-decided so every tab/reload agrees).
CARD_EXPIRE_S = 24 * 3600
FAIL_CARD_EXPIRE_S = 3 * 86400
_FAIL_KINDS = {"flimit", "fcut", "fcheck", "fwreck", "fail"}


def _trim_cards_locked(now=None):
    """Drop lines older than CARD_KEEP_S (caller holds `_cards_lock`). Returns (kept, dropped)."""
    now = time.time() if now is None else now
    cut = datetime.fromtimestamp(now - CARD_KEEP_S).isoformat(timespec="seconds")
    try:
        with open(CARDS, "rb") as f:
            lines = f.read().splitlines(keepends=True)
    except OSError:
        return 0, 0
    keep = []
    for ln in lines:
        try:
            if (json.loads(ln).get("at") or "") < cut:
                continue
        except (ValueError, AttributeError):      # unparsable line: keep (never drop what we cannot date)
            warn_once("cardline", "cards file has an unreadable line — kept as is", soft=True)
        keep.append(ln if ln.endswith(b"\n") else ln + b"\n")
    if len(keep) < len(lines):
        _atomic_write(CARDS, b"".join(keep), prefix=".cards-")
    return len(keep), len(lines) - len(keep)


def _card_add(kind, project, title, text="", cwd="", extra=None):
    row = {"at": datetime.now().isoformat(timespec="seconds"), "kind": kind,
           "project": project or "", "title": title or "", "text": text or "", "cwd": cwd or ""}
    if extra:
        # ⚠Metadata only (ids, harness phrases, counts) — never conversation text.
        row.update({k: v for k, v in extra.items() if k not in row})
    with _cards_lock:
        now = time.time()
        if now - _TRIM["at"] >= CARD_TRIM_EVERY_S:
            _TRIM["at"] = now
            try:
                _trim_cards_locked(now)
            except OSError as e:
                warn_once("cardtrim", "Could not trim old cards ({err}) — the file keeps growing", vars={"err": str(e)})
        try:
            with _open_append(CARDS) as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            warn_once("card", "Could not write a card ({err}) — completion marks are not kept on screen",
                      vars={"err": str(e)})
    return row


def _card_bump(kind, cwd, match, fields, within_s=CARD_EXPIRE_S):
    """Replace the newest recent card of `kind`·`cwd` for which `match(card)` is true with `card + fields(card)` and
    a fresh `at`, moved to the end (the file is read newest-last). Returns the new row, or None when nothing matched.
    ⚠A resumed agent's second completion otherwise lands as a second card, and the group counts one agent twice (2026-09-24)."""
    cut = datetime.fromtimestamp(time.time() - within_s).isoformat(timespec="seconds")
    with _cards_lock:
        try:
            with open(CARDS, "rb") as f:
                lines = f.read().splitlines(keepends=True)
        except OSError:
            return None
        for i in range(len(lines) - 1, -1, -1):
            try:
                c = json.loads(lines[i])
            except ValueError:
                warn_once("cardline", "cards file has an unreadable line — kept as is", soft=True)
                continue
            if (c.get("at") or "") < cut:
                return None                        # newest-last file: everything above is older still
            if c.get("kind") != kind or c.get("cwd") != cwd or not match(c):
                continue
            c.update(fields(c))
            c["at"] = datetime.now().isoformat(timespec="seconds")
            rest = lines[:i] + lines[i + 1:]
            rest = [ln if ln.endswith(b"\n") else ln + b"\n" for ln in rest]
            try:
                _atomic_write(CARDS, b"".join(rest) + (json.dumps(c, ensure_ascii=False) + "\n").encode("utf-8"),
                              prefix=".cards-")
            except OSError:
                return None
            return c
    return None


def _card_expired(c, now):
    t = iso_epoch(c.get("at"), None)
    if t is None:
        return False
    return now - t > (FAIL_CARD_EXPIRE_S if (c.get("kind") or "") in _FAIL_KINDS else CARD_EXPIRE_S)


def cards(limit=40, now=None):
    """Recent cards. If the file grows, read only from the end (append-only, so the front is old).
    Expired cards carry `old: true` — the client treats them as read (badge and unread list)."""
    now = time.time() if now is None else now
    rows = []
    for line in _tail_lines(CARDS, nbytes=120000, limit=limit * 2):
        try:
            c = json.loads(line)
        except ValueError:
            continue                              # ⚠tail read: the first line is cut mid-record — expected, not a fault
        if _card_expired(c, now):
            c["old"] = True
        if c.get("kind") in _TEXTLESS_KINDS:
            c["text"] = ""                        # ⚠old stored transition cards held reply/instruction text (rule 1, 2026-09-25)
        rows.append(c)
    return rows[-limit:][::-1]                    # newest on top


_TEXTLESS_KINDS = ("wait", "ask", "abort")        # session transition cards — body is never sent


READ_MARK = os.path.join(DATA_DIR, "cards-read.txt")
# ★Mark cards read **one at a time** (clicking an unread card marks it read;
#   "mark all read" alone is not enough). One watermark (time) cannot do it — setting it to an old card's time
#   **also marks newer cards read.** So keep a time (mark all) and **a key set** (individual) separately.
#   The key uses the same formula as the screen: `at|kind|project` (cards.jsonl has no id, so derive one — the source stays unchanged).
#   ⚠Stored **on the server, not the browser** — must survive closing the tab (same reason as the watermark).
READ_IDS = os.path.join(DATA_DIR, "cards-read-ids.txt")
# ⚠Lock + atomic swap: overlapping clicks lost a key, and a poll reading mid-truncate saw read cards as unread.
_read_ids_lock = threading.Lock()


def cards_read():
    """Time (ISO) of the last 'mark all read'. Empty string if none — then everything is unread."""
    try:
        with open(READ_MARK, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def cards_read_ids():
    """Individually read card keys. Those older than the watermark are **dropped** (already read, nothing to keep)."""
    mark = cards_read()
    out = []
    try:
        with open(READ_IDS, encoding="utf-8") as f:
            for line in f:
                k = line.strip()
                if k and (not mark or k.split("|")[0] > mark) and k not in out:
                    out.append(k)
    except OSError:
        return []
    return out[-500:]                      # cap — keeps the file from growing forever (older ones are covered by the watermark)


def mark_cards_read(keys_in):
    """Mark many cards read under one lock and one atomic write (bulk read used to be one POST + rewrite per key)."""
    add = []
    for k in keys_in or []:
        k = (k or "").strip() if isinstance(k, str) else ""
        if k and "\n" not in k and k not in add:
            add.append(k)
    if not add:
        return []
    with _read_ids_lock:
        keys = cards_read_ids()
        have = set(keys)
        keys += [k for k in add if k not in have]
        keys = keys[-500:]
        try:
            # rewrite doubling as cleanup (line count capped at 500)
            _atomic_write(READ_IDS, ("\n".join(keys) + "\n").encode("utf-8"), prefix=".cards-read-ids-")
        except OSError as e:
            warn_once("cardread1", "Could not write card read state ({err}) — clicking does not lower the badge",
                      vars={"err": str(e)})
    return keys


def set_cards_read(ts=None):
    ts = ts or datetime.now().isoformat(timespec="seconds")
    # ⚠Same lock as mark_cards_read — otherwise its rewrite can land between our mark and remove (half state).
    with _read_ids_lock:
        try:
            _atomic_write(READ_MARK, ts.encode("utf-8"), prefix=".cards-read-")
        except OSError as e:
            warn_once("cardread", "Could not write read marks ({err}) — the badge stays", vars={"err": str(e)})
        try:
            os.remove(READ_IDS)             # all read, so individual keys are meaningless (leaving the file would confuse)
        except OSError:
            pass                            # already absent
    return ts


def _recent_transcripts(now, max_age_h, live=None):
    """Recently active transcripts [(mtime, path)] — newest first. Unreadable files are skipped.

    ★Cutting by age alone **makes live sessions vanish from the screen** (measured 2026-08-24:
      a session may be left open doing nothing). A session left open and quiet past max_age_h
      does not even show as `Ended`; it drops out of the list entirely. That is worse than leaving a ghost — it says
      what exists does not, leading to relaunching the same session or forgetting the context it holds.
      ⇒ If `live` is given, **the single newest transcript** of that path is included regardless of age.
      (Which one in that path is actually alive is decided by `sessions()` assigning slots per process count.)"""
    files = []
    newest_by_dir = {}
    proots = [p for p in claude_roots.projects_dirs(CLAUDE_PROJECTS) if os.path.isdir(p)]   # every Claude root
    if not proots:
        return []       # ⚠Claude Code has not run on this machine yet: empty list, not a «sessions» health warning
    for pdir in [os.path.join(r, d) for r in proots for d in os.listdir(r)]:
        if not os.path.isdir(pdir):
            continue
        for fn in os.listdir(pdir):
            if not fn.endswith(".jsonl"):
                continue
            fp = os.path.join(pdir, fn)
            try:
                mt = os.path.getmtime(fp)
            except OSError:
                continue
            if now - mt <= max_age_h * 3600:
                files.append((mt, fp))
            elif live:
                # dropped by age — revived below if it is the newest file of a live path
                cur = newest_by_dir.get(pdir)
                if not cur or mt > cur[0]:
                    newest_by_dir[pdir] = (mt, fp)

    if live:
        have = {fp for _mt, fp in files}
        dirs_have = {os.path.dirname(fp) for fp in have}
        for cwd in live:
            pdirs = [os.path.join(r, _slug(cwd)) for r in proots]
            if any(pd in dirs_have for pd in pdirs):
                continue                      # that path already has a recent file
            # ⚠same cwd in two roots: the newest transcript wins (one live slot per path)
            row = max((newest_by_dir[pd] for pd in pdirs if pd in newest_by_dir), default=None)
            if row and row[1] not in have:
                files.append(row)             # quiet but alive — include it
    # ★★**Sessions in the official list are not dropped by age** (2026-09-08).
    #   ⚠The cwd revival above uses `live_cwds()`'s path tally, but pids caught by an official sid are
    #     **excluded** from that tally (claimed) — so sessions known officially were exactly the ones excluded from revival.
    #     Measured: once all 5 pids were caught officially, `live_cwds()` became `{}` ⇒ a session quiet for 12+ hours
    #     was about to vanish from the list (that is "saying what exists does not" — a pitfall this file
    #     already hit on 2026-08-24: a session may be left open doing nothing).
    #   ⇒ **Revive directly by sid.** More accurate than guessing by path; sessions the official list does not know are
    #     still handled by the cwd path above (the two do not overlap and together leave no gap).
    _av = agent_view()
    if _av:
        have2 = {fp for _mt, fp in files}
        for _it in _av.values():
            _sid = (_it.get("sessionId") or "") if isinstance(_it, dict) else ""
            if not _sid:
                continue
            _fp = _sid_transcript(_sid)
            if not _fp or _fp in have2:
                continue
            try:
                files.append((os.path.getmtime(_fp), _fp))
                have2.add(_fp)
            except OSError:
                continue

    files.sort(reverse=True)
    return files
