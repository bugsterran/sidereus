"""Failure catalog scan: grading, signatures, per-line parsing and the cumulative transcript scan (split from failures.py 2026-09-24)."""
import glob
import json
import os
import re
import threading
import time
from sidereus.redact import redact
from sidereus.warn import warn_once
from sidereus.transcript import CLAUDE_PROJECTS, _TUID_RE, _line_ts
from sidereus.ident import _proj_name
from sidereus.agents import _agent_meta, sub_paths, sub_sess_dir
from sidereus.cards import _recent_transcripts
from sidereus.claude_roots import projects_dirs

# ── Failure catalog · unfinished wreckage ───────────────────────────────────
#   ★Why (2026-09-02): observability tools center on "turning failed runs into assets", yet
#     Sidereus read **not a single failure signal** (measured: last 14 days of transcripts had
#     task-notification failed 656 · killed 236 · tool is_error 1889 · api_error 122).
#     What the user needs is not eval — there is nothing to eval. It is two things: ⓐ what breaks
#     repeatedly (own fault or infrastructure) ⓑ whether a dying run left **half-edited files**.
#   ★Reading: not a tail window but **a cumulative scan that remembers its position** (same reason as _bg_lines).
#     This user runs one session for a long time — transcripts reach 1GB (measured repo-A 1,020MB).
#     A 6MB tail sees 0.6% of the file, making "last 24 hours" itself false.
#     So the first look scans everything but **filters at the byte level** (json parsing only for hits).
FAIL_HOURS = 24
FAIL_CHUNK = 8_000_000
FAIL_KEEP = 4000            # cap on events kept per file
FAIL_MAX_FILES = 60         # cap on **main-session** transcripts scanned (newest first)
# ★Subagent files are counted **separately** (2026-09-07). In one bucket cut at 60, subagents push out
#   main-session files — measured: in the last 720 h, 28 main sessions / 539 subagents.
#   Mixed newest-60 cannot guarantee how many main files remain, and then **failures visible now
#   disappear** (regression). So the quota is split.
# ★Why a cap of 400 (measured 2026-09-07): a cold full scan of subagents is
#   539 files 360MB = **0.87 s** (main sessions: 28 files 1,620MB = 3.51 s). Per-file cost is 1/40 of a
#   main session, so a generous cap is cheap. Still not unbounded because this directory accumulates —
#   2,084 files (1,030MB) in total — so cut by window (`hours`) and put a count cap on top.
FAIL_SUB_MAX_FILES = 400
FAIL_SEEN_H = 720           # max period events are held (30 days)

_FAIL_EV = {}               # transcript -> [events]  (cumulative)
_FAIL_OFF = {}              # transcript -> next byte offset to read
# ★`_FAIL_LOCK` guards **only the two dicts above** — no reason to hold it while reading files.
#   `_fail_events` used to hold this lock through a cold full scan (measured 2026-09-07: 40 files 2.81 s).
#   For those 2.8 s `_fail_loop` and other request threads' failure tabs froze entirely — the screen says
#   nothing, so **the breakage looks like "quiet"**
#   (a blocked failure tab renders the same as one with no failures).
#   ⇒ Read outside the lock; hold it only briefly "when reading the offset" and "when inserting events".
#   ⚠Then two threads can scan the same file at once and events **accumulate twice**. What prevents that is
#     not a data lock but the "scanning" flag below — only overlapping scans need blocking.
_FAIL_BUSY = set()          # transcripts someone is reading now (prevents duplicate scans — not a data lock)
_FAIL_LOCK = threading.Lock()
# ★Channel signalling that `_FAIL_BUSY` was released. A thread arriving late on the same file **waits** —
#   a half list would be the lie "no failures", worse than slow.
#   `_FAIL_LOCK` is released while waiting (Condition.wait does that) ⇒ other files and paths are not blocked.
_FAIL_SCAN = threading.Condition(_FAIL_LOCK)
FAIL_SCAN_WAIT_S = 8        # cap on waiting for one file (measured: cold scan of all 40 files is 2.8 s — one file is far shorter)

