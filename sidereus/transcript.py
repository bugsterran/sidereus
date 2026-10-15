"""Transcript primitives shared by every domain: tail readers, human-text/noise filters, tool targets, line timestamps."""
import os
import re
import time
from datetime import datetime
from sidereus.config import claude_home


# ── Claude session work state ─────────────────────────────────────────────────
#   Added 2026-08-18: monitor **what Claude sessions are doing now**, not mail. Source is
#   `~/.claude/projects/<slug>/<sessionId>.jsonl` (one line = one event, carrying `cwd`·`gitBranch`·`timestamp`·`type`).
#
#   ★Conversation content never goes on the page — **metadata only** (project, branch, last tool, elapsed).
#     This page is a shared screen; other sessions' prompts and replies belong to those sessions' users.
#   ⚠"working" is an estimate: judged by whether the transcript was just written (last event time).
#     No lines are appended while Claude is only thinking, so it **may briefly look idle** — never assert it.
CLAUDE_PROJECTS = os.path.join(claude_home(), "projects")


def _tail_lines(path, nbytes=200000, limit=300):
    """Read only the last few lines — transcripts reach tens of MB (never parse them whole)."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > nbytes:
                f.seek(size - nbytes)
                f.readline()                      # drop the truncated first line
            raw = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return [l for l in raw.splitlines() if l.strip().startswith("{")][-limit:]


_TSRAW_RE = re.compile(rb'"timestamp":\s*"([^"]+)"')


def _off_after(f, size, at):
    """Byte offset of the first line written after epoch `at` (binary search; lines are append-ordered).
    A probe reads up to 8 lines forward to find one carrying a timestamp; none found = treat as «after»."""
    lo, hi = 0, size
    while hi - lo > 4096:
        mid = (lo + hi) // 2
        f.seek(mid)
        f.readline()                          # drop the partial line
        t = None
        for _ in range(8):
            ln = f.readline()
            if not ln:
                break
            m = _TSRAW_RE.search(ln[:4096])
            if m:
                t = iso_epoch(m.group(1).decode("ascii", "replace"), None)
                if t is not None:
                    break
        if t is not None and t <= at:
            lo = mid
        else:
            hi = mid
    return hi


def _lines_until(path, at, nbytes=200000, limit=300):
    """Like `_tail_lines`, but the window **ends at epoch `at`** (+ the lines just after it) instead of at EOF.
    ⚠Transcripts reach 1GB: never read the whole file — binary-search the offset, then read one `nbytes` window."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            end = min(size, _off_after(f, size, at) + 16384)   # keep the failing result line that follows `at`
            start = max(0, end - nbytes)
            f.seek(start)
            if start:
                f.readline()
            raw = f.read(max(0, end - f.tell())).decode("utf-8", "replace")
    except OSError:
        return []
    ls = [l for l in raw.splitlines() if l.strip().startswith("{")]
    if end < size and ls:
        ls = ls[:-1]                          # the cut last line
    return ls[-limit:]


