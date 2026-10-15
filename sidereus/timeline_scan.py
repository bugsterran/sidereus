"""Timeline scanning: transcript segments, compactions, token lines, sleep and idle intervals.

Split out of `sidereus/timeline.py` (2026-09-24); `timeline` assembles the rows and re-exports the names it uses.
⚠Patch these names here, not on `timeline` — functions in this module read their own globals."""
import json
import re
import subprocess
import threading
import time
from datetime import datetime
from sidereus.config import IS_MAC
from sidereus.warn import warn_once
from sidereus.transcript import _head_extend, _line_ts, _tail_incr


TL_HOURS = 6               # how far back the timeline looks


_HOUR_TS = {}              # "YYYY-MM-DDTHH" -> _line_ts of that hour's :00:00


def _fast_ts(ts):
    """Same value as `_line_ts({"timestamp": ts}, 0)`, parsed once per hour prefix.
    ★Measured 2026-09-24: cold `_seg_scan` made 160k strptime calls = 1.0 s of 2.9 s. DST moves on hour boundaries,
      so hour base + mm*60 + ss equals the per-line parse. ⚠Anything off the fixed shape goes to `_line_ts` (same fallback)."""
    if len(ts) < 19 or ts[13] != ":" or ts[16] != ":":
        return _line_ts({"timestamp": ts}, 0)
    mm, ss = ts[14:16], ts[17:19]
    if not (mm.isascii() and ss.isascii() and mm.isdigit() and ss.isdigit()) or int(mm) > 59 or int(ss) > 59:
        return _line_ts({"timestamp": ts}, 0)
    h = ts[:13]
    base = _HOUR_TS.get(h)
    if base is None:
        base = _line_ts({"timestamp": h + ":00:00"}, None)
        if base is None:
            return _line_ts({"timestamp": ts}, 0)
        if len(_HOUR_TS) > 5000:
            _HOUR_TS.clear()
        _HOUR_TS[h] = base
    return base + int(mm) * 60 + int(ss)


SEG_GAP = 180              # quiet this long ⇒ a new segment (seconds)
SEG_MAX = 60               # cap on segments per session


def _compacts(fp, cut):
    """This session's **context compaction history**, as recorded by `compact_boundary`.

    ★Why (2026-09-01): compaction shrinks 1M tokens to 10k and the session loses earlier context.
      The answer to "why did it suddenly forget" is here; each costs 149~230 s (measured).
      Frequent ones signal the session should be restarted — this cannot prevent it, **only explain**.
    ⚠Reads only the tail, so compactions older than that window are unknown."""
    # ★Same window as the bars: collected by `_seg_scan` from the lines it already reads. A separate ≥30MB
    #   read of the same file doubled cold bytes. The segment window always reaches `cut` (or the 80MB cap,
    #   or the whole file), so every compaction at/after `cut` is still seen. ⚠Called right after
    #   `_sess_segments(fp, cut)`; with no cached scan it runs one.
    ent = _SEG_RAW.get(fp)
    if ent is None:
        _sess_segments(fp, cut)
        ent = _SEG_RAW.get(fp)
    if not ent:
        return []
    return [dict(it) for it in ent[7] if it["at"] >= cut][-20:]   # copies: don't leak the cached original


def _cpt_item(ln):
    """A `compact_boundary` line -> compaction item, else None."""
    try:
        e = json.loads(ln)
    except Exception:
        return None
    # ★**Check the type.** A string match also catches lines that merely mention the word
    #   (measured 2026-09-01: the session writing this code counted its own talk as compactions — all 3 fake).
    if not isinstance(e, dict) or e.get("type") != "system" or e.get("subtype") != "compact_boundary":
        return None
    m = e.get("compactMetadata") or {}
    at = _line_ts(e, 0)
    if not at:
        return None
    return {"at": int(at), "trig": m.get("trigger") or "?",
            "pre": int(m.get("preTokens") or 0), "post": int(m.get("postTokens") or 0),
            "drop": int(m.get("cumulativeDroppedTokens") or 0),
            "ms": int(m.get("durationMs") or 0)}


