"""OTLP intake: state the harness reports directly."""
import json
import os
import threading
import time
from sidereus.config import DATA_DIR
from sidereus.bus import _atomic_write
from sidereus.memo import BoundedMemo
from sidereus.otel_acct import _oa_cache, _oa_hook, _oa_label, _oa_save, _oa_src, _oa_tool
from sidereus.otel_cache import _oc_add, _oc_save
from sidereus.otel_hooks import _oh_add, _oh_int, _oh_save
from sidereus.timefmt import ymd as _ymd
from sidereus.usage import _usage_add, _uidx_hours, _uidx_refresh


# ── OTLP intake — **state the harness reports directly** (2026-08-19; sought an open, measurable source) ──
#   ★Why: until now state was **inferred** by tailing transcript files, and it kept being wrong —
#     ⓐ an Agent's tool_result was a receipt, not completion ⓑ completion notices get lost
#     ⓒ some things were never written to the transcript at all (reply in the terminal, no record in the file).
#   Claude Code supports **official OpenTelemetry** (`code.claude.com/docs/en/monitoring-usage`).
#   Measured 2026-08-19: `OTEL_EXPORTER_OTLP_PROTOCOL=http/json` works, so it is received right here **with no dependencies**
#     (no collector, Docker or Grafana — this server is already an HTTP server).
#   Events received: user_prompt (turn start) · tool_decision/tool_result (tools) · api_request (tokens) · assistant_response (turn end).
#   ⛔No bodies — `OTEL_LOG_USER_PROMPTS`·`ASSISTANT_RESPONSES`·`TOOL_DETAILS` are left off
#     (turning them on ships prompts, replies and tool args. This file's rule: conversation content never goes on screen).
# ★Limit on trusting OTel's "working". If the transcript is quiet longer than this, events alone do not
#   claim `Thinking`·`Running a tool` (see the _session_row comment above).
OTEL_TRUST_S = 300
OTEL_KEEP = {"user_prompt", "assistant_response", "api_request", "tool_decision", "tool_result",
             "api_error", "permission_mode_changed"}
_otel = {}          # session.id -> latest state {"ev","at","tool","tokens","seq"}
_otel_sample = {}   # diagnostics — **all attributes** of the last api_request (to check whether quota info arrives)
# ★**Received vs dropped** (2026-09-09; real-time tokens showed zero). `/api/otel` used to show only
#   "who is sending" — so when real-time went to 0, "not arriving" and "arrived but dropped" could not be told apart
#   (a synthetic POST was received fine while session events had stalled for 5 min).
#   ⇒ Count drops per filter: name (outside `OTEL_KEEP`) · sequence (late old event) · no session id.
_otel_stat = {"posts": 0, "recs": 0, "kept": 0, "dropName": 0, "dropSeq": 0, "dropSid": 0,
              "acct": 0, "dupReq": 0, "reSeq": 0, "names": {}, "lastPost": 0, "lastKept": 0, "hooks": 0,
              "acctUnk": 0}
