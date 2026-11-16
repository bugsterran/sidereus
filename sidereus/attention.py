"""«Attention» — rank sessions by how much they need the user right now."""
import re
import threading
import time
from sidereus.transcript import iso_epoch
from sidereus.ident import _sid8
from sidereus.cards import cards_read, cards_read_ids, wreck_of
from sidereus import failures as _fl
from sidereus import file_owner as _fo
from sidereus.bgtasks import BG_IDLE_S, BG_LONG_S

# ⛔Metadata only: every `why` is built here from tool names, counts and minutes — never task/reply/card text.
# Wire contract: each signal carries `v` (numbers, tool names, sid8, agent types) and an English `why` built from
#   k + v by _why() — the MCP text as-is; the page renders its own (translated) label from k + v.
# ★Points decided 2026-09-23. No quota-share ranking; `credit` = a session that spends Anthropic plan/credits outside
#   Claude Code (pi OAuth row `credit`), shown while it is spending — actionable per session.
ATT_PTS = {"blocked": 100, "ask": 90, "conflict": 85, "credit": 80, "mailidle": 75, "abort": 70, "ctx95": 65, "fail": 60,
           "wreck": 60, "stall": 55, "loop": 50, "toolfail": 45, "bgidle": 30, "bglong": 30, "ctx85": 25, "done": 20,
           "bgdone": 15}
ATT_CREDIT_S = 300          # «Spending credits» while the newest anthropic/ entry is this recent
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
# Failure card kinds -> English title (page label source); an unknown f-kind folds into "fail".
# ⚠Tie-break ranks that keep the pre-`v` picks: cards with the same `at` sorted by their former (Korean) title codepoints,
#   and an unknown tool (None) outranks every named tool on an equal count, as its former fallback word sorted above ASCII names.
_FAIL_ORD = ("fcut", "fwreck", "fail", "fcheck", "flimit")
_SRC_ORD = ("bg", "agent")
_FAIL_TITLE = {"flimit": "Stopped by limit", "fcut": "Cut by external cause",
               "fcheck": "Cause needs a look", "fwreck": "Half-edited files", "fail": "Failure alert"}
_TF = {"at": 0.0, "idx": {}}
_TF_LOCK = threading.Lock()
_TF_TTL = 30


def _card_ts(c):
    return iso_epoch(c.get("at"), 0.0)


def _under(cwd, root):
    return bool(cwd and root) and (cwd == root or cwd.startswith(root.rstrip("/") + "/"))


def _tf_tool(sig):
    """Tool name from the error signature class only (never error text); None = unknown tool."""
    m = _TF_NAME.match(sig)
    if m:
        return m.group(1)
    return next((t for p, t in _TF_TOOL if sig.startswith(p)), None)


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


def _human_after(r, t):
    """The person responded in this session after `t` (typed prompt, `!` command, picker answer).
    ⚠humanAt 0/missing is unknown, never «replied»: an unanswered question must not drop."""
    ha = r.get("humanAt")
    return isinstance(ha, int) and not isinstance(ha, bool) and ha > 0 and ha > t


_conflicts = _fo.conflicts      # module seam: tests swap it so attention() never scans live transcripts


def _tool_tail(tool):
    return " · " + tool if tool else ""