_FAIL_MARK_B = (b"<status>failed</status>", b"<status>killed</status>",
                b'"subtype":"api_error"', b'"is_error":true')
# tool_use id -> name, so a tool error can be reported by tool name instead of its raw output (byte regex, no json parse).
_TU_MARK_B = b'"type":"tool_use"'
_TU_NAME_RE = re.compile(rb'"type":"tool_use","id":"(toolu_[A-Za-z0-9_]{1,64})","name":"([^"\\]{1,80})"')
_FAIL_TNAME = {}            # transcript -> {tool_use id: name} (recent ids only, FAIL_TNAME_KEEP)
FAIL_TNAME_KEEP = 400

_ST_RE = re.compile(r"<status>([a-z]+)</status>")
_SUMM_FULL = re.compile(r"<summary>(.{1,400}?)</summary>", re.S)
_DENY_MARK = ("The user doesn't want to proceed", "user doesn't want to take this action",
              "requested permissions", "permission to use",
              "Permission for this action was denied")
# ★A hook block is **not an error** — a gate the user set up worked (devil's advocate etc.).
#   Mixed in, the tool-error list gets buried under hook output (measured 30 days: 249 of 724).
_HOOK_MARK = ("악마의 변호인", "blocked by hook", "Hook denied", "hook feedback")
# A model fallback is an **infrastructure signal**, not a tool error — auto mode could not get a model.
_UNAVAIL = re.compile(r"([\w.\[\]-]{3,30}) is temporarily unavailable")

# failure text -> **signature**. Order is the decision (stall before API error, limit before 429).
_SIG_RULES = (
    (re.compile(r"no progress for (\d+)s"), "서브에이전트 정지 — {0}초 무진전(stream watchdog)"),
    (re.compile(r"went to sleep mid-response"), "절전 중 응답 끊김"),
    (re.compile(r"Connection closed mid-response"), "연결 끊김(mid-response)"),
    (re.compile(r"hit your ([A-Za-z0-9 -]{1,20}?) limit"), "한도 도달 — {0}"),
    (re.compile(r"API Error: (\d{3})\s*([A-Za-z ]{0,18})"), "API {0} {1}"),
    (re.compile(r"error type ([a-z_]+), HTTP (\d{3})"), "API {1} ({0})"),
    (re.compile(r"failed with exit code (\d+)"), "백그라운드 명령 exit {0}"),
    (re.compile(r"script failed \(exit (\d+)\)"), "감시 스크립트 exit {0}"),
    (re.compile(r"(timed out|timeout)", re.I), "시간 초과"),
)

# ★**Grades** (2026-09-02; non-certain failures should be graded "needs check", not "failed"):
#     cut   = the harness wrote `failed` and the cause is **external** (sleep, connection, limit, overload, watchdog).
#             The agent did nothing wrong — the only action is **rerun it**.
#     check = `failed` but the cause matches nothing above, or a tool returned an error. **Needs a look**.
#     mine  = I stopped it or I blocked it (permission denial, hook block). Nothing to act on.
#   All three used to be called "failure" — counting even `stopped by user` as failure is false.
#   ⚠The criterion is **the harness's raw text** (2026-09-02; the selection criteria were unclear).
#     At first grading used our own Korean labels (`agent stopped`…), so every label tweak silently shifted
#     grades and **the screen had no way to show why a grade was given.**
#     The phrases below appear verbatim in notification bodies, so the basis can be quoted on screen.
_GRADE_RULES = (
    ("mine", "was stopped by user"),
    ("mine", "stopped by the user"),
    ("cut",  "no progress for"),                   # Agent stalled: no progress for 600s …
    ("cut",  "went to sleep mid-response"),
    ("cut",  "Connection closed mid-response"),
    ("cut",  "response stopped arriving"),
    ("cut",  "Overloaded"),
    ("cut",  "hit your session limit"),
    ("cut",  "hit your weekly limit"),
    ("cut",  "hit your 5-hour limit"),
    ("cut",  "is temporarily unavailable"),
    ("cut",  "terminated early due to an API error"),   # every API cause not matched above
)