SEG_CAP_BYTES = 80_000_000     # **cap** on bytes read per session to find segments
SEG_CAP_LINES = 160_000
# ★Remember per file **the window size that worked last time**. Otherwise it gropes up 3MB → 12MB → 48MB
#   every time, reading the same bytes three times (63MB per call on a 277MB session). Remembered, it is once.
_SEG_WIN = {}
# ⚠Caps must exceed the files one window touches (measured 2026-09-24: 12h 160 · 24h 190 · 325 across a replay).
#   At the old 200/300 a 24h pass cleared both caches mid-pass, so every request stayed cold (~2 s).
SEG_CACHE_MAX = 1500
# ★Per-file **raw-material cache** (see ★ in `_seg_scan`) — one slot per path, so an active file just
#   refreshes its slot. Value is `(nb, lim, start, end, oldest, ts_all, tok_all, cpt_all, trimmed)` — `start`/`end`
#   are the **byte range** read so far (bookmarks for growing either end); `cpt_all` feeds `_compacts`.
_SEG_RAW = {}


# ★**Canonical token definition** (2026-09-09; the agent timeline, daily and per-project totals all disagreed).
#   All three screens use this one: input + output + cache_read + cache_creation = ccusage's `totalTokens`.
#   Measured to **match exactly** (09-07 352,606,896 · 09-08 683,110,423 — direct transcript totals and
#   `ccusage daily` agree to the last digit).
#   ⚠Output tokens used to be excluded ("0.1% share · must not diverge from the day card"). That reason is gone —
#     the day card now uses the same definition, so matching "daily" (ccusage) to the digit is better.
#   The leading `"` in the regex keeps `cache_read_input_tokens` from double-matching the `input_tokens`
#   branch, and excludes `output_tokens_details`·`ephemeral_5m_input_tokens` too.
_TOKRE = re.compile(r'"(input_tokens|output_tokens|cache_read_input_tokens'
                    r'|cache_creation_input_tokens)":(\d+)')
# ★**One response = several lines** (measured 2026-09-09 · today's usage lines 3,385 / actual responses 1,693 =
#   exactly 2.00 per response). Each content block comes as a line (`thinking` → `tool_use` → `text`) and
#   **every line carries a copy of the whole response's usage**. Summing per line doubles it.
#   ⇒ Count a response **once** by `(message.id, requestId)`. ccusage groups by the same key.
#   ⚠Duplicates occur **within the same file** (measured: every duplicate pair in one file) — filter while
#     scanning a file, not when merging files.
_RESP_MID = re.compile(r'"id":"(msg_[A-Za-z0-9_-]{1,60})"')
_RESP_RID = re.compile(r'"requestId":"([^"]{1,60})"')


def _resp_key_line(ln):
    """Key of the **response** the line belongs to. `None` if either part is missing — then no dedup
    (old and synthetic lines lack `requestId`; measured 09-07~09 such lines carry 0 tokens)."""
    a = _RESP_MID.search(ln)
    if not a:
        return None
    b = _RESP_RID.search(ln)
    return (a.group(1), b.group(1)) if b else None


def _resp_key(e):
    """Same key from a parsed line (`_today_fetch`·`_burn_fetch` already do `json.loads`)."""
    mid = ((e.get("message") or {}).get("id") or "") if isinstance(e, dict) else ""
    rid = (e.get("requestId") or "") if isinstance(e, dict) else ""
    return (mid, rid) if (mid and rid) else None