OTEL_SRC_CAP = 64
# ★Persisted per-bucket bySrc (2026-09-24): `bySrc` above zeroes on every restart, but the +37% OTel-vs-transcript
#   gap needs a 5h window and the user keeps restarting for feature work. ⇒ 5-min buckets on disk, 8 days kept.
#   ⚠Cap is per bucket (same 64 + "other" rule). ⚠Disk IO only from `_today_loop` (≤ every 60s) — ingest never touches disk.
OTEL_SRC_FILE = os.path.join(DATA_DIR, "otel-bysrc.json")
OTEL_SRC_STEP = 300
OTEL_SRC_KEEP = 8 * 86400
OTEL_SRC_SAVE_S = 60
_otel_src = {}      # bucket start epoch (int) -> {"model|query_source": [count, tokens]}
_otel_src_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}
_otel_req = BoundedMemo(4000)   # `request_id`s already accounted — used only to avoid double-counting retransmits
# ★**Cumulative tool success/failure** (2026-09-21). `tool_result`'s name and success were held as `lastTool`·`ok`,
#   **last value only**, and `_otel_state()` did not return them, so they were dropped before reaching the screen.
#   The failure tab thus saw only transcripts, and nobody could answer "which tool fails how often".
#   ⇒ One in-memory counter only (no new file on disk).
#   ⛔It holds **only tool names and counts** — arguments and result bodies are never even received (metadata only, never conversation text).
#   ⚠A server restart starts from 0. The screen tooltip states that ("counted since server start").
OTEL_TOOL_MAX = 40          # cap on distinct tool names per session — beyond it merge into `Other` (names grow unbounded)
_otel_tools = {}            # session.id -> {tool name: [calls, failures]}
_otel_tools_all = {}        # all-session totals — same shape. Survives session cleanup (so the screen can count)
_OTEL_TOOLS_SINCE = time.time()   # time this counter was 0 = server start
# Per-day tool tally for the retro rank card; persisted so a restart keeps it. Metadata only (name · counts · ms).
OTEL_TDAY_FILE = os.path.join(DATA_DIR, "otel-tools.json")
OTEL_TDAY_KEEP_D = 31
OTEL_TDAY_CAP = 160         # names per day; beyond it merge into `Other`
_otel_tday = {}             # ymd -> {tool name: [calls, failures, durMsSum, durN, failDurMs]}
# ⚠Files written before failDurMs hold 4-element rows; the load pads them with 0 (never drop them).
_otel_tday_meta = {"loaded": False, "savedAt": 0.0, "dirty": False}
# ★**Limit** of the sequence guard. `event.sequence` is **not** monotonic over a session's life (when the exporter
#   reconnects it counts from 1 again — measured 2026-09-09). So "went backwards" is split two ways.
OTEL_SEQ_BACK = 100        # a backward jump larger than this is a counter reset; follow the new base
OTEL_SEQ_STALE_S = 60      # quiet this long ⇒ give up on sequence comparison (no "now" to compare against)
_otel_lock = threading.Lock()


def _otel_val(v):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return v[k]
    return None


def _otel_ok(v):
    """The `success` attribute comes as a bool or a string ("true") — accept both. None if unreadable."""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "ok", "success"):
        return True
    if s in ("false", "0", "error", "failure"):
        return False
    return None


def _otel_tool_count(sid, name, success, dur_ms=None, ts=None):
    """Increment one tool tally — `[calls, failures]` (+ the per-day row with duration).

    ⚠Called **with `_otel_lock` held** (the caller already holds it — taking it again here deadlocks).
    ★If success is unreadable, count the call but not a failure — unknown is never called failure."""
    bad = 1 if _otel_ok(success) is False else 0
    nm = (str(name).strip() if name else "") or "(이름 없음)"
    for d, cap in ((_otel_tools.setdefault(sid, {}), OTEL_TOOL_MAX),
                   (_otel_tools_all, OTEL_TOOL_MAX * 4)):
        k = nm if (nm in d or len(d) < cap) else "기타"
        c = d.setdefault(k, [0, 0])
        c[0] += 1
        c[1] += bad
    _otel_tday_add(_ymd(ts if ts is not None else time.time()), nm, bad, dur_ms)
    return nm, bad


def _otel_tday_add(day, nm, bad, dur_ms):
    """Bump one day row. ⚠Caller holds `_otel_lock`."""
    d = _otel_tday.setdefault(day, {})
    c = d.setdefault(nm if (nm in d or len(d) < OTEL_TDAY_CAP) else "기타", [0, 0, 0.0, 0, 0.0])
    c[0] += 1
    c[1] += bad
    try:
        ms = float(dur_ms) if dur_ms is not None else -1.0
    except (TypeError, ValueError):
        ms = -1.0
    if ms >= 0:
        c[2] += ms
        c[3] += 1
        if bad:
            c[4] += ms
    _otel_tday_meta["dirty"] = True