def _fail_grade(kind, text):
    """(grade, basis phrase).

      cut   — the harness wrote `failed` and **the cause phrase was recognized**. Action = rerun.
      check — `failed` but **the cause phrase was not recognized.** Action = look at it (should be rare).
      mine  — I stopped or blocked it. No action.
      noise — a tool returned an error. **Part of the normal workflow**.

    ★Why `noise` is separate (2026-09-02; the selection criteria were unclear):
      putting tool errors under "needs check" lumped 322 there, of which `Exit code 1` 185 ·
      `File does not exist` · `String to replace not found` were **normal progress**.
      Calling "grep found nothing" a "needs check" empties the grade of meaning.
      ⇒ "needs check" keeps only **failure notifications whose cause could not be read**."""
    if kind in ("deny", "hook"):
        return "mine", "Blocked by me — permission denial or hook block"
    if kind == "tool":
        return "noise", "A tool returned an error — part of the normal workflow"
    t = text or ""
    # ★Match phrases **first** — splitting by kind first gave `is temporarily unavailable` (a tool result)
    #   the wrong basis "api_error record". The basis must be the phrase that actually matched.
    for g, ph in _GRADE_RULES:
        if ph in t:
            return g, ph
    if kind == "api":
        return "cut", "api_error record (written by the harness itself)"
    return "check", ""


_SIG_NUM = re.compile(r"\d+")
_SIG_PATH = re.compile(r"/[\w.~-]+(?:/[\w.~-]+)+")
_SIG_QUOTED = re.compile("[\"“”][^\"“”]{0,120}[\"“”]")


def _fail_sig(text):
    """Build from failure text **a key that groups the same cause**. Empty if no rule matches."""
    for rx, tpl in _SIG_RULES:
        m = rx.search(text or "")
        if m:
            g = [(x or "").strip() for x in m.groups()]
            try:
                return tpl.format(*g).strip().rstrip("(").strip()
            except (IndexError, KeyError, ValueError):
                return tpl            # template/group count mismatch: the bare template still groups the cause
    return ""