def _line_tokens(ln):
    """Tokens used by the line. ⚠No `json.loads` — this function passes over **every line** of the tail.

    ★Count **only the first occurrence** of each field (measured 2026-09-09). `iterations:[{input_tokens…}]`
      inside `usage` holds the same numbers **again**, so running the regex to the end of line doubled them
      (one line measured: `2·2167·83148` followed by `2·83148·2167`). Combined with the response duplication (×2)
      above, the timeline drew **×2.94** the true value (today 618.1M vs true 210.0M).
    ⚠Don't cut `iterations` by name — old lines lacked the field, and other copy fields may appear later.
      "First per field" is a rule that does not depend on shape."""
    i = ln.find('"usage"')
    if i < 0:
        return 0
    got = {}
    for m in _TOKRE.finditer(ln, i):
        k = m.group(1)
        if k not in got:
            got[k] = int(m.group(2))
    return sum(got.values())


def _scan_lines(lines, oldest, ts_all, tok_all, cpt_all):
    """Append each line's time · tokens · compaction to the lists; returns `(oldest, ts_all, tok_all, cpt_all)`."""
    for ln in lines:
        if "compact_boundary" in ln:
            it = _cpt_item(ln)
            if it:
                cpt_all.append(it)
        i = ln.find('"timestamp":"')
        if i < 0:
            continue
        v = _fast_ts(ln[i + 13:i + 37])
        if not v:
            continue
        if oldest is None or v < oldest:
            oldest = v      # ★this is **the read range** — where the window reached, not activity, so count all
        # ★`queue-operation` is **not activity** (measured 2026-09-09). Lines the user queued while the model ran
        #   carry no trace of the model working. But they have timestamps and made bars —
        #   repo-A's 06:07~06:14 bar was **only 8 `queue-operation` lines** with 0 tokens.
        #   The screen called it "7 min of activity" (false).
        #   ⚠Surfaced when per-bar tokens (`tks`) were added — "7 min activity · no token record".
        #   ⇒ Excluded from segments. Other kinds stay: `assistant` (lines with usage) ·
        #     `user` (incl. tool results) · `attachment`·`system`·`file-history-*` are all records written during
        #     real work (measured 24 h · 12 tail files: assistant 2,567 ·
        #     attachment 1,603 · user 1,323 · system 343 · queue-operation 316 · others 127).
        if '"type":"queue-operation"' not in ln:
            ts_all.append(v)
            n = _line_tokens(ln)
            if n:
                tok_all.append((v, n, _resp_key_line(ln)))
    return oldest, ts_all, tok_all, cpt_all


