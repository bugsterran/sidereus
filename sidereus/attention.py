"""«Attention» — rank sessions by how much they need the user right now."""
import re
import threading
import time
from sidereus.transcript import iso_epoch
from sidereus.ident import _sid8
from sidereus.cards import cards_read, cards_read_ids
from sidereus import failures as _fl
from sidereus import file_owner as _fo

# ⛔Metadata only: every `why` is built here from tool names, counts and minutes — never task/reply/card text.
# ★Points decided 2026-09-23 (user). No quota-share signal: not actionable per session.
ATT_PTS = {"blocked": 100, "ask": 90, "conflict": 85, "mailidle": 75, "abort": 70, "ctx95": 65, "fail": 60, "wreck": 60,
           "stall": 55, "loop": 50, "toolfail": 45, "ctx85": 25, "done": 20, "bgdone": 15}
ATT_FAIL_CARD_S = 1800      # failure alert card counts for 30 min at most ...
# ... and clears once the same session shows real activity (row ageSec =
#   transcript actAt, noise-free — not poll time) past the failure time + this grace. Covers Mac sleep: no activity
#   while asleep, the first real turn after wake clears it. ⚠Failure time = the event's own `at` when known (a card
#   made on wake for a pre-sleep failure carries the wake time).
ATT_RESUME_GRACE_S = 60
ATT_STALL_S = 1800          # subagent log silent this long while the parent waits
ATT_LOOP_N = 8              # consecutive identical tool calls
ATT_TOOLFAIL_N = 4          # same tool-error signature this many times ...
ATT_TOOLFAIL_S = 600        # ... within 10 min ...
ATT_TOOLFAIL_RECENT_S = 180 # ... and the latest within 3 min (no per-tool success info in _FAIL_EV)
# ★2026-09-23: counting every is_error ranked a healthy busy session first (failures.py grades tool errors `noise`;
#   185/322 were `Exit code 1`). These normal-workflow signatures (failures._tool_sig output) never count.
_TF_BENIGN = ("Exit code", "File does not exist", "Path does not exist", "String to replace not found",
              "Found N matches of the string", "File has not been read yet", "File has been modified since read",
              "File content (", "EISDIR", "Blocked: sleep", "Sibling tool call errored", "Cancelled")
_TF_TOOL = (("Exit code", "Bash"), ("Blocked: sleep", "Bash"), ("File does not exist", "Read"),
            ("File content (", "Read"), ("EISDIR", "Read"), ("String to replace", "Edit"),
            ("Found N matches", "Edit"), ("File has not been read", "Edit"), ("### Error", "MCP"))
_TF_NAME = re.compile(r"^(?:InputValidationError: )?([\w.-]{2,60}) (?:was called|failed due)")
ATT_DONE_S = (15, 7200)     # done & waiting: state "wait" already needs a turn-end marker; the floor only debounces a quick reply-then-type
_FAIL_TITLE = {"flimit": "한도로 멈춤", "fcut": "바깥 원인으로 끊김",
               "fcheck": "원인 확인 필요", "fwreck": "반쯤 고친 파일"}
_TF = {"at": 0.0, "idx": {}}
_TF_LOCK = threading.Lock()
_TF_TTL = 30


def _card_ts(c):
    return iso_epoch(c.get("at"), 0.0)


def _under(cwd, root):
    return bool(cwd and root) and (cwd == root or cwd.startswith(root.rstrip("/") + "/"))


def _tf_tool(sig):
    """Tool name from the error signature class only (never error text)."""
    m = _TF_NAME.match(sig)
    if m:
        return m.group(1)
    return next((t for p, t in _TF_TOOL if sig.startswith(p)), "도구")