def _sig_cut(s, n):
    """Cut `s` to at most n chars at a word boundary and mark it with «…».
    ⚠A raw slice left «…before recursi» in the retro table and its tooltip, with no sign it was cut."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    head = s[:n - 1]
    sp = head.rfind(" ")
    if sp >= n // 2:   # else no usable space (long token / CJK run) -> keep the hard cut
        head = head[:sp]
    return head.rstrip(" ,;:—-") + "…"


def _tool_sig(t, n=90):
    """One tool-error line -> signature. Paths, numbers and quoted parts are erased so identical errors group into one line."""
    ln = (t or "").strip().splitlines()
    # ⚠Normalise before cutting: cutting the raw line first (was [:140]) could end the sig mid-word after the subs shrank it.
    ln = ln[0][:400] if ln else ""
    ln = ln.replace("<tool_use_error>", "").replace("</tool_use_error>", "").strip()  # ⚠both tags, else the closing one leaks into the sig
    ln = _SIG_PATH.sub("<경로>", ln)
    ln = _SIG_QUOTED.sub("<…>", ln)
    ln = _SIG_NUM.sub("N", ln)
    return _sig_cut(ln, n) or "도구 오류"


def _fail_line(ln, names=None):
    """Extract zero or more failure events from one line. `names` = {tool_use_id: tool name} seen earlier in the file."""
    try:
        e = json.loads(ln)
    except (TypeError, ValueError):
        return ()                             # half-written or non-JSON line: no failure in it
    at = int(_line_ts(e, 0) or 0)
    if not at:
        return ()
    cwd = e.get("cwd") or ""
    if e.get("type") == "system" and e.get("subtype") == "api_error":
        err = e.get("error") if isinstance(e.get("error"), dict) else {}
        stc = err.get("status") or 0
        return ({"at": at, "kind": "api", "tid": "", "cwd": cwd, "grade": "cut",
                 "why": "api_error record (written by the harness itself)",
                 "sig": ("API %s" % stc) if stc else "API 오류",
                 "text": (str(err.get("message") or "")
                          or json.dumps(err, ensure_ascii=False))[:200]},)
    out = []
    c = (e.get("message") or {}).get("content")
    txt = c if isinstance(c, str) else ""
    if isinstance(c, list):
        for b in c:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_result" and b.get("is_error"):
                c2 = b.get("content")
                t2 = c2 if isinstance(c2, str) else ("\n".join(
                    x.get("text", "") for x in c2
                    if isinstance(x, dict) and x.get("type") == "text")
                    if isinstance(c2, list) else "")
                t2 = (t2 or "").strip()
                if not t2:
                    continue
                # ★A permission denial is **not a failure** — the user blocked it. Counted separately (to locate blocks).
                head = t2[:240]
                um = _UNAVAIL.search(head)
                if any(k in head for k in _HOOK_MARK):
                    k2, sg = "hook", "훅이 막음 — " + _tool_sig(t2, 80)
                elif any(k in head for k in _DENY_MARK):
                    k2, sg = "deny", "권한 거부 — 사용자가 거절"
                elif um:
                    k2, sg = "api", "모델 일시 불가 — " + um.group(1)
                else:
                    k2, sg = "tool", _tool_sig(t2)
                _g, _w = _fail_grade(k2, t2)
                # ⚠`sig`/`text` here come from raw tool output — server-internal only (attention's benign filter);
                #   the API sends `tool` + a fixed label instead (`failures()` `_pub_sig`, AGENTS.md rule 1).
                out.append({"at": at, "kind": k2, "tid": "", "cwd": cwd,
                            "tool": (names or {}).get(b.get("tool_use_id") or "") or "",
                            "sig": sg, "text": t2[:200], "grade": _g, "why": _w})
        txt = " ".join(b.get("text", "") for b in c
                       if isinstance(b, dict) and b.get("type") == "text")
    if "<task-notification" not in (txt or ""):
        return tuple(out)
    m = _ST_RE.search(txt)
    if not m or m.group(1) not in ("failed", "killed"):
        return tuple(out)
    sm = _SUMM_FULL.search(txt)
    s = (sm.group(1).strip() if sm else "")[:300]
    tm = _TUID_RE.search(txt)
    tid = tm.group(1) if tm else ""
    if "was stopped by user" in s or "stopped by the user" in s:
        # ★The raw text itself says the user stopped it — this is not a failure.
        out.append({"at": at, "kind": "stop", "tid": tid, "cwd": cwd, "st": m.group(1),
                    "sig": "중단 — 내가 멈춤", "text": s,
                    "grade": "mine", "why": "was stopped by user"})
        return tuple(out)
    if s.startswith("Agent "):
        kind = "agent"
    elif s.startswith("Monitor "):
        kind = "monitor"
    else:
        kind = "bg"
    # ★Watchers and background jobs stopped by a human are not failures — `killed` is usually us turning them off.
    #   Keep only agents' killed (cut off midway, so wreckage may remain).
    if m.group(1) == "killed" and kind != "agent":
        return tuple(out)
    sig = _fail_sig(s) or {"agent": "서브에이전트 " + m.group(1),
                           "monitor": "감시 " + m.group(1)}.get(kind, "백그라운드 " + m.group(1))
    _g, _w = _fail_grade(kind, s)
    out.append({"at": at, "kind": kind, "tid": tid, "cwd": cwd,
                "sig": sig, "text": s, "st": m.group(1), "grade": _g, "why": _w})
    return tuple(out)


def _fail_read(fp):
    """Scan from after the last read to the end and **accumulate** events. A first-seen file is read whole.

    ★Whole-file sounds scary, but byte-level filtering makes 1GB take seconds (measured, see comments below).
      And only once — afterwards only newly written bytes are read.

    ★2026-09-07 — **never read while holding the lock** (a long hold freezes every failure tab). Split into three parts:
        ⓐ short lock — fix the read offset (`off`) and take the "scanning" flag
        ⓑ **outside** the lock — read the file, collecting events in **local variables** (cold 40 files measured 2.81 s)
        ⓒ short lock — insert what was collected, advance the offset, release the flag
      Measured (2026-09-07): before = `_FAIL_LOCK` held for the whole cold 2.81 s · after = held only in ⓐⓒ (microseconds).
    ⚠**Returns a snapshot (copy)**. Previously `_FAIL_EV[fp]` was returned directly and callers had to take the lock
      and copy with `list(...)` — that contract moved in here. Callers no longer need the lock."""
    # ⓐ fix offset + acquire scan right — the lock covers only this far
    with _FAIL_SCAN:
        deadline = time.time() + FAIL_SCAN_WAIT_S
        while fp in _FAIL_BUSY:
            # ★someone else is reading this file — **wait** (a half list would be the lie "no failures").
            #   The lock is released while waiting, so other files and paths are not blocked.
            #   ⚠Capped: if a read hangs somewhere, the whole poll hanging is worse.
            if not _FAIL_SCAN.wait(max(0.0, deadline - time.time())) and fp in _FAIL_BUSY:
                warn_once(f"failscan:{os.path.basename(fp)}",
                          "Failure scan took over {n}s ({file}) — that file's failures are missing from the list",
                          vars={"n": FAIL_SCAN_WAIT_S, "file": os.path.basename(fp)})
                return list(_FAIL_EV.get(fp) or [])
        # ★Size is measured **after the wait ends** (2026-09-07). The earlier thread advances `_FAIL_OFF` meanwhile,
        #   so a size measured before waiting gives `off > size`, **misjudged** as "file truncated", and the file's
        #   events are dropped wholesale and rescanned from scratch. A stat inside the lock is microseconds.
        try:
            size = os.path.getsize(fp)
        except OSError:
            return list(_FAIL_EV.get(fp) or [])
        off = _FAIL_OFF.get(fp)
        if off is None:
            off = 0                               # first-seen file — scan it whole
        if off > size:                            # file was recreated (truncated)
            off = 0
            _FAIL_EV.pop(fp, None)
            _FAIL_TNAME.pop(fp, None)
        evs = _FAIL_EV.setdefault(fp, [])
        if off >= size:
            return list(evs)                      # nothing new written — don't read
        _FAIL_BUSY.add(fp)
        names = dict(_FAIL_TNAME.get(fp) or {})
    # ⓑ this is **outside** the lock — the slow part. Collected items go only into local variables.
    got = []
    rem = b""
    # ★The stored offset is the byte right after the last consumed `\n` (2026-09-25). Storing `size` and then
    #   always dropping the first line after `off > 0` lost one complete new line per incremental read
    #   (repro: 1 line -> 1, +1 -> still 1, +2 -> 2), and a line cut mid-write was dropped on both sides.
    #   ⚠Drop a first line only when `off` is truly mid-line (byte before it is not `\n`).
    skip_first = False
    new_off = off
    try:
        try:
            with open(fp, "rb") as f:
                if off > 0:
                    f.seek(off - 1)
                    skip_first = f.read(1) != b"\n"
                f.seek(off)
                while True:
                    chunk = f.read(FAIL_CHUNK)
                    if not chunk:
                        break
                    parts = (rem + chunk).split(b"\n")
                    rem = parts.pop()             # trailing partial line: left for the next read
                    new_off += len(chunk)
                    if skip_first and parts:
                        parts.pop(0)              # drop the truncated first line
                        skip_first = False
                    for raw in parts:
                        if not raw.startswith(b"{"):
                            continue
                        if _TU_MARK_B in raw:
                            for tid_b, nm_b in _TU_NAME_RE.findall(raw):
                                names[tid_b.decode("ascii", "replace")] = nm_b.decode("utf-8", "replace")
                        hit = False
                        for k in _FAIL_MARK_B:
                            if k in raw:
                                hit = True
                                break
                        if hit:
                            got.extend(_fail_line(raw.decode("utf-8", "replace"), names))
        except OSError:
            pass
        new_off -= len(rem)                       # resume at the start of the unfinished line
        # ⓒ swap in — hold the lock briefly again only while inserting the finished values
        with _FAIL_SCAN:
            evs = _FAIL_EV.setdefault(fp, [])
            evs.extend(got)
            _FAIL_OFF[fp] = new_off
            _FAIL_TNAME[fp] = dict(list(names.items())[-FAIL_TNAME_KEEP:])
            old = time.time() - FAIL_SEEN_H * 3600
            if len(evs) > FAIL_KEEP or (evs and evs[0]["at"] < old):
                keep = [x for x in evs if x["at"] >= old][-FAIL_KEEP:]
                evs[:] = keep
            return list(evs)
    finally:
        # ⚠whatever blows up while reading, always release the flag — otherwise the file stays "scanning" forever
        with _FAIL_SCAN:
            _FAIL_BUSY.discard(fp)
            _FAIL_SCAN.notify_all()


def _fail_sub_id(fp):
    """(session directory, agent id) if the path is a subagent transcript, else ("", "")."""
    base = os.path.basename(fp)
    sd = sub_sess_dir(fp)                      # plain or Workflow-tool agent (one level deeper)
    if not sd or not base.startswith("agent-"):
        return "", ""
    return sd, base[len("agent-"):-len(".jsonl")]


def _fail_transcripts(now, max_age_h, capped=True):
    """Files for the failure scan [(mtime, path)] — **main sessions + subagents**. Newest first.

    ★Why not `_recent_transcripts` (2026-09-07; failures were useless without knowing which subagent and task
      produced them): that function scans only **one level**, `<project>/<session>.jsonl`, so subagent logs
      (`<project>/<session>/subagents/agent-<id>.jsonl`) were **never scanned**.
      Measured (2026-09-07): 38 subagent logs in the last 24 h held 75 failure events, yet
      `/api/failures?h=24` caught **0** of them (52 from main sessions only).
    ⚠Do not make that function recursive — `sessions()` and others share it, so subagents would show up
      **as sessions in the session list**. Hence the list is widened only for the failure scan.
    ★Quotas are cut separately: main FAIL_MAX_FILES · subagents FAIL_SUB_MAX_FILES.
      Cutting one combined bucket pushes out main-session files and **failures visible now disappear** (see cap comment above)."""
    # ★capped=False (retro only): every file in the window — the count caps undercounted early 30-day days (08-28: 7 of 50).
    main = _recent_transcripts(now, max_age_h)[:(FAIL_MAX_FILES if capped else None)]
    subs = []
    # ★dig directly with glob — child logs must be seen even when the parent transcript leaves the window.
    #   Measured: glob + stat over all 2,084 files is 0.013 s (negligible).
    for fp in [p for r in projects_dirs(CLAUDE_PROJECTS) for p in sub_paths(r) if os.path.basename(p).startswith("agent-")]:
        try:
            mt = os.path.getmtime(fp)
        except OSError:
            continue
        if now - mt <= max_age_h * 3600:
            subs.append((mt, fp))
    subs.sort(reverse=True)
    files = main + subs[:(FAIL_SUB_MAX_FILES if capped else None)]
    files.sort(reverse=True)
    return files


FAIL_PRUNE_S = 600
_FAIL_PRUNED = [0.0]


def _fail_prune(now):
    """Drop cached state for transcripts that are gone or older than FAIL_SEEN_H (bounded growth).
    ⚠Not "files outside this call's list": callers differ in hours/caps, and evicting a file another
    caller still scans would force a cold rescan of it on every alternation."""
    if now - _FAIL_PRUNED[0] < FAIL_PRUNE_S:
        return
    _FAIL_PRUNED[0] = now
    old = now - FAIL_SEEN_H * 3600
    with _FAIL_SCAN:
        keys = [k for k in set(_FAIL_EV) | set(_FAIL_OFF) if k not in _FAIL_BUSY]
    dead = []
    for fp in keys:
        try:
            if os.path.getmtime(fp) < old:
                dead.append(fp)
        except OSError:
            dead.append(fp)
    if dead:
        with _FAIL_SCAN:
            for fp in dead:
                if fp not in _FAIL_BUSY:
                    _FAIL_EV.pop(fp, None)
                    _FAIL_OFF.pop(fp, None)
                    _FAIL_TNAME.pop(fp, None)


def _fail_events(hours, capped=True):
    """Failure events in the window (deduplicated, agent type attached). Shared by `failures` and `wreckage`."""
    now = time.time()
    hours = max(0.5, min(FAIL_SEEN_H, float(hours)))
    cut = now - hours * 3600
    files = _fail_transcripts(now, max(hours, 24), capped)
    _fail_prune(now)
    evs, seen = [], set()
    # ★No lock here (2026-09-07) — `_fail_read` holds it briefly per file only at "read offset / insert events"
    #   and returns a snapshot (copy). This one line used to swallow the cold full scan's **2.81 s with the lock held**.
    #   ⚠The lock is released between files, so files A and B are snapshotted at different moments. Why that is fine:
    #     events are **append-only** (cumulative log), and the `seen` dedup below keys on events, not files
    #     ⇒ a skew only means "a just-created event shows on the next poll"; nothing appears from nowhere or is double-counted.
    raw = [(fp, _fail_read(fp)) for _mt, fp in files]
    for fp, got in raw:
        ssd, said = _fail_sub_id(fp)
        # for a subagent log, the "parent session directory" is where meta lives
        sd = ssd or fp[:-len(".jsonl")]
        meta = None
        byid = None
        for ev in got:
            if ev["at"] < cut:
                continue
            # ★Completion notifications arrive **more than once per event** (measured: 40 events → 67 messages). A tool-use-id
            #   identifies one agent run, so when present it alone defines the same event.
            key = ((ev["tid"], ev["sig"]) if ev["tid"]
                   else (ev["kind"], ev["sig"], ev["text"][:80], ev["at"] // 60))
            if key in seen:
                continue
            seen.add(key)
            ev = dict(ev)
            if ev["kind"] == "agent" and ev["tid"]:
                if meta is None:
                    meta = _agent_meta(sd, ttl=60)
                m = meta.get(ev["tid"]) or {}
                ev["type"] = m.get("agentType") or ""
                ev["adesc"] = redact(m.get("description") or "")[:70]
                af = m.get("_file") or ""
                if af and os.path.exists(af):
                    ev["afile"] = af
            # ★Identity is attached regardless of `kind` (2026-09-07; without it the user had no action to take).
            #   The branch above names only **completion notices in the parent transcript** (kind=="agent").
            #   Hook blocks, tool errors and API errors have kind hook/tool/api, so even inside a subagent their
            #   `type`·`adesc` were blank (measured: every `/api/failures` row had "types": {}).
            #   ⇒ Fill identity from **the file path the event came from**. The file name is the agent id, so
            #     reverse-indexing `_agent_meta` by `_id` yields type and task description (same pattern as above).
            if said:
                if not ev.get("type"):
                    if byid is None:
                        byid = {}
                        for _m in _agent_meta(sd, ttl=60).values():
                            if _m.get("_id"):
                                byid[_m["_id"]] = _m
                    m2 = byid.get(said) or {}
                    ev["type"] = m2.get("agentType") or ""
                    ev["adesc"] = redact(m2.get("description") or "")[:70]
                    ev["depth"] = int(m2.get("spawnDepth") or 1)
                    ev["par"] = m2.get("parentAgentId") or ""
                    # ⚠`afile` goes only on **events without a tid**. One with a tid is "another (child)'s
                    #   completion notice"; recording this file carrying the notice as that child's log makes
                    #   `wreckage` read **the wrong agent's file list** (false wreckage).
                    if not ev["tid"]:
                        ev["afile"] = fp
                # ★Lineage — the user must know **which session to go to** for action to be possible.
                #   proj (working path) alone cannot find it when several sessions share the path.
                ev["aid"] = said
                ev["sess"] = os.path.basename(sd)
            ev["proj"] = _proj_name(ev.get("cwd") or "")
            ev["sid"] = os.path.basename(sd)     # owning session id — alert cards open its work log
            evs.append(ev)
    return evs, len(files), round(hours, 1)