def _seg_scan(fp, cut, nb, lim):
    """Timestamps read in the window + **the oldest time the window reached** (before cut = read enough)
    + **(time, tokens) pairs** (added 2026-09-08 to plot token usage alongside).

    ★Why count tokens here: this loop already passes every line of the tail. Reading separately would read
      the same file twice (up to 80MB). Extra cost per line is one `find('"usage"')`."""
    # ★**Unchanged files are not reread** (2026-09-09). Counting everything increased the read volume
    #   (12 h window 60MB · 69 files) — yet most are **finished sessions** whose content never changes again.
    #   Only the window (`cut`) moves forward each time.
    #   ⇒ Cache only what is **independent of `cut`** (line time, tokens, response key); cutting by `cut` and
    #     response dedup are **redone every time**. That keeps the result identical to an uncached run
    #     (⚠baking dedup into the cache drops a whole response when its first line is outside the window and its copy inside).
    #   Measured: 0.91 s → 0.30 s (12 h window, from the second call). Cache size is 49,733 in-window times +
    #   21,258 usage lines — a few MB.
    #   ★Made incremental (2026-09-18). The key included `size`, so **a single appended byte missed everything**,
    #     and running sessions (measured: 4 transcripts appended within the last 60 s, one of 28MB) were
    #     effectively cold every request ⇒ 109.1MB per request. Now only **the new tail** after the last offset is
    #     parsed and appended (see the three ⚠ in `_tail_incr`). `oldest` stays — the **start** of the read range does not change.
    ent = _SEG_RAW.get(fp)
    front = []
    try:
        if ent and (ent[0] != nb or ent[1] != lim):
            # ★A wider window reads only the new front range (`_head_extend`) and prepends it — the 4x growth
            #   steps used to reread the tail from scratch. ⚠A trimmed entry has lost lines, so reread it all.
            if ent[0] < nb and ent[1] <= lim and not ent[8]:
                front, _fs = _head_extend(fp, nb, ent[2])
                ent = (nb, lim, _fs) + ent[3:]
            else:
                ent = None                 # window shrank or entry trimmed — reread from scratch
        lines, _bs, _be, _rs = _tail_incr(fp, nb, (ent[2], ent[3]) if ent else None)
    except Exception as e:             # both readers already absorb OSError — anything here is a fault
        warn_once("tl-segs", "timeline segment read failed ({err}) — that session's bar is empty",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return [], None, []
    if _bs is None:
        return [], None, []
    if _rs or ent is None:
        oldest, ts_all, tok_all, cpt_all, trimmed = None, [], [], [], False
    else:
        oldest, ts_all, tok_all, cpt_all, trimmed = ent[4], ent[5], ent[6], ent[7], ent[8]
    if front and not _rs:
        f_old, f_ts, f_tok, f_cpt = _scan_lines(front, None, [], [], [])
        if f_old is not None and (oldest is None or f_old < oldest):
            oldest = f_old
        ts_all, tok_all, cpt_all = f_ts + ts_all, f_tok + tok_all, f_cpt + cpt_all
    oldest, ts_all, tok_all, cpt_all = _scan_lines(lines, oldest, ts_all, tok_all, cpt_all)
    ts, tok = [], []
    seen_resp = set()      # ★response dedup — within this scan only (see ⚠ at `_resp_key_line` above)
    # ⚠Incremental reads never drop the front, so the accumulation outgrows the window ⇒ trim **from the front** at `lim`.
    #   Only old out-of-window items are dropped, so the `cut`-filtered result is unchanged. `oldest` is the start of
    #   the read range, so it is reset only here (the window moved forward).
    if len(ts_all) > lim:
        ts_all = ts_all[-lim:]
        _v0 = min(ts_all)
        tok_all = [t for t in tok_all if t[0] >= _v0]
        oldest = _v0
        trimmed = True
    # ⚠Compactions are not trimmed by `lim` (they used their own wider read); output takes `[-20:]` anyway.
    if len(cpt_all) > 200:
        cpt_all = cpt_all[-200:]
    if len(_SEG_RAW) > SEG_CACHE_MAX:
        _SEG_RAW.clear()
    _SEG_RAW[fp] = (nb, lim, _bs, _be, oldest, ts_all, tok_all, cpt_all, trimmed)
    ts = [v for v in ts_all if v >= cut]
    for v, n, k in tok_all:
        if v < cut:
            continue
        if k is not None:
            if k in seen_resp:
                continue           # second line of the same response — keep the time (activity), drop only tokens
            seen_resp.add(k)
        tok.append((v, n))
    return ts, oldest, tok


def _seg_whole(fp, nb, lim):
    """True when the last `_seg_scan(fp, …, nb, lim)` started at byte 0 and kept every line (no `lim` trim).
    ★Measured 2026-09-24: 425 of 787 cold scans (498 of 950 MB) regrew windows over files already read whole."""
    ent = _SEG_RAW.get(fp)
    return bool(ent) and ent[0] == nb and ent[1] == lim and ent[2] == 0 and len(ent[5]) < lim


def _sess_segments(fp, cut, nb=3_000_000, lim=6000, tok_out=None):
    """Segments where the session **actually moved**. Groups tail timestamps by gaps.

    ★Why (2026-09-01): session bars used to be drawn as one solid "open" span, so a mostly idle
      session stretched across the screen and looked like it "worked the whole time".
    ★**If the window is requested in time, read back to that time** (2026-09-02: a compaction mark appeared with
      no bar, and the start 6 h back was missing). It was fixed at 3MB, so on a 277MB session it reached
      **only the last 2 hours** — the screen said "last 6 hours" while missing 4, and the compaction mark (reading
      30MB) **floated alone where no bar was** (measured: segments up to 10:55, compaction at 09:27).
      Both readers must see the same window so the screen does not contradict itself.
    ⚠At the cap (80MB) it stops — then **return what was reached** and the UI marks it with hatching.
      Never claim an unknown span had no activity."""
    got = _SEG_WIN.get(fp)
    if got and got[0] > nb:
        nb, lim = got                      # last time this file needed this much
    ts, oldest, tok = _seg_scan(fp, cut, nb, lim)
    # no line older than cut seen = window too small. Grow 4x at a time until it reaches cut.
    while (oldest is None or oldest > cut) and nb < SEG_CAP_BYTES:
        if _seg_whole(fp, nb, lim):
            break                          # ⚠whole file read, nothing trimmed: a wider window rereads the same lines
        nb = min(nb * 4, SEG_CAP_BYTES)
        lim = min(lim * 4, SEG_CAP_LINES)
        ts, oldest, tok = _seg_scan(fp, cut, nb, lim)
    # ★Pass on **only the last scan's** result — it runs several times while widening; adding intermediates double-counts.
    #   ⚠`tok_out` is an output channel (return shape unchanged — so existing callers are untouched).
    _SEG_WIN[fp] = (nb, lim)
    if len(_SEG_WIN) > SEG_CACHE_MAX:
        _SEG_WIN.clear()
    if tok_out is not None:
        tok_out.extend(tok)
    segs = []
    if not ts:
        return segs, 0
    ts.sort()
    a = b = ts[0]
    for t in ts[1:]:
        if t - b > SEG_GAP:
            segs.append((a, b)); a = t
        b = t
    segs.append((a, b))
    # ★The second value is **the oldest time the window reached** (not the start of activity). The UI draws
    #   the "unknown before here" hatching with it — once cut is reached, the hatching disappears.
    seen = int(oldest if (oldest and oldest <= cut) else ts[0])
    # ★If **truncated** by the segment cap (SEG_MAX), move the hatching back to the cut point.
    #   Otherwise it says "window reached", the hatching vanishes, there is no bar, and a compaction mark
    #   floats alone in an empty spot again (the just-fixed symptom revives on wide windows — measured 2026-09-02:
    #   repo-A's 48 h window was cut at exactly 60 segments).
    kept = segs[-SEG_MAX:]
    if len(segs) > SEG_MAX and kept:
        seen = max(seen, int(kept[0][0]))
    return kept, seen


# ── Sleep intervals — is a timeline gap "unused" or "the Mac slept"? ──────────────
#   ★Why (2026-09-17): 15:09~15:11 activity was entirely blank during active work.
#     `pmset -g log` recorded `15:08:08 Entering Sleep state due to 'Idle Sleep'` →
#     `15:12:23 Wake from Deep Idle … UserActivity` — the Mac slept.
#     If the screen cannot tell the two apart, a gap always reads as "did nothing".
NAP_TTL_S = 120            # ★`pmset -g log` is tens of MB, so running it every request (30 s) is waste.
#   Sleep intervals are past facts; 2 min stale never makes the screen wrong — if asleep now, no response anyway.
NAP_RETRY_S = 30           # retry delay after a failed/timed-out pmset (the last good value stays served)
NAP_MIN_S = 30             # drop shorter sleeps — maintenance blips, not "stopped time"
IDLE_MIN_S = 600           # ★minimum idle length (awake but no records) — 10 min.
#   ⚠Reusing 30 s (`NAP_MIN_S`) fails: gaps between bars come in hundreds at tens of seconds,
#   making the strip blotchy, and they are thinner than the minimum bar width (0.5% ≈ 6.7px), showing only as dots.
#   ⇒ Cut at a length worth calling "away" (measured case 9/18 12:44~13:13 = 31 min).
_naps_cache = {"at": 0.0, "v": []}
_naps_lock = threading.Lock()
_NAP_TS = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4})\s")