def _toolfail_idx(now):
    """cwd -> [(n, tool, first_at)] for non-benign tool-error signatures repeated >= ATT_TOOLFAIL_N times in
    10 min with the latest within 3 min. Read-only snapshot of failures._FAIL_EV (30s TTL).
    ⚠Uses getattr: _FAIL_EV/_FAIL_LOCK live in failures_scan (re-exported by failures); a rename must not break state()."""
    with _TF_LOCK:
        if now - _TF["at"] < _TF_TTL:
            return _TF["idx"]
    ev, lk = getattr(_fl, "_FAIL_EV", None), getattr(_fl, "_FAIL_LOCK", None)
    grp, cut = {}, now - ATT_TOOLFAIL_S
    if isinstance(ev, dict) and lk is not None:
        with lk:
            lists = [list(v[-200:]) for v in ev.values() if v]
        for evs in lists:
            for e in reversed(evs):             # events are appended in time order
                if (e.get("at") or 0) < cut:
                    break
                sg = e.get("sig") or ""
                if e.get("kind") != "tool" or not sg or sg.startswith(_TF_BENIGN):
                    continue
                grp.setdefault((e.get("cwd") or "", sg), []).append(e["at"])
    idx = {}
    for (cw, sg), ats in grp.items():
        if len(ats) >= ATT_TOOLFAIL_N and now - max(ats) <= ATT_TOOLFAIL_RECENT_S:
            idx.setdefault(cw, []).append((len(ats), _tf_tool(sg), min(ats)))
    with _TF_LOCK:
        _TF.update(at=now, idx=idx)
    return idx


def _ev_at(tids):
    """tid -> failure event time from failures._FAIL_EV (read-only; tids with no event are absent)."""
    ev, lk = getattr(_fl, "_FAIL_EV", None), getattr(_fl, "_FAIL_LOCK", None)
    if not tids or not isinstance(ev, dict) or lk is None:
        return {}
    with lk:
        lists = [list(v[-200:]) for v in ev.values() if v]
    out = {}
    for evs in lists:
        for e in evs:
            t = e.get("tid")
            if t in tids and e.get("at"):
                out[t] = min(out.get(t, e["at"]), e["at"])
    return out


def _resumed(r, at, now):
    """The row's last real activity is past `at` + grace (session carried on after the failure)."""
    return bool(at) and now - int(r.get("ageSec") or 0) > at + ATT_RESUME_GRACE_S


_conflicts = _fo.conflicts      # module seam: tests swap it so attention() never scans live transcripts


def _sig(k, why, since, pts=None):
    return {"k": k, "why": why, "pts": ATT_PTS[k] if pts is None else pts, "since": int(since)}


def _owner_of(rows):
    """cwd -> owning row resolver: cwd-scoped evidence (cards, tool failures) goes to the most recently active session of that cwd only."""
    owner = {}
    for r in sorted(rows, key=lambda r: r.get("ageSec") or 0, reverse=True):
        # ⚠Claude rows only: cards and tool failures come from Claude hooks — a fresher Gemini row at the same cwd must not take them
        if r.get("cwd") and r.get("plat") in (None, "", "cc"):
            owner[r["cwd"]] = r
    def own(cwd):
        best = None
        for root, r in owner.items():
            if _under(cwd, root) and (best is None or len(root) > len(best[0])):
                best = (root, r)
        return best[1] if best else None
    return own


def _card_sigs(extra, cards, own, now, read, rid):
    grp = {}
    evat = _ev_at({c.get("tid") for c in cards or [] if (c.get("kind") or "").startswith("f") and c.get("tid")})
    for c in cards or []:
        k, cw = c.get("kind") or "", c.get("cwd") or ""
        r = own(cw)
        if r is None:
            continue
        at = _card_ts(c)
        same = not (c.get("sid") and r.get("sid") and c["sid"] != r["sid"])
        # ★failure family = kinds starting with 'f' (flimit·fcut·fcheck·fwreck·legacy fail)
        if k.startswith("f") and now - at <= ATT_FAIL_CARD_S:
            if same and _resumed(r, min(at, evat.get(c.get("tid"), at)), now):
                continue
            grp.setdefault((id(r), "fail"), []).append((at, _FAIL_TITLE.get(k, "실패 알림")))
        elif k in ("agent", "bgdone") and at and not c.get("old") and not (read and c.get("at", "") <= read):
            if same and _resumed(r, at, now):   # session carried on after the completion: treat as seen
                continue
            ck = "%s|%s|%s" % (c.get("at"), k, c.get("project") or "")
            if ck not in rid:
                grp.setdefault((id(r), "bgdone"), []).append((at, "서브에이전트" if k == "agent" else "백그라운드", ck))
    # one signal per kind: several cards of the same kind count once (+5 is per distinct signal)
    for (rk, k), its in grp.items():
        its.sort()
        if k == "fail":
            why = its[-1][1] + (" 등 %d건" % len(its) if len(its) > 1 else "")
        else:
            labs = sorted({x[1] for x in its})
            why = "%s 완료 %d건 미확인" % ("·".join(labs), len(its))
        sg = _sig(k, why, its[0][0])
        if k == "bgdone":                   # card read keys (at|kind|project, metadata) so the row's «Seen» can POST /api/cards/read
            sg["keys"] = [x[2] for x in its]
        if k == "fail":                     # only card signals expire on a clock: the UI shows the 30-min cap left
            sg["until"] = int(its[-1][0] + ATT_FAIL_CARD_S)
        extra.setdefault(rk, []).append(sg)