def _tail_bytes(path, nbytes):
    """(raw last `nbytes` bytes, file size) — first line kept as-is, nothing decoded. Raises OSError."""
    with open(path, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        f.seek(max(0, size - nbytes))
        return f.read(), size


def _tail_incr(fp, nb, prev):
    """Read **only the newly appended tail** of an append-only JSONL (incremental `_tail_lines`).

    `prev` is the previous `(start, end)` byte offsets or `None`.
    Returns `(lines, start, end, reset)` — on `reset` the caller **drops its previous accumulation** and restarts.

    ★Why (measured 2026-09-18): `/api/agents/timeline` re-read **109.1MB** of transcript tails on every
      request. The cache key included `size`, so **a single appended byte missed everything** — running
      sessions were effectively cold on every request.
    ⚠**Consume only up to the last newline and leave the offset there** — reading mid-append yields a half
      last line. Parsing it or counting it in the offset makes the next read start mid-line, splitting it
      in two and **dropping both**.
    ⚠If `size` is **smaller** than the previous `end`, treat it as a different file (rotated/rewritten) and reread all.
    """
    try:
        size = os.path.getsize(fp)
    except OSError:
        return [], None, None, True
    reset = not (prev and prev[1] is not None and size >= prev[1])
    if reset:
        off = size - nb if size > nb else 0
        start = off
    else:
        start, off = prev[0], prev[1]
        if size == off:
            return [], start, off, False       # nothing grew — don't even open the file
    # ⚠Line by line, decoding only candidate lines: one bytes block + its decoded str + the split list
    #   kept ~300MB alive for one cold 48MB tail (one non-BMP char made the whole str 4 bytes/char);
    #   ★tracemalloc peak, 80MB window of a 1GB transcript: 638MB -> 144MB (= the returned lines). `\n` never occurs inside a
    #   UTF-8 sequence, so per-line "replace" decoding equals whole-block decoding.
    out = []
    try:
        with open(fp, "rb") as f:
            f.seek(off)
            left = size - off                  # never read past the `size` snapshot (file may still grow)
            if reset and off > 0:
                ln = f.readline(left)          # drop the truncated first line (same as `_tail_lines`)
                if not ln.endswith(b"\n"):
                    return [], size, size, True
                off += len(ln)
                left -= len(ln)
                start = off
            end = off
            while left > 0:
                ln = f.readline(left)
                if not ln.endswith(b"\n"):
                    break                      # partial last line — don't move the offset past it
                left -= len(ln)
                end += len(ln)
                if b"{" in ln:                 # cheap superset of the filter below
                    s = ln[:-1].decode("utf-8", "replace")
                    if s.strip().startswith("{"):
                        out.append(s)
    except OSError:
        return [], None, None, True
    return out, start, end, reset


def _head_extend(fp, nb, start):
    """Lines of the **front range** `[size-nb, start)` a wider window adds before an earlier `_tail_incr` read.
    Returns `(lines, new_start)`; `new_start == start` when nothing was added.

    ★Growing a window used to reread the whole tail (3→12→48→80MB = up to 143MB for one 80MB window).
    ⚠`start` must be a line start (as `_tail_incr` returns it). The new first line is dropped exactly as a
      cold `_tail_incr(fp, nb, None)` drops it, so the lines equal a cold read of the same window."""
    try:
        size = os.path.getsize(fp)
    except OSError:
        return [], start
    off = size - nb if size > nb else 0
    if off >= start or size < start:
        return [], start
    out = []
    try:
        with open(fp, "rb") as f:
            f.seek(off)
            left = start - off
            if off > 0:
                ln = f.readline(left)          # drop the truncated first line (same as the cold read)
                if not ln.endswith(b"\n"):
                    return [], start           # no line boundary before `start` — nothing to add
                left -= len(ln)
                off += len(ln)
            while left > 0:
                ln = f.readline(left)
                if not ln.endswith(b"\n"):
                    break
                left -= len(ln)
                if b"{" in ln:                 # same filter as `_tail_incr`
                    s = ln[:-1].decode("utf-8", "replace")
                    if s.strip().startswith("{"):
                        out.append(s)
    except OSError:
        return [], start
    return out, off


# ★Only human-written lines count as "current task" — notifications, reminders and shell output far outnumber them,
#   and unfiltered the screen is covered by `<task-notification>` (measured: the last user entry usually is one).
_NOT_HUMAN = ("<task-notification", "<system-reminder", "<bash-input", "<bash-stdout",
              "<local-command", "Caveat:", "[Request interrupted")


def _human_text(content):
    txt = None
    if isinstance(content, str):
        txt = content
    elif isinstance(content, list):
        for x in content:
            if isinstance(x, dict) and x.get("type") == "text":
                txt = x.get("text")
                break
    if not txt:
        return ""
    t = txt.strip()
    if any(t.startswith(k) for k in _NOT_HUMAN):
        return ""
    t = " ".join(t.split())
    return t[:64]


# ★`user` lines to skip in state detection — written **by the harness**, not a human.
#   Why (measured 2026-09-08): a slash command like `/usage-credits` writes three `type=user` lines
#   (`<local-command-caveat>Caveat:…` · `<command-name>/usage-credits</command-name>…`
#    · `<local-command-stdout>…`) to the transcript. The shape logic below (`_parse_transcript`) reads
#   a `user` line as "a tool result just arrived = model is thinking" ⇒ slash-command lines were misread
#   as **"the user just spoke"** and the state got **stuck at `think` forever**.
#   Measured: session d4e5f6a7 showed **`think`·`Bash` for 37 min**, while in fact at 21:15:22Z
#   (06:15 KST) `assistant`(text) → `stop_hook_summary` → `turn_duration` had **closed the turn**
#   (= correct state `wait`). `last_shape` was fixed by the slash-command line first, so the later
#   turn-end markers were ignored. Not specific to that session — **any session left after a slash command
#   kept showing `think`**.
#   ⚠`[Request interrupted` is **deliberately not filtered**: below it sets `aborted`, and an interrupt
#     is **a legitimate state**, not noise (needs a human to move). Filtering it kills interrupt detection.
#   ⚠Leave `_NOT_HUMAN` (above) alone — it is for the "current task" label only and its list differs.
#     Indeed `<command-name` is not in it: the label may silently drop that line (empty string),
#     but state must **treat the line as absent** to reach the turn-end markers after it.
_NOT_HUMAN_STATE = ("<task-notification", "<system-reminder", "<bash-input", "<bash-stdout",
                    "<local-command", "<command-name", "<command-message", "<command-args",
                    "Caveat:")


def _noise_user(content) -> bool:
    """Is this `user` line not human-written (slash-command output, notification, reminder, etc.)?

    ⛔Content is never stored or sent — **boolean only** (same contract as the shape logic).
    ★`content` comes as str or list. The measured slash-command lines were str, but `{"type":"text"}` block
      lists also occur, so both are checked. Same test as `_human_text` (prefix after strip).
    ⚠If the list mixes in non-`text` blocks (`tool_result` etc.) it is **real activity**, not noise —
      `errored`·`aborted` must be extracted from that line, so it must not be filtered here."""
    if isinstance(content, str):
        txt = content
    elif isinstance(content, list):
        parts = []
        for x in content:
            if not isinstance(x, dict):
                return False
            if x.get("type") != "text":
                return False               # tool_result etc. mixed in = real activity
            parts.append(x.get("text") or "")
        txt = "\n".join(parts)
    else:
        return False
    t = txt.strip()
    return bool(t) and any(t.startswith(k) for k in _NOT_HUMAN_STATE)


def _reply_summary(content, limit=110):
    """**One-line summary** of the last assistant reply. Card text, so first two lines only, markdown stripped.
    ★The card used to show the last human instruction, but a completion alert echoing **the user's own words**
      was useless (2026-08-19). An alert must say *what was done*."""
    txt = None
    if isinstance(content, list):
        for x in content:                          # last text block (the final answer, not narration between tool calls)
            if isinstance(x, dict) and x.get("type") == "text" and (x.get("text") or "").strip():
                txt = x["text"]
    elif isinstance(content, str):
        txt = content
    if not txt:
        return ""
    lines = []
    for ln in txt.splitlines():
        t = ln.strip()
        if not t or t.startswith(("```", "|", "---")):
            continue
        t = re.sub(r"[*`#>]+", "", t).strip()      # strip markdown symbols only — ★keep underscores (a notify tool name got glued together)
        t = re.sub(r"^[-•·\d.]+\s*", "", t)
        if t:
            lines.append(t)
        if len(lines) == 2:
            break
    return " / ".join(lines)[:limit]


# ★"What is it working on" — the tool **name alone is not enough** (2026-08-19: the user needs to see the task itself).
#   That slot used to show **the last human instruction**, which is the user's own words and of little value (the bell card
#   switched from instruction to reply summary for the same reason). A **target** next to the tool name is the task.
#   ⚠To stay at metadata level only **whitelisted keys** are read — `prompt`·`body`·`subject` are **deliberately excluded**
#     (mailbox_send's body is conversation content itself; keeps the *session panel is metadata only* rule).
_ARG_KEYS = ("description", "file_path", "path", "pattern", "query", "url", "command")


def _tool_target(block):
    """Tool call -> one-line target (empty if none). Paths as basename only, truncated, newlines removed.

    ★Bash yields **the command itself** (2026-09-03: the description was unreadable against the terminal). Previously
      `description` came first, so the screen showed `Print the runtime-root diff again` while the terminal showed
      `cd ~/agent-A && git diff --stat abc1234..HEAD -- engine …` —
      **the two screens could not be matched.** The description is a name the model made up; the command is the fact.
      ⚠In exchange **the description disappears from this slot.** The work log (`_agent_arg`) still has the command,
        and the description is only a model-given name, so losing it loses no facts — hence this trade."""
    a = block.get("input")
    if not isinstance(a, dict):
        return ""
    if block.get("name") == "Bash":
        c = a.get("command")
        if isinstance(c, str) and c.strip():
            return " ".join(c.split())[:72]
    for k in _ARG_KEYS:
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            if k in ("file_path", "path"):
                v = os.path.basename(v) or v
            return v[:72]
    return ""


# Same wrappers as usage_index._MODEL_WRAP (that module sits above this one, so it cannot be imported here).
_LABEL_WRAP = re.compile(r"^(?:[a-z]{2,4}\.)?anthropic\.|\[[^\]]*\]$|@\d{8}$|-v\d+(?::\d+)?$|-\d{8}$|-latest$")


def _model_label(model):
    """`claude-sonnet-4-5-20250929[1m]` → `sonnet-4-5`: family + full version, no prefix/tag/date.
    ⚠Do not cut to two segments — `sonnet-4-5` would read as `sonnet-4`."""
    if not model:
        return ""
    m, prev = str(model).strip().lower(), None
    while m != prev:
        prev, m = m, _LABEL_WRAP.sub("", m)
    return m[7:] if m.startswith("claude-") else m


_FRAC_RE = re.compile(r"\.(\d+)(?=([+-]\d\d:?\d\d)?$)")


def iso_epoch(s, default=0.0):
    """ISO string -> epoch, `default` if unreadable. ★Python 3.9's `fromisoformat` **cannot parse 'Z'**
    (launchd runs 3.9) and accepts only 3- or 6-digit fractions — so the remaining time silently became `null`
    (measured 2026-08-20: the reset countdown showed '?'). Naive strings are local time, as before."""
    try:
        v = str(s).strip()
        if v[-1:] in ("Z", "z"):
            v = v[:-1] + "+00:00"
        v = _FRAC_RE.sub(lambda m: "." + (m.group(1) + "00000")[:6], v, count=1)
        return datetime.fromisoformat(v).timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return default          # unparsable/out-of-range timestamp: caller's default


def _iso_ts(iso):
    return iso_epoch(iso, None) if iso else None


_TUID_RE = re.compile(r"<tool-use-id>([^<]+)</tool-use-id>")
# ★Lowered 900 → 30 (measured 2026-09-07: 2 origin subagents running but only 1 shown).
#   900 came from the 2026-09-01 observation that «the last record landed at completion notice +283s (the harness's
#   last flush)». Re-measuring that observation showed **it was a resume, not a flush** — the first line appended to
#   that agent's log after the notice was "The user sent a new message while you were working" / "The coordinator sent a message
#   while you were working" / "[Request interrupted by user]". i.e. a person spoke to it again.
#   ⇒ Full measurement (all transcripts · 1,536 agents · «each agent's last completion notice» vs jsonl mtime):
#       mtime < notice          1,115
#       notice +0 ~ +1.1s         419   ← the real last flush ends here (max 1.1s)
#       +1.1s ~ +120s               0
#       +143.9s                     1 ← resumed after the notice and kept working
#       +891.6s                     1 ← resumed, then stopped by the user
#     1,534 of 1,536 (99.87%) are within 1.1s, and the two larger ones were resumes that **should be revived**.
#   30s is 27x headroom over the measured max (1.1s). The time stamped in `_bg_popped` is not the notice time but **the scan
#   time** (2.5s polling + deep-scan delay), so it can lag the notice by seconds; this headroom covers that too.
#   ⚠Lower it further (e.g. 5s) and finished agents revive, and a revived row sticks until RUN_STALE_S (2 hours) —
#     the «show what is gone for long» failure. Conversely 900 hid every «resume that works 5 min and ends».


def _line_ts(d, fallback):
    """The time the line **was written**. ★Must not stamp `now` — scanning 20MB turns hours-old notifications into 'just now',
    leaving already-dead watchers as alive (measured 2026-08-19: a bot session's watcher showed as 2)."""
    ts = d.get("timestamp")
    if not ts:
        return fallback
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").timestamp() + _TZ_OFF
    except (TypeError, ValueError, OverflowError, OSError):
        return fallback         # non-string or garbled timestamp: caller's fallback, never `now`


# transcript timestamps are UTC — convert to local (otherwise they look 9 hours old and all expire)
_TZ_OFF = -time.timezone if time.daylight == 0 else -time.altzone