def _nap_parse(txt):
    """Filtered lines of `pmset -g log` -> `[(start, end), …]` (epoch).

    ⚠`DarkWake` is **not waking up** — a few-second maintenance blip that sleeps again right away.
      ★Measured 2026-09-17 12:14~13:32: `DarkWake`/`Sleep` repeats 6 times with no human use =
      **one long sleep**. Counting them as wakes shatters a 78-minute gap into pieces.
      ★Measured 2026-09-18: full-wake lines also contain `DarkWake` in their description
      (`Wake  DarkWake to FullWake from Deep Idle ...`) — substring filtering drops real full wakes too.
      So decide by **the event-type token** right after the timestamp."""
    out, st = [], None
    for ln in txt.splitlines():
        m = _NAP_TS.match(ln)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S %z").timestamp()
        except ValueError:
            continue
        kind = ln[m.end():].split(None, 1)[0] if ln[m.end():].strip() else ""
        if "Entering Sleep state" in ln:
            if st is None:
                st = ts
        elif kind == "Wake":
            if st is not None and ts > st:
                out.append((st, ts))
            st = None
    return out


def _naps_fetch():
    """Raw sleep intervals from `pmset -g log`; empty list on non-Mac, **None** on failure or timeout."""
    try:
        # ⚠The raw log is huge — always narrow with `grep` and set a timeout.
        r = subprocess.run(
            ["/bin/sh", "-c",
             "/usr/bin/pmset -g log | /usr/bin/grep -E "
             "'Entering Sleep state|Wake from'"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=12) if IS_MAC else None
        return _nap_parse(r.stdout or "") if r is not None else []   # ⚠non-Mac — no pmset (empty list)
    except subprocess.TimeoutExpired:
        warn_once("naps-slow", "Sleep lookup (pmset -g log) took over 12 s — timeline gaps are not marked as asleep")
    except Exception as e:
        warn_once("naps", "Could not read sleep periods ({err}) — timeline gaps are not marked as asleep",
                  vars={"err": f"{type(e).__name__}: {e}"})
    return None   # ⚠None = failed, distinct from a genuinely empty [] — _naps_refresh keeps the last good value


def _naps_refresh():
    try:
        raw = _naps_fetch()
        if raw is None:
            # ★2026-09-25: 9 pmset timeouts in 200 viewer.err lines, each cached [] as fresh and blanked
            #   the sleep bands for the full TTL. ⇒ Keep the last good value; retry after NAP_RETRY_S, not NAP_TTL_S.
            with _naps_lock:
                _naps_cache["at"] = time.time() - NAP_TTL_S + NAP_RETRY_S
            return
        with _naps_lock:
            _naps_cache["at"], _naps_cache["v"] = time.time(), list(raw)
    finally:
        with _naps_lock:
            _naps_cache["busy"] = False


def naps(hours=TL_HOURS):
    """Sleep intervals overlapping the last `hours`. A failed or timed-out pmset keeps the last good bands; **empty list** only when nothing was ever fetched (the screen must not die)."""
    now = time.time()
    cut = now - max(0.5, min(168, float(hours))) * 3600
    # ★Measured 2026-09-24: pmset costs 1.4-1.5 s, and every request after the 120 s TTL paid it inline (timeline 1.9-3.5 s).
    #   ⇒ Once filled, a stale cache is served and refreshed on a background thread.
    # ⚠The empty cache also refreshes in the background and returns [] (★2026-09-25: cold timeline(3) 1.91 s, 1.31 s of it pmset).
    #   Safe because nothing caches the timeline response: the next page poll recomputes and draws the sleep bands.
    with _naps_lock:
        stale = (now - _naps_cache["at"]) >= NAP_TTL_S
        raw = list(_naps_cache["v"])
        spawn = stale and not _naps_cache.get("busy")
        if spawn:
            _naps_cache["busy"] = True
    if spawn:
        threading.Thread(target=_naps_refresh, name="naps-refresh", daemon=True).start()
    out = []
    for a, b in raw:
        a2, b2 = max(a, cut), min(b, now)
        if b2 - a2 >= NAP_MIN_S:
            out.append([int(a2), int(b2)])
    return out


def _naps_awake(nl, rows):
    """Sleep intervals **minus the pieces that have records** at that time.

    ★Why (2026-09-18; work showed up on top of a sleep band): `pmset` shows 17:06:29 `Idle Sleep` →
      17:38:27 `Wake`, but in between a 17:11:29 `DarkWake` lasted **27 min** (1618 s), during which the
      `repo-A` session wrote 13 lines at 17:11 · 7 at 17:12. The screen painted all 32 min as sleep and
      **covered the work** — `_nap_parse`'s assumption ("DarkWake is a few-second blip") broke.
    ⇒ Redefine "asleep": not "the system slept" but **"slept + no records at that time"**.
      `_nap_parse`'s DarkWake rule **stays** — without activity it must still be one long sleep
      (★2026-09-17 12:14~13:32 must not be split).
    ⚠Activity is the union of segments of **all rows** (sessions, agents) — one row alone misses times
      another row was awake.
    ⚠Uses only **segments the timeline already built** (no new transcript reads) — this is where incremental
      reads took 38.5 s → 0.4 s. Zero-width segments (a single timestamp) are dropped: no arbitrary width
      for a single point.
    """
    act = []
    for a in rows:
        for g in (a.get("segs") or []):
            if g[1] > g[0]:
                act.append((g[0], g[1]))
    if not act:
        return list(nl)
    act.sort()
    mg = [list(act[0])]                      # merge overlaps — makes the difference below O(n)
    for s, e in act[1:]:
        if s <= mg[-1][1]:
            mg[-1][1] = max(mg[-1][1], e)
        else:
            mg.append([s, e])
    out, i = [], 0
    for a, b in sorted(nl):
        cur = a
        while i < len(mg) and mg[i][1] <= cur:
            i += 1
        j = i
        while j < len(mg) and mg[j][0] < b:
            s, e = mg[j]
            # split pieces get **the existing minimum-length rule unchanged** (no new constant)
            if s > cur and s - cur >= NAP_MIN_S:
                out.append([int(cur), int(s)])
            cur = max(cur, e)
            j += 1
        if b - cur >= NAP_MIN_S:
            out.append([int(cur), int(b)])
    return out


def _idle_gaps(nl, rows, t0, t1):
    """Idle = time in the window that is **neither asleep nor covered by any row's activity**.

    ★Why: timeline gaps showed two meanings as the same blank —
      ① slept (`.tlnap` hatching) ② awake but no records (no mark). Measured 9/18 12:44~13:13,
      31 min, was the latter and the screen was just blank. "Absent because asleep" and "awake but idle"
      are different facts.
    ⇒ **The other side of the same material** as `_naps_awake`: that is sleep ∖ activity, this is window ∖ (sleep ∪ activity).
      No new transcript scan (same reason as the ⚠ there).
    ⚠The sleep subtracted is **the raw sleep intervals** (`nl`), not `_naps_awake`'s result — the result has
      activity carved out, so the spaces between pieces would leak out as idle, and sleep and idle bands would overlap.
      This function is where zero overlap is guaranteed.
    """
    busy = []
    for a in rows:
        for g in (a.get("segs") or []):
            if g[1] > g[0]:
                busy.append((g[0], g[1]))
    for a, b in (nl or []):
        if b > a:
            busy.append((a, b))
    busy.sort()
    mg = []
    for s, e in busy:                        # merge overlaps — makes the difference O(n)
        if mg and s <= mg[-1][1]:
            mg[-1][1] = max(mg[-1][1], e)
        else:
            mg.append([s, e])
    out, cur = [], t0
    for s, e in mg:
        if s > cur and s - cur >= IDLE_MIN_S:
            out.append([int(cur), int(s)])
        cur = max(cur, e)
    if t1 - cur >= IDLE_MIN_S:
        out.append([int(cur), int(t1)])
    return out