def _toolfail_sigs(extra, own, now):
    for cw, reps in _toolfail_idx(now).items():
        r = own(cw)
        if r is None or r.get("state") == "done":
            continue
        n, tool, t1 = max(reps)             # several signatures/subdir cwds under one session: keep the worst
        grp2 = extra.setdefault(id(r), [])
        old = [s for s in grp2 if s["k"] == "toolfail"]
        if old and old[0]["n"] >= n:
            continue
        if old:
            grp2.remove(old[0])
        grp2.append(dict(_sig("toolfail", "같은 오류 %d회 반복 · %s" % (n, tool), t1), n=n))


def _conflict_sigs(extra, rows, now):
    # conflict: unit-set groups (file_owner.conflicts) merged per row of the latest editor -> one signal per row
    byid = {r.get("sid"): r for r in rows if r.get("sid")}
    try:
        cfs = _conflicts(rows, now)
    except Exception:
        cfs = []
    cmg = {}
    for g in cfs:
        r = byid.get(g.get("by"))
        if r is None:
            continue
        m = cmg.setdefault(id(r), {"files": set(), "sids": [], "labs": [], "since": g["since"]})
        m["files"].update(g["files"])
        m["since"] = min(m["since"], g["since"])
        m["sids"] += [s for s in g["sids"] if s not in m["sids"]]
        m["labs"] += [x for x in g.get("labs") or () if x not in m["labs"]]
    for rk, m in cmg.items():
        who = ("세션 " + ", ".join(_sid8(s) for s in m["sids"])) if len(m["sids"]) > 1 else ("서브에이전트 " + ", ".join(m["labs"]))
        extra.setdefault(rk, []).append(_sig("conflict", "충돌 위험 · 파일 %d · %s" % (len(m["files"]), who), m["since"]))


def _collect(rows, cards, now, read, rid):
    """id(row) -> [signal] from cwd-scoped evidence: cards, then tool failures, then conflicts."""
    own = _owner_of(rows)
    extra = {}
    _card_sigs(extra, cards, own, now, read, rid)
    _toolfail_sigs(extra, own, now)
    _conflict_sigs(extra, rows, now)
    for sl in extra.values():
        for s in sl:
            s.pop("n", None)
    return extra