def _why(k, v):
    """English `why` of one signal from its k + v (also the MCP text, agent_brief passes it through)."""
    if k == "gone":
        return "Disconnected?" if v["q"] else "Disconnected"
    if k == "ask":
        return "Asked a question" + (" · kept working since" if v["kept"] else "")
    if k == "abort":
        return "Interrupted — needs a new instruction"
    if k == "ctx95":
        return "Context %d%% — auto-compact soon" % v["pct"]
    if k == "ctx85":
        return "Context %d%%" % v["pct"]
    if k == "wreck":
        return "Leftover edits in %d files" % v["n"]
    if k == "stall":
        return "Subagent silent %d min · parent waiting" % v["m"]
    if k == "loop":
        return "Same call repeated %d×" % v["n"] + _tool_tail(v["tool"])
    if k == "toolfail":
        return "Same error repeated %d×" % v["n"] + _tool_tail(v["tool"])
    if k == "fail":
        return "Failure alert" + (" (%d)" % v["n"] if v["n"] > 1 else "")
    if k == "mailidle":
        return "Mail waiting · session idle · %d message(s) · %d min" % (v["n"], v["m"])
    if k == "bglong":
        return "Long background %d · longest %d min" % (v["n"], v["m"]) + (" · %d idle" % v["idle"] if v["idle"] > 0 else "")
    if k == "bgidle":
        return "%d background shell(s) · %d idle · longest %d min" % (v["n"], v["idle"], v["m"])
    if k == "done":   # ⚠seconds under 60 s, else whole minutes
        return "Done · waiting for input " + ("%d min" % (v["s"] // 60) if v["s"] >= 60 else "%d s" % v["s"])
    if k == "bgdone":
        return "%d agent completion(s) unread" % v["n"]
    if k == "credit":
        return "Spending credits · %ds ago" % v["s"]
    if k == "conflict":
        who = ("sessions " + ", ".join(v["sids"])) if "sids" in v \
            else ("subagents " + ", ".join("main" if x is None else x for x in v["labs"]))
        return "Conflict risk · %d file(s) · %s" % (v["files"], who)
    return k


def _sig(k, v, since, pts=None, why=None):
    """One signal; `v` None (blocked) = no v, `why` given as-is."""
    s = {"k": k, "why": _why(k, v) if why is None else why, "pts": ATT_PTS[k] if pts is None else pts, "since": int(since)}
    if v is not None:
        s["v"] = v
    return s


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


def _ask_open(r, c, at):
    """An «ask» card still unanswered: same session, row live and not already `ask`, no human prompt after the card.
    ⚠humanAt missing (old parse cache, external CLI row) is unknown: no card signal rather than a stale one.
    ⚠humanAt 0 = no human line found (parse.py looks past the tail): hold. tailAt is not evidence of a reply —
    notifications and hand-backs alone can push the question out of the tail."""
    ha = r.get("humanAt")
    return bool(c.get("sid")) and c.get("sid") == r.get("sid") and (r.get("state") or "") not in ("ask", "done", "gone") \
        and isinstance(ha, int) and not isinstance(ha, bool) and ha < at


def _card_sigs(extra, cards, own, now, read, rid, by_sid=None):
    grp = {}
    evat = _ev_at({c.get("tid") for c in cards or [] if (c.get("kind") or "").startswith("f") and c.get("tid")})
    for c in cards or []:
        k, cw = c.get("kind") or "", c.get("cwd") or ""
        # An «ask» card belongs to its own session, not to the newest row of the cwd.
        r = (by_sid or {}).get(c.get("sid") or "") if k == "ask" else own(cw)
        # «Half-edited files» goes to its owner row like `cards.wreck_of`; an unlisted owner falls back to own(cw)
        if k == "fwreck":
            r = (by_sid or {}).get(c.get("sid") or "") or r
        if r is None:
            continue
        at = _card_ts(c)
        same = not (c.get("sid") and r.get("sid") and c["sid"] != r["sid"])
        # ★failure family = kinds starting with 'f' (flimit·fcut·fcheck·fwreck·legacy fail)
        if k.startswith("f") and now - at <= ATT_FAIL_CARD_S:
            if same and _resumed(r, min(at, evat.get(c.get("tid"), at)), now):
                continue
            grp.setdefault((id(r), "fail"), []).append((at, k if k in _FAIL_TITLE else "fail"))
        elif k in ("agent", "bgdone") and at and not c.get("old") and not (read and c.get("at", "") <= read):
            # session carried on after the completion, or the person typed there (inside the grace): treat as seen
            if same and (_resumed(r, at, now) or _human_after(r, at)):
                continue
            ck = "%s|%s|%s" % (c.get("at"), k, c.get("project") or "")
            if ck not in rid:
                grp.setdefault((id(r), "bgdone"), []).append((at, "agent" if k == "agent" else "bg", ck))
        elif k == "ask" and at and not c.get("old") and not (read and c.get("at", "") <= read) and _ask_open(r, c, at):
            # ⚠Hand-backs and task notifications wake the session and flip the row off `ask` while the question is unanswered.
            ck = "%s|%s|%s" % (c.get("at"), k, c.get("project") or "")
            if ck not in rid:
                # kept: the question is no longer the last thing in the terminal, so the label says it scrolled up
                grp.setdefault((id(r), "ask"), []).append((at, True, ck))
    # one signal per kind: several cards of the same kind count once (+5 is per distinct signal)
    for (rk, k), its in grp.items():
        its.sort(key=lambda x: (x[0], _FAIL_ORD.index(x[1]) if k == "fail" else _SRC_ORD.index(x[1]) if k == "bgdone" else 0)
                 + tuple(x[2:]))
        if k == "fail":
            v = {"kind": its[-1][1], "n": len(its)}
        elif k == "ask":
            v = {"kept": True}
        else:
            src = {x[1] for x in its}
            v = {"n": len(its), "src": [x for x in ("bg", "agent") if x in src]}
        sg = _sig(k, v, its[0][0])
        if k in ("bgdone", "ask"):          # card read keys (at|kind|project, metadata) so the row's «Seen» can POST /api/cards/read
            sg["keys"] = [x[2] for x in its]
        if k == "fail":                     # only card signals expire on a clock: the UI shows the 30-min cap left
            sg["until"] = int(its[-1][0] + ATT_FAIL_CARD_S)
        extra.setdefault(rk, []).append(sg)


def _toolfail_sigs(extra, own, now):
    for cw, reps in _toolfail_idx(now).items():
        r = own(cw)
        if r is None or r.get("state") == "done":
            continue
        # several signatures/subdir cwds under one session: keep the worst (⚠never compare None with str)
        n, tool, t1 = max(reps, key=lambda x: (x[0], (1, "") if x[1] is None else (0, x[1]), x[2]))
        grp2 = extra.setdefault(id(r), [])
        old = [s for s in grp2 if s["k"] == "toolfail"]
        if old and old[0]["v"]["n"] >= n:
            continue
        if old:
            grp2.remove(old[0])
        grp2.append(_sig("toolfail", {"n": n, "tool": tool}, t1))


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
        # several sessions -> sid8s; one session -> its unit labels (None = the main unit)
        who = {"sids": [_sid8(s) for s in m["sids"]]} if len(m["sids"]) > 1 else {"labs": list(m["labs"])}
        extra.setdefault(rk, []).append(_sig("conflict", dict({"files": len(m["files"])}, **who), m["since"]))


def _collect(rows, cards, now, read, rid):
    """id(row) -> [signal] from cwd-scoped evidence: cards, then tool failures, then conflicts."""
    own = _owner_of(rows)
    extra = {}
    _card_sigs(extra, cards, own, now, read, rid, {r["sid"]: r for r in rows if r.get("sid")})
    _toolfail_sigs(extra, own, now)
    _conflict_sigs(extra, rows, now)
    return extra


def _row_sigs(r, now, listed=None):
    """Signals read off the session row itself."""
    st, age = r.get("state") or "", int(r.get("ageSec") or 0)
    t0, live = now - age, st not in ("done", "gone")
    sg = []
    if st == "gone":
        # External CLI killed without SessionEnd: list-only and below every user-set point (it leaves on its own).
        sg.append(_sig("gone", {"q": r.get("goneWhy") == "silent"}, t0, pts=10))
    if r.get("blocked"):
        # Marker rows carry blockedAt (prompt time): since/ep stay fixed per prompt, so a dismissed row and the OS alert return on a new one.
        ba = r.get("blockedAt")
        if isinstance(ba, int) and ba > 0:
            sg.append(dict(_sig("blocked", None, ba, why=r["blocked"]), ep=ba))
        else:
            sg.append(_sig("blocked", None, t0, why=r["blocked"]))
    if st == "ask":
        sg.append(_sig("ask", {"kept": False}, t0))
    if st == "abort":
        sg.append(_sig("abort", {}, t0))
    cr = r.get("credit")
    la = int(cr.get("lastAt") or 0) if isinstance(cr, dict) else 0
    if live and la > 0 and now - la <= ATT_CREDIT_S:
        sg.append(_sig("credit", {"s": max(0, int(now - la))}, la))   # s = seconds since the last spend
    win = r.get("win") or 0
    if live and win:
        pct = int((r.get("ctx") or 0) * 100 / win)
        if pct >= 95:
            sg.append(_sig("ctx95", {"pct": pct}, t0))
        elif pct >= 85:
            sg.append(_sig("ctx85", {"pct": pct}, t0))
    # ⚠Owner split first: a cwd-wide count raised `wreck` on idle non-owner rows that never resume to clear it.
    w = wreck_of(r.get("sid") or "", r.get("cwd") or "", listed or set())
    wn, wat = (int(r.get("wreck") or 0), (getattr(_fl, "_WRECK_AT", None) or {}).get(r.get("cwd") or "", 0)) \
        if w is None else w
    if int(r.get("wreck") or 0) > 0 and wn > 0 and not _resumed(r, wat, now):
        sg.append(_sig("wreck", {"n": wn}, t0))
    # parent "waiting" = its own turn is the pending tool or it is idle, and it has not written for 5 min
    subs = [s for s in (r.get("sub") or []) if isinstance(s, dict)]
    idle = max([int(s.get("idle") or 0) for s in subs] or [0])
    if live and idle >= ATT_STALL_S and st in ("tool", "wait") and age >= 300:
        # ⚠absolute idle start: rows come from a stale snapshot, so `now - idle` drifts per poll and breaks the ack key
        ats = [int(s["idleAt"]) for s in subs if int(s.get("idle") or 0) >= ATT_STALL_S and s.get("idleAt")]
        sg.append(_sig("stall", {"m": idle // 60}, min(ats) if ats else now - idle))
    rep = r.get("rep") or {}
    if live and int(rep.get("n") or 0) >= ATT_LOOP_N:
        tl = rep.get("tool")   # None = unknown tool
        sg.append(_sig("loop", {"n": int(rep["n"]), "tool": str(tl) if tl else None}, t0))
    mi = r.get("mailIdle") or {}   # sidereus/mail_idle.py: counts and age only
    if st == "wait" and int(mi.get("n") or 0) > 0:
        sg.append(_sig("mailidle", {"n": int(mi["n"]), "m": int(mi.get("age") or 0) // 60}, now - int(mi.get("age") or 0)))
    bi = r.get("bgIdle") or {}   # open background shells whose output file is quiet (mtime only, never content)
    bl = r.get("bgLong") or {}   # open background shells launched > BG_LONG_S ago (launch time only)
    bil = int(bi.get("idle") or 0) if isinstance(bi, dict) else 0
    bgl = False
    if live and isinstance(bl, dict) and int(bl.get("long") or 0) > 0:
        # One bg signal per session: a long shell absorbs the idle count so the row is not listed twice.
        lsince = int(bl.get("at") or 0) or now - int(bl.get("max") or 0)
        if not _human_after(r, int(bl.get("last") or lsince) + BG_LONG_S):
            bgl = True
            sg.append(_sig("bglong", {"n": int(bl["long"]), "m": int(bl.get("max") or 0) // 60, "idle": bil}, lsince))
    # ⚠Only a shown bglong absorbs bgidle: one cleared by input must not hide a shell that went idle later.
    if live and not bgl and isinstance(bi, dict) and bil > 0:
        mx = int(bi.get("max") or 0)
        bsince = int(bi.get("at") or 0) or now - mx   # ⚠absolute `at`: `max` is from a stale snapshot
        # ⚠Compare with the newest idle onset (mtime + BG_IDLE_S), not `at`: a prompt before a shell went idle must not hide it.
        if not _human_after(r, int(bi.get("last") or bsince) + BG_IDLE_S):
            sg.append(_sig("bgidle", {"n": int(bi.get("n") or 0), "idle": int(bi["idle"]), "m": mx // 60}, bsince))
    # ⚠A Workflow call returns at launch, so the parent ends its turn (`wait`) while the run goes on — not the human's turn.
    wf_run = any(isinstance(w, dict) and w.get("run") for w in (r.get("wf") or []))
    if st == "wait" and not r.get("sub") and not r.get("bgs") and not wf_run \
            and ATT_DONE_S[0] <= age <= ATT_DONE_S[1] and not _human_after(r, t0):   # ⚠a `!` line is not activity: t0 stays old
        sg.append(_sig("done", {"s": age}, t0))
    return sg


def _rank(rows, extra, now):
    """Rows with at least one signal, scored and sorted."""
    out = []
    listed = {r.get("sid") for r in rows if r.get("sid")}   # wreck owner lookup (cards.wreck_of)
    for r in rows:
        sg = _row_sigs(r, now, listed)
        sg.extend(extra.get(id(r), ()))
        if not sg:
            continue
        sg.sort(key=lambda s: (-s["pts"], s["since"]))
        top = sg[0]
        out.append({"sid": r.get("sid") or r.get("id") or "", "cwd": r.get("cwd") or "",
                    "project": r.get("project") or "", "branch": r.get("branch") or "",
                    "score": top["pts"] + 5 * (len(sg) - 1),
                    "why": top["why"] + (" +%d more" % (len(sg) - 1) if len(sg) > 1 else ""),
                    "since": top["since"], "sigs": sg})
    out.sort(key=lambda x: (-x["score"], x["since"]))
    return out


def attention(sessions, cards, quota=None, read=None, read_ids=None):
    """-> {at, rows:[{sid, cwd, project, branch, score, why, since, sigs:[{k, why, pts, since, v?, until?, keys?, ep?}]}]}.
    score = top signal pts + 5 per extra signal; ties -> oldest since. k='done' is list-only (no badge) in the UI."""
    now = time.time()
    rows = [r for r in (sessions or []) if isinstance(r, dict)]
    read = cards_read() if read is None else read
    rid = set(cards_read_ids() if read_ids is None else read_ids)
    return {"at": int(now), "rows": _rank(rows, _collect(rows, cards, now, read, rid), now)}
