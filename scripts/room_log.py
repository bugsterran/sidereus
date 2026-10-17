#!/usr/bin/python3
"""Print one mailbox room's messages from bus.jsonl, oldest first — the input of the room-minutes skill.

usage: room_log.py <room> [--since <ISO|ns>] [--from-doc <path> | --doc-dir <dir>] [--bus <path>]
  --since     keep messages after this time (ISO 8601, naive = local time, or epoch ns).
  --from-doc  keep messages after the LAST `<!-- room-minutes: room=<r> until=<t_ns> last=<id> -->` marker in the file
              (t > until, or t == until with id != last); only markers whose room equals <room>. A missing file or
              no marker = no cut; an unparseable marker = one stderr warning.
  --doc-dir   use <dir>/<slug>.md as --from-doc (when it exists) and print it as doc= in the header.
  --bus       bus file (default: mailbox_core.BUS).
Output: a header line `# room=<r%> slug=<safe> after=<iso|-> n=<N> from=<iso|-> to=<iso|-> until=<t_ns> last=<id> doc=<path|->` (r% = percent-encoded), then one tab-separated line
per message: local time, sender, id, `[D]` for a tagged decision (else empty), `subject — body` with newlines escaped.
Only that room's messages; DMs (room null) and other rooms never appear. Exit 2 on a bad slug or an unknown room.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mailbox_core  # noqa: E402  (path set just above)

# Decision tags: the Korean tag (colon or bracket form) and the English one.
DECISION_TAGS = ("\uacb0\uc815:", "[\uacb0\uc815]", "Decision:", "[Decision]")
MARKER_ANY = re.compile(r"<!--\s*room-minutes:(.*?)-->", re.S)
MARKER = re.compile(r"\s*room=(\S+)\s+until=(\d+)\s+last=(\S+)\s*")


def room_field(room):
    """Room as written in the header and marker: percent-encoded so spaces etc. round-trip through `\\S+`."""
    return urllib.parse.quote(room, safe="")


def slug(room):
    """File-safe name for docs/decisions/<slug>.md; None when nothing usable is left."""
    s = re.sub(r"[^A-Za-z0-9._-]", "_", room or "")
    return None if s in ("", ".", "..") else s


def fmt_t(t_ns):
    """Local ISO time (seconds) of an epoch-ns stamp."""
    return datetime.datetime.fromtimestamp(int(t_ns) / 1e9).astimezone().isoformat(timespec="seconds")


def parse_since(s):
    """Epoch ns from digits or an ISO time (naive = local); ValueError otherwise."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.astimezone()
    return int(d.timestamp()) * 10**9 + d.microsecond * 1000


def last_marker(path, room):
    """(until_ns, last_id) of the last marker for this exact room in the doc, or None.

    ⚠Rooms that share a slug share a doc, so another room's marker must never cut this one.
    """
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    hit = None
    for body in MARKER_ANY.findall(text):
        m = MARKER.fullmatch(body)
        if not m:
            print(f"room_log: unparseable room-minutes marker in {path}: {body.strip()[:80]!r}", file=sys.stderr)
            continue
        if urllib.parse.unquote(m.group(1)) == room:
            hit = (int(m.group(2)), m.group(3))
    return hit


def text_of(r):
    subj, body = (r.get("subject") or "").strip(), (r.get("body") or "").strip()
    s = f"{subj} \u2014 {body}" if subj and body else (subj or body)
    return s.replace("\\", "\\\\").replace("\r\n", "\n").replace("\n", "\\n").replace("\t", "\\t")


def is_decision(text):
    return any(tag in text for tag in DECISION_TAGS)


def known_room(room):
    try:
        with open(mailbox_core.ROOMS, encoding="utf-8") as f:
            return room in json.load(f)
    except (OSError, ValueError, TypeError):
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print one mailbox room's messages, oldest first.")
    ap.add_argument("room")
    ap.add_argument("--since")
    ap.add_argument("--from-doc")
    ap.add_argument("--bus")
    ap.add_argument("--doc-dir", help="minutes folder; <dir>/<slug>.md is used as --from-doc when it exists")
    a = ap.parse_args(argv)
    sl = slug(a.room)
    if sl is None:
        print(f"room_log: unusable room name {a.room!r}", file=sys.stderr)
        return 2
    msgs = sorted((r for r in mailbox_core.rows(a.bus) if r.get("room") == a.room),
                  key=lambda r: (int(r.get("t") or 0), str(r.get("id") or "")))
    if not msgs and not known_room(a.room):
        print(f"room_log: unknown room {a.room!r}", file=sys.stderr)
        return 2
    cut, cut_id = None, None
    if a.since:
        try:
            cut = parse_since(a.since)
        except ValueError:
            print(f"room_log: bad --since {a.since!r}", file=sys.stderr)
            return 2
    doc = a.from_doc
    if a.doc_dir:
        doc = os.path.join(os.path.abspath(a.doc_dir), sl + ".md")
    if doc and os.path.isfile(doc):
        m = last_marker(doc, a.room)
        if m and (cut is None or m[0] >= cut):
            cut, cut_id = m
    if cut is not None:
        # ⚠Equal t with a different id is new: two posts can share one ns stamp after a merge.
        msgs = [r for r in msgs if int(r.get("t") or 0) > cut
                or (cut_id is not None and int(r.get("t") or 0) == cut and str(r.get("id")) != cut_id)]
    until = int(msgs[-1].get("t") or 0) if msgs else (cut or 0)
    last = str(msgs[-1].get("id")) if msgs else (cut_id or "-")
    after = fmt_t(cut) if cut is not None else "-"
    # doc= goes last: a path may contain spaces.
    # from/to = first/last new message in the TSV time format, so the skill copies the heading and never converts ns.
    frm, to = (fmt_t(msgs[0].get("t") or 0), fmt_t(msgs[-1].get("t") or 0)) if msgs else ("-", "-")
    try:
        print(f"# room={room_field(a.room)} slug={sl} after={after} n={len(msgs)} from={frm} to={to}"
              f" until={until} last={last} doc={doc or '-'}")
        for r in msgs:
            t = text_of(r)
            print("\t".join([fmt_t(r.get("t") or 0), str(r.get("from") or ""), str(r.get("id") or ""),
                             "[D]" if is_decision(t) else "", t]))
        sys.stdout.flush()
    except BrokenPipeError:
        # ⚠`| head` closes the pipe early; point stdout at devnull so the exit-time flush does not raise again.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(main())