def _row_sigs(r, now):
    """Signals read off the session row itself."""
    st, age = r.get("state") or "", int(r.get("ageSec") or 0)
    t0, live = now - age, st not in ("done", "gone")
    sg = []
    if st == "gone":
        # External CLI killed without SessionEnd: list-only and below every user-set point (it leaves on its own).
        sg.append(_sig("gone", "끊김?" if r.get("goneWhy") == "silent" else "끊김", t0, pts=10))
    if r.get("blocked"):
        # Marker rows carry blockedAt (prompt time): since/ep stay fixed per prompt, so a dismissed row and the OS alert return on a new one.
        ba = r.get("blockedAt")
        if isinstance(ba, int) and ba > 0:
            sg.append(dict(_sig("blocked", r["blocked"], ba), ep=ba))
        else:
            sg.append(_sig("blocked", r["blocked"], t0))
    if st == "ask":
        sg.append(_sig("ask", "질문 대기", t0))
    if st == "abort":
        sg.append(_sig("abort", "중단됨 — 다시 지시 필요", t0))
    win = r.get("win") or 0
    if live and win:
        pct = int((r.get("ctx") or 0) * 100 / win)
        if pct >= 95:
            sg.append(_sig("ctx95", "컨텍스트 %d%% — 곧 자동 압축" % pct, t0))
        elif pct >= 85:
            sg.append(_sig("ctx85", "컨텍스트 %d%%" % pct, t0))
    wat = (getattr(_fl, "_WRECK_AT", None) or {}).get(r.get("cwd") or "", 0)
    if int(r.get("wreck") or 0) > 0 and not _resumed(r, wat, now):
        sg.append(_sig("wreck", "반쯤 고친 파일 %d개" % int(r["wreck"]), t0))
    # parent "waiting" = its own turn is the pending tool or it is idle, and it has not written for 5 min
    idle = max([int(s.get("idle") or 0) for s in (r.get("sub") or []) if isinstance(s, dict)] or [0])
    if live and idle >= ATT_STALL_S and st in ("tool", "wait") and age >= 300:
        sg.append(_sig("stall", "서브에이전트 %d분 무기록 · 부모 대기" % (idle // 60), now - idle))
    rep = r.get("rep") or {}
    if live and int(rep.get("n") or 0) >= ATT_LOOP_N:
        sg.append(_sig("loop", "%s 같은 호출 %d회 반복" % (rep.get("tool") or "도구", int(rep["n"])), t0))
    mi = r.get("mailIdle") or {}   # sidereus/mail_idle.py: counts and age only
    if st == "wait" and int(mi.get("n") or 0) > 0:
        sg.append(_sig("mailidle", "메일 %d통 대기 · 세션 쉼 %d분" % (int(mi["n"]), int(mi.get("age") or 0) // 60),
                       now - int(mi.get("age") or 0)))
    # ⚠A Workflow call returns at launch, so the parent ends its turn (`wait`) while the run goes on — not the human's turn.
    wf_run = any(isinstance(w, dict) and w.get("run") for w in (r.get("wf") or []))
    if st == "wait" and not r.get("sub") and not r.get("bgs") and not wf_run \
            and ATT_DONE_S[0] <= age <= ATT_DONE_S[1]:
        sg.append(_sig("done", ("작업 끝 · 입력 대기 %d분" % (age // 60)) if age >= 60 else ("작업 끝 · 입력 대기 %d초" % age), t0))
    return sg


def _rank(rows, extra, now):
    """Rows with at least one signal, scored and sorted."""
    out = []
    for r in rows:
        sg = _row_sigs(r, now)
        sg.extend(extra.get(id(r), ()))
        if not sg:
            continue
        sg.sort(key=lambda s: (-s["pts"], s["since"]))
        top = sg[0]
        out.append({"sid": r.get("sid") or r.get("id") or "", "cwd": r.get("cwd") or "",
                    "project": r.get("project") or "", "branch": r.get("branch") or "",
                    "score": top["pts"] + 5 * (len(sg) - 1),
                    "why": top["why"] + (" 외 %d" % (len(sg) - 1) if len(sg) > 1 else ""),
                    "since": top["since"], "sigs": sg})
    out.sort(key=lambda x: (-x["score"], x["since"]))
    return out


def attention(sessions, cards, quota=None, read=None, read_ids=None):
    """-> {at, rows:[{sid, cwd, project, branch, score, why, since, sigs:[{k, why, pts, since, until?, keys?}]}]}.
    score = top signal pts + 5 per extra signal; ties -> oldest since. k='done' is list-only (no badge) in the UI."""
    now = time.time()
    rows = [r for r in (sessions or []) if isinstance(r, dict)]
    read = cards_read() if read is None else read
    rid = set(cards_read_ids() if read_ids is None else read_ids)
    return {"at": int(now), "rows": _rank(rows, _collect(rows, cards, now, read, rid), now)}