def _otel_tday_load():
    """Merge the saved day rows into memory (adds, so tools counted before the load are kept)."""
    try:
        with open(OTEL_TDAY_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = None
    src = (d.get("d") if isinstance(d, dict) else None) or {}
    with _otel_lock:
        if _otel_tday_meta["loaded"]:   # ⚠save loop and a retro request can race here — a second merge double-counts
            return
        _otel_tday_meta["loaded"] = True
        for day, row in (src.items() if isinstance(src, dict) else ()):
            if not (isinstance(day, str) and isinstance(row, dict)):
                continue
            dst = _otel_tday.setdefault(day, {})
            for k, v in row.items():
                if not (isinstance(v, list) and len(v) in (4, 5)):
                    continue
                kk = k if (k in dst or len(dst) < OTEL_TDAY_CAP) else "기타"
                c = dst.setdefault(kk, [0, 0, 0.0, 0, 0.0])
                try:
                    c[0] += int(v[0] or 0)
                    c[1] += int(v[1] or 0)
                    c[2] += float(v[2] or 0)
                    c[3] += int(v[3] or 0)
                    c[4] += float(v[4] or 0) if len(v) == 5 else 0.0
                except (TypeError, ValueError):
                    continue


def _otel_tday_save(now=None, force=False):
    """Prune days older than 31 and write atomically — at most every 60s, only when changed. Returns True if written."""
    now = now or time.time()
    if not _otel_tday_meta["loaded"]:
        _otel_tday_load()
    if not force and now - _otel_tday_meta["savedAt"] < OTEL_SRC_SAVE_S:
        return False
    cut = _ymd(now - OTEL_TDAY_KEEP_D * 86400)
    with _otel_lock:
        old = [k for k in _otel_tday if k < cut]
        for k in old:
            _otel_tday.pop(k, None)
        if not (old or _otel_tday_meta["dirty"] or force):
            return False
        blob = json.dumps({"v": 1, "d": _otel_tday}, separators=(",", ":"), ensure_ascii=False)
        _otel_tday_meta["dirty"] = False
    _otel_tday_meta["savedAt"] = now
    try:
        _atomic_write(OTEL_TDAY_FILE, blob.encode("utf-8"), prefix=".otel-tools.")
    except OSError:
        _otel_tday_meta["dirty"] = True
        return False
    return True


def _otel_tool_rank(since_ymd, top=5, rest=200, src=None):
    """Tool calls summed over days >= since_ymd, most-called first. ok = % not explicitly failed · ms = mean duration.
    tms = calls x mean ms (calls without a duration count at the mean) · fms = % of measured time spent on failed calls.
    `time` = the same rows ranked by tms (rows with no duration left out). src = one account's day rows (None = all)."""
    if not _otel_tday_meta["loaded"]:
        _otel_tday_load()
    tday = _otel_tday if src is None else src
    acc = {}
    with _otel_lock:
        held = sorted(tday)
        for day in held:
            if day < since_ymd:
                continue
            for k, v in tday[day].items():
                a = acc.setdefault(k, [0, 0, 0.0, 0, 0.0])
                for i in range(len(v)):
                    a[i] += v[i]
    rows = [{"n": k, "calls": v[0], "ok": (round(100.0 * (v[0] - v[1]) / v[0], 1) if v[0] else None),
             "ms": (int(round(v[2] / v[3])) if v[3] else None),
             "tms": (int(round(v[0] * v[2] / v[3])) if v[3] else 0),
             "fms": (int(round(100.0 * v[4] / v[2])) if v[2] > 0 else 0)} for k, v in acc.items()]
    rows.sort(key=lambda r: (-r["calls"], r["n"]))
    tail = rows[top:]
    timed = sorted((r for r in rows if r["tms"] > 0), key=lambda r: (-r["tms"], r["n"]))
    # ⚠from is clamped to the range start — held[0] alone named a day before the range («Last 7 days · 9/5~»).
    # live = OTel events kept since start, so «0 tool calls» is not shown as «no OTel data».
    return {"top": rows[:top], "rest": tail[:rest], "restN": len(tail),
            "calls": sum(r["calls"] for r in rows), "from": (max(held[0], since_ymd) if held else None),
            "live": int(_otel_stat.get("kept") or 0) > 0,
            "time": {"rows": timed[:top], "restN": max(0, len(timed) - top)}}


def _otel_tools_summary(top=40):
    """All-session tool tallies — {rows:[[name,calls,failures],…], kinds, since}. Sorted by failures descending.
    ⚠Counts only since server start (memory only). The screen states that."""
    with _otel_lock:
        items = [[k, v[0], v[1]] for k, v in _otel_tools_all.items()]
    items.sort(key=lambda x: (-x[2], -x[1]))
    return {"rows": items[:top], "kinds": len(items), "since": int(_OTEL_TOOLS_SINCE)}


def _otel_src_add(ts, key, tokens):
    """Add one api_request to its 5-min bucket. ⚠Caller holds `_otel_lock`."""
    b = int(ts // OTEL_SRC_STEP * OTEL_SRC_STEP)
    d = _otel_src.setdefault(b, {})
    k = key if (key in d or len(d) < OTEL_SRC_CAP) else "other"
    c = d.setdefault(k, [0, 0])
    c[0] += 1
    c[1] += int(tokens or 0)
    _otel_src_meta["dirty"] = True


def _otel_src_load():
    """Merge the saved buckets into memory (adds, so events ingested before the load are kept)."""
    try:
        with open(OTEL_SRC_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = None
    src = (d.get("b") if isinstance(d, dict) else None) or {}
    cut = time.time() - OTEL_SRC_KEEP
    with _otel_lock:
        _otel_src_meta["loaded"] = True
        for bk, row in (src.items() if isinstance(src, dict) else ()):
            try:
                b = int(bk)
            except (TypeError, ValueError):
                continue
            if b < cut or not isinstance(row, dict):
                continue
            dst = _otel_src.setdefault(b, {})
            for k, v in row.items():
                if not (isinstance(v, list) and len(v) == 2):
                    continue
                kk = k if (k in dst or len(dst) < OTEL_SRC_CAP) else "other"
                c = dst.setdefault(kk, [0, 0])
                c[0] += int(v[0] or 0)
                c[1] += int(v[1] or 0)


def _otel_src_save(now=None, force=False):
    """Prune buckets older than 8 days and write atomically — at most every 60s, only when changed.
    Called from `_today_loop` (30s cycle); the first call loads the file first. Returns True if written."""
    now = now or time.time()
    _otel_tday_save(now)
    _oc_save(now)
    _oh_save(now)
    _oa_save(now)
    if not _otel_src_meta["loaded"]:
        _otel_src_load()
    if not force and now - _otel_src_meta["savedAt"] < OTEL_SRC_SAVE_S:
        return False
    cut = now - OTEL_SRC_KEEP
    with _otel_lock:
        old = [b for b in _otel_src if b < cut]
        for b in old:
            _otel_src.pop(b, None)
        if not (old or _otel_src_meta["dirty"] or force):
            return False
        blob = json.dumps({"v": 1, "step": OTEL_SRC_STEP,
                           "b": {str(b): r for b, r in _otel_src.items()}},
                          separators=(",", ":"))
        _otel_src_meta["dirty"] = False
    _otel_src_meta["savedAt"] = now
    try:
        _atomic_write(OTEL_SRC_FILE, blob.encode("utf-8"), prefix=".otel-bysrc.")
    except OSError:
        _otel_src_meta["dirty"] = True
        return False
    return True


def _otel_src_win(h=5, now=None, start=None):
    """Sum buckets overlapping the last `h` hours (or from `start`). {h, from, since, total, rows:{key:[count,tokens]}}.
    `since` = oldest bucket held — how much history the window can actually cover."""
    now = now or time.time()
    frm = start if start is not None else now - h * 3600
    rows = {}
    with _otel_lock:
        since = min(_otel_src) if _otel_src else None
        for b, r in _otel_src.items():
            if b + OTEL_SRC_STEP <= frm or b > now:
                continue
            for k, v in r.items():
                c = rows.setdefault(k, [0, 0])
                c[0] += v[0]
                c[1] += v[1]
    return {"h": h, "from": int(frm), "since": since, "total": sum(v[1] for v in rows.values()),
            "rows": rows}


def _otel_src_heat(start, now=None, src=None):
    """Weekday (Mon=0) x local hour grid of api_request counts/tokens from `start` (retro «Activity by hour»).
    {from, since, n, cells: 7x24 [count, tokens]} — every key folded together, no model/source names leave here.
    ⚠Range is capped by OTEL_SRC_KEEP (8 days): a 30-day view covers only what the buckets still hold."""
    now = now or time.time()
    bs = _otel_src if src is None else src
    cells = [[[0, 0] for _h in range(24)] for _d in range(7)]
    n = 0
    with _otel_lock:
        since = min(bs) if bs else None
        for b, r in bs.items():
            if b < start or b > now:
                continue
            lt = time.localtime(b)
            c = cells[lt.tm_wday][lt.tm_hour]
            for v in r.values():
                c[0] += v[0]
                c[1] += v[1]
                n += v[0]
    return {"from": int(start), "since": since, "n": n, "cells": cells}


def _otel_src_models(start, now=None, src=None):
    """R1/R2 retro «Models»: api_request counts/tokens per model from `start`, split main/agent/side by query_source.
    {from, since, n, rows: [{model, count, tokens, kinds: {main, agent, side}: [count, tokens]}]} sorted by tokens.
    ⚠Only the model id and the folded kind leave here — query_source (agent names) stays server-side.
    The overflow key "other" becomes one model row "other". src = one account's buckets (None = all)."""
    now = now or time.time()
    bs = _otel_src if src is None else src
    acc = {}
    n = 0
    with _otel_lock:
        since = min(bs) if bs else None
        for b, r in bs.items():
            if b < start or b > now:
                continue
            for k, v in r.items():
                m = k.split("|", 1)[0] if "|" in k else k
                row = acc.get(m)
                if row is None:
                    row = acc[m] = {"model": m, "count": 0, "tokens": 0,
                                    "kinds": {"main": [0, 0], "agent": [0, 0], "side": [0, 0]}}
                row["count"] += v[0]
                row["tokens"] += v[1]
                kc = row["kinds"][_otel_src_kind(k)]
                kc[0] += v[0]
                kc[1] += v[1]
                n += v[0]
    rows = sorted(acc.values(), key=lambda x: (-x["tokens"], -x["count"], x["model"]))
    return {"from": int(start), "since": since, "n": n, "rows": rows}


def _otel_src_kind(key):
    """model|query_source -> main (repl_main_thread) · agent (agent:*) · side (summaries, suggestions, rest)."""
    src = key.split("|", 1)[1] if "|" in key else key
    if src == "repl_main_thread":
        return "main"
    if src.startswith("agent:"):
        return "agent"
    return "side"


def _otel_src_cmp(h=5, now=None, hours=None):
    """OTel tokens vs transcript tokens (`usage-index` hour buckets, the source of the +37% figure) over the same window.
    ★Window = whole hours only (transcript side is hour-bucketed), starting no earlier than the first full hour
      OTel holds — so both sides cover the same span. `covered` False = OTel history shorter than `h`.
    Metadata only (token counts per model|query_source)."""
    now = now or time.time()
    want = int((now - h * 3600) // 3600 * 3600)
    with _otel_lock:
        since = min(_otel_src) if _otel_src else None
    start = int(-(-since // 3600) * 3600) if (since is not None and since > want) else want
    if hours is None:
        try:
            _uidx_refresh()
        except Exception:
            pass                # hour buckets fall back to the last index (stale, not empty)
        hours = _uidx_hours()
    tr = 0
    for k, mm in hours.items():
        if int(k) >= start:
            for v in mm.values():
                tr += sum(v[:4])
    w = _otel_src_win(h, now, start=start)
    kind = {"main": 0, "agent": 0, "side": 0}
    for k, v in w["rows"].items():
        kind[_otel_src_kind(k)] += v[1]
    kind["nonMain"] = kind["agent"] + kind["side"]
    ot = w["total"]
    return {"h": h, "from": start, "to": int(now), "since": since, "covered": start == want,
            "otelTotal": ot, "transcriptTotal": tr,
            "ratio": round(ot / tr, 4) if tr else None,
            "ratioNoSide": round((ot - kind["side"]) / tr, 4) if tr else None,
            "byKind": kind}


def _otel_acct_add(lab, fn, *args):
    """Per-account add, or count the record as unknown-account (All only). ⚠Caller holds `_otel_lock`."""
    if lab is None:
        _otel_stat["acctUnk"] = (_otel_stat.get("acctUnk") or 0) + 1
    else:
        fn(lab, time.time(), *args)


def _otel_ingest(payload):
    """Receive OTLP/JSON logs and keep only the latest state per session. **Raw records are not stored** (memory, privacy)."""
    n = 0
    for rl in (payload.get("resourceLogs") or []):
        for sl in (rl.get("scopeLogs") or []):
            for lr in (sl.get("logRecords") or []):
                at = {a.get("key"): _otel_val(a.get("value") or {}) for a in (lr.get("attributes") or [])}
                ev = at.get("event.name")
                sid = at.get("session.id")
                # per-account copy: resolved outside `_otel_lock` (stat of the SessionStart record); None = unknown
                lab = _oa_label(sid) if ev in ("api_request", "tool_result", "hook_execution_complete") else None
                # ★diagnostic counts — count the name first (what arrived is kept even if dropped), then filter.
                with _otel_lock:
                    _otel_stat["recs"] += 1
                    nm = _otel_stat["names"]
                    if len(nm) < 40:
                        nm[str(ev)] = (nm.get(str(ev)) or 0) + 1
                    # R1/R4: hook firings feed only the retro aggregate — not OTEL_KEEP, kept/drop counts or live state.
                    if ev == "hook_execution_complete":
                        _otel_stat["hooks"] = (_otel_stat.get("hooks") or 0) + 1
                        # fails exclude num_blocking: a block is the hook's decision, not a failure.
                        _hf = _oh_int(at.get("num_non_blocking_error")) + _oh_int(at.get("num_cancelled"))
                        _oh_add(time.time(), at.get("hook_event"), at.get("total_duration_ms"), _hf)
                        _otel_acct_add(lab, _oa_hook, at.get("hook_event"), at.get("total_duration_ms"), _hf)
                        continue
                    if not ev or ev not in OTEL_KEEP:
                        _otel_stat["dropName"] += 1
                    elif not sid:
                        _otel_stat["dropSid"] += 1
                if not ev or not sid or ev not in OTEL_KEEP:
                    continue
                n += 1
                with _otel_lock:
                    cur = _otel.setdefault(sid, {})
                    seq = at.get("event.sequence") or 0
                    try:
                        seq = int(seq)
                    except Exception:
                        seq = 0
                    # ★**Accounting comes before the order guard** (2026-09-09; real-time tokens showed zero).
                    #   A sum ignores order — even a late `api_request`'s tokens were really used. It used to sit
                    #   **inside** the guard below, so once the guard blocked, real-time tokens went to 0 entirely
                    #   (measured: all 5 sessions at 0 for 5~10 min).
                    # ⚠`request_id` is remembered against retransmits — the only duplication risk the order guard
                    #   covered, so moving out of the guard replaces it with this.
                    if ev == "api_request":
                        rq = at.get("request_id") or at.get("client_request_id") or ""
                        if rq and rq in _otel_req:
                            _otel_stat["dupReq"] += 1
                        else:
                            if rq:
                                _otel_req.put(rq, 1)
                            _otel_sample.clear()
                            _otel_sample.update(at)
                            _tkn = sum(int(at.get(k) or 0) for k in
                                       ("input_tokens", "cache_read_tokens", "cache_creation_tokens"))
                            # one event = **one API call** (output included in the count)
                            _tkn += int(at.get("output_tokens") or 0)
                            _usage_add(time.time(), _tkn, float(at.get("cost_usd") or 0), sid)
                            # read/creation split only; ⚠_oc_add takes its own lock, never `_otel_lock` (held here)
                            _oc_add(time.time(), sid, at.get("cache_read_tokens"), at.get("cache_creation_tokens"))
                            _otel_acct_add(lab, _oa_cache, sid, at.get("cache_read_tokens"), at.get("cache_creation_tokens"))
                            _otel_stat["acct"] += 1
                            # ★Per model|query_source split (2026-09-24): OTel ran +37% over transcripts; this separates side calls. Capped at 64 keys (+"other").
                            _bs = _otel_stat.setdefault("bySrc", {})
                            _bk = "%s|%s" % (at.get("model") or "-", at.get("query_source") or "-")
                            _otel_src_add(time.time(), _bk, _tkn)
                            if lab is not None:
                                _oa_src(lab, time.time(), _bk, _tkn)
                            _bk = _bk if _bk in _bs or len(_bs) < OTEL_SRC_CAP else "other"
                            _c = _bs.setdefault(_bk, [0, 0])
                            _c[0] += 1
                            _c[1] += _tkn
                    prev = cur.get("seq") or 0
                    if seq and seq < prev:
                        # ★A **large** backward jump is not "a late old event" but **the exporter's counter
                        #   resetting** (measured 2026-09-09: after a viewer restart the same live sessions' seq
                        #   dropped 5182→210 · 58528→1241 — the sessions were unchanged). Then every new event
                        #   is below the old sequence and is dropped **forever**. That is how real-time went to 0.
                        # ⇒ On a large jump back, or after a quiet spell, **follow the new counter**.
                        if prev - seq > OTEL_SEQ_BACK or \
                                (time.time() - (cur.get("at") or 0)) > OTEL_SEQ_STALE_S:
                            prev = 0
                            _otel_stat["reSeq"] += 1
                        else:
                            _otel_stat["dropSeq"] += 1
                            continue                 # reordered within one batch — state uses only the latest
                    _otel_stat["kept"] += 1
                    _otel_stat["lastKept"] = time.time()
                    cur["seq"] = seq or prev or 0
                    cur["ev"] = ev
                    cur["at"] = time.time()
                    if ev in ("tool_decision", "tool_result"):
                        cur["tool"] = at.get("tool_name") or cur.get("tool")
                        if ev == "tool_result":
                            cur["lastTool"] = at.get("tool_name")
                            cur["ok"] = at.get("success")
                            # ★a last value alone gets overwritten by the next event ⇒ also bump the tally (name and count only)
                            _nm, _bad = _otel_tool_count(sid, at.get("tool_name"), at.get("success"),
                                                         at.get("duration_ms"), time.time())
                            _otel_acct_add(lab, _oa_tool, _nm, _bad, at.get("duration_ms"))
                    if ev == "api_request":
                        cur["tokens"] = sum(int(at.get(k) or 0) for k in
                                            ("input_tokens", "cache_read_tokens", "cache_creation_tokens"))
                        cur["model"] = at.get("model") or cur.get("model")
    if len(_otel) > 100:
        with _otel_lock:
            for k in list(_otel)[:50]:
                _otel.pop(k, None)
                _otel_tools.pop(k, None)   # drop the session counter too (the total `_otel_tools_all` remains)
    return n


# state stated by the event — **a harness fact**, not an inference
_OTEL_STATE = {"user_prompt": "think", "api_request": "think", "tool_decision": "tool",
               "tool_result": "think", "assistant_response": "wait", "api_error": "wait"}


def _otel_state(sid, max_age=300):
    """(state, tool, tokens) or None. Old entries are not used (the session may not have telemetry on)."""
    with _otel_lock:
        cur = dict(_otel.get(sid) or {})
        tls = {k: list(v) for k, v in (_otel_tools.get(sid) or {}).items()}
    if not cur or time.time() - (cur.get("at") or 0) > max_age:
        return None
    # ⚠Existing field names and structure stay as is (several UI places use them). Only the three below are **appended**.
    return {"state": _OTEL_STATE.get(cur.get("ev")), "tool": cur.get("tool"), "at": cur.get("at"),
            "tokens": cur.get("tokens"), "ev": cur.get("ev"), "age": int(time.time() - cur["at"]),
            "lastTool": cur.get("lastTool") or "",      # last tool whose result **came back** (differs from `tool`)
            "ok": _otel_ok(cur.get("ok")),              # whether that result succeeded (None if unreadable)
            "tools": tls}                               # this session's tallies {name: [calls, failures]}
