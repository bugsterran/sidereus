"""Session rows: sessions() and its snapshot cache."""
import json
import os
import re
import threading
import time
from sidereus.config import DATA_DIR
from sidereus import claude_roots
from sidereus.warn import warn_once
from sidereus.transcript import _model_label, _tail_lines
from sidereus.ident import _proj_name, _proj_root, _sid8, mbox_of
from sidereus.live import (_MBOX_LAB_RE, _blocked, _ctx_window, _model_win, _parse_cache,
    _parse_lock, live_cwds, mailbox_watches, sid_alive)
from sidereus.gitinfo import _git_state, _wt_of, session_repos
from sidereus.agents import WF_HIST_N, WF_HIST_S, WF_KEEP_S, _DESC_TOOLS, _bg_show, _subs_mt, _subs_newer, plm_of, team_info, wf_public, wf_runs
from sidereus.usage_index import _uidx, _uidx_lock
from sidereus.cards import _WRECK_BY_CWD, _note_lock, _recent_transcripts
from sidereus.usage import _sid_proj
from sidereus.otel import OTEL_TRUST_S, _otel_state
from sidereus.projcost import _projcost_of
from sidereus.bgtasks import _bg_open
from sidereus.notes import _note_bg_done, _note_ctx, _note_transition, _sess_state
from sidereus.parse import _parse_transcript
from sidereus.ext import ext_children, ext_rollout_rows, ext_rows
from sidereus import pl_runs, prefs   # module access: tests stub pl_runs._ag_by_name
from sidereus.perm_marks import perm_wait
from sidereus.term import term_attach


# «Pipeline recording off» (row `plOff`): Apply off for the cwd yet [pl:] tags in its Agent descriptions.
PL_OFF_S = 6 * 3600              # a tagged agent this recent still counts (= pl_runs.PLR_KEEP_S)
PL_APPLY_TTL_S = 5               # config `pipeline_apply` re-read at most this often
_PL_TAG = re.compile(r"\[pl:[a-z0-9-]{1,40}/[^\]]{1,80}\]")
_PL_APPLY = {"at": 0.0, "v": None}


def _pl_off(cwd, sess_dir, sub, targ, now):
    """True when «Apply» is off for cwd (hooks/pl_flow.py _apply_off: own override, else global; git root also checked)
    and the session tags agents `[pl:…]` (live sub label · Agent call in flight · subagent meta newer than PL_OFF_S).
    ⚠Boolean only — no label or description leaves here (rule 1)."""
    if not cwd:
        return False
    if now - _PL_APPLY["at"] > PL_APPLY_TTL_S or _PL_APPLY["v"] is None:
        _PL_APPLY.update(at=now, v=prefs.saved("pipeline_apply"))
    v = _PL_APPLY["v"] or {}
    projs = v.get("projects") or {}
    if (projs.get(cwd) or projs.get(_proj_root(cwd)) or v.get("mode")) != "off":
        return False
    if isinstance(targ, str) and _PL_TAG.search(targ):
        return True
    if any(isinstance(x, dict) and isinstance(x.get("lab"), str) and _PL_TAG.search(x["lab"]) for x in sub or ()):
        return True
    try:
        ags = pl_runs._ag_by_name(sess_dir, now) if sess_dir else {}
    except Exception:
        return False
    return any(isinstance(a, dict) and (a.get("t1") or 0) >= now - PL_OFF_S for xs in ags.values() for a in xs)


WAKE_STALE_S = 15.0   # hooks/mailbox_wake.py STALE_S: its waiter touches the lock every 2 s


def _wake_rows(fp, now):
    """Async Stop-hook waiter (`hooks/mailbox_wake.py`) holding `.wake/<sid>.lock` -> one `proc` watch row.
    ⚠Liveness is the lock mtime only — never os.kill on the pid inside (it terminates the process on Windows).
    No `min`: the waiter is restarted at every turn end, so there is no meaningful uptime."""
    sid = os.path.basename(fp or "")[:-6] if (fp or "").endswith(".jsonl") else ""
    if not sid or not all(c.isalnum() or c in "-_" for c in sid):
        return []
    try:
        mt = os.path.getmtime(os.path.join(DATA_DIR, ".wake", sid[:64] + ".lock"))
    except OSError:
        return []           # no lock = no waiter (the normal case)
    return [{"lab": "Mailbox watch", "src": "proc"}] if now - mt < WAKE_STALE_S else []


def _mon_rows(fp, beats, now, dead):
    """The screen's **watcher** rows. Merges two sources and tags each item with `src`.

    ★`proc` = measured from processes (source of truth · rationale is the 70~73-hour measurement in the `mailbox_watches()` comment above).
      The number is **real uptime**, so `for N min` is correct, and long running is normal so no color is applied.
    ★`beat` = the old heartbeat-based source. **Only mailbox watchers are dropped** — processes are their source of truth.
      Other harness Monitors (other purposes) keep current behavior (no expiry · label push-out retained).
      No such item exists right now, but if one does it must be shown — this file's principle of
      not declaring death from silence stays in place there.
    ★If lookups keep failing (None), **fall back to the heartbeat list** — saying what exists does not is worse."""
    if dead:
        return []
    w = mailbox_watches()
    if w is None:
        rows = _bg_show(beats, now, dead)
        for r in rows:
            r["src"] = "beat"
        return _wake_rows(fp, now) + rows
    out = _wake_rows(fp, now)
    for it in (w.get(fp) or []):
        out.append({"lab": it[0], "min": int((now - it[1]) / 60), "src": "proc"})
    keep = [it for it in (beats or []) if not _MBOX_LAB_RE.search(it[0] or "")]
    for r in _bg_show(keep, now, dead):
        r["src"] = "beat"
        out.append(r)
    return out


def _bg_age(items, now):
    # ★Item lengths differ — subagents have 4 [label, time, current task, depth], the rest 2.
    #   Tuple unpacking raises ValueError on the 4-item ones, and then **the whole session list goes blank**
    #   (measured 2026-08-27: sessions vanished from the screen entirely). Read by index so length does not matter.
    return int(max([(now - it[1]) / 60 for it in (items or [])], default=0))


_CONT_KEY = '"continuedInSessionId"'
_CONV_TYPES = ("user", "assistant")


def _continued(fp):
    """Successor sid if the transcript's last conversation record is a continuation, else "".

    ★2026-09-24 (f3f9583a): a fork leaves `continued-in` {continuedInSessionId} at the tail (only metadata
      after it). A plain `claude`/`claude -c` terminal pid has no sid in argv, so it keeps a path slot and the
      old transcript showed as live next to its successor. ⚠A user/assistant line after it = resumed, not continued."""
    for line in reversed(_tail_lines(fp, nbytes=16384, limit=40)):
        if _CONT_KEY not in line and '"user"' not in line and '"assistant"' not in line:
            continue                  # cheap pre-filter before json
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("continuedInSessionId"):
            return str(d["continuedInSessionId"])
        if d.get("type") in _CONV_TYPES:
            return ""
    return ""


def _dead(p, live):
    """Ended session — no process, so nothing is running (only old notifications linger)."""
    return _sess_state(p.get("cwd"), p.get("shape"), live, sid=p.get("sid")) == "done"


def _row_state(mt, now, live, p, stale):
    """(state, otel event or None, gotPrompt seconds, dead) — transcript decision merged with OTel."""
    # ★For sessions sending telemetry, **that is the source of truth** (harness facts, not inference).
    #   But (a) if there is no process (done) that wins (b) `Awaiting answer` (ask) is more specific than events, so it is kept
    #     (it was caught from AskUserQuestion·ExitPlanMode in the transcript; events do not make that distinction).
    dead = stale or _dead(p, live)
    st0 = "done" if stale else _sess_state(p.get("cwd"), p.get("shape"), live, p.get("ask"),
                                           p.get("abort"), p.get("err"), sid=p.get("sid"),
                                           ask_tool=bool(p.get("askTool")))
    o = None if stale else _otel_state(p.get("sid"))
    # ★**Use the newer evidence.** Events used to stay valid for 15 min, so a 4-min-old `user_prompt` overrode a 1-min-old transcript
    #   (assistant response = input wait) and froze it as `Thinking` (measured 2026-08-21).
    #   A session may stop sending telemetry (restart·export failure), so **compare ages** and use the winner.
    # ★But **newer is not always right** (measured 2026-09-03, an idle session showed as
    #   thinking): a bot session's transcript ended with `turn_duration` and got no line for 26 min,
    #   yet a single 4-min-old `user_prompt` event overrode it into `Thinking`.
    #   A truly working session **writes lines** — 26 min of silence is not what working looks like.
    #   ⇒ OTel's 'working' (tool·think) is trusted **only when the transcript moved recently**.
    #     Otherwise use the transcript decision and **pass along only the fact that a prompt was received**
    #     (do not say it is dead — show only the time; the person judges).
    got = 0
    # ★OTel's 'wait' **does not win while the transcript holds a pending tool**
    #   (2026-09-04, this work showed as input-wait a third time).
    #   `assistant_response` means "the response ended" and maps to 'wait', but if that response **ended with a tool
    #   call**, next is not the human's turn but the tool running. `tool_decision` only arrives when the tool actually
    #   starts, leaving a gap, and that gap showed as input wait.
    #   Measured (c3d4e5f6 · 2026-09-04 07:34): ev=assistant_response ago=87s → state=wait, while
    #     the transcript at the same time had shape=tool (unanswered tool_use), mt age 70s — Bash was actually running.
    #     5s later ev=tool_decision arrived and it recovered to state=tool.
    #   ⇒ An unanswered tool_use is **a structural fact**, not a timing guess. The transcript wins.
    #   ⚠An exception with the same intent already existed for `ask` (so 'wait' cannot override question wait) — widened for the same reason.
    # ★OTel's `'wait'` **overrides nothing** (2026-09-04, missed again — git push running
    #   20 min showed as input wait). `assistant_response` maps to 'wait', but that event only states **the previous
    #   turn ended**; it says nothing about what is happening now. While a tool runs after it or
    #   the model generates again no new event arrives (api_request comes at the end), so a stale
    #   `assistant_response` froze the screen at 'human's turn' for minutes to tens of minutes.
    #   Measured 08:05:18 bot-A: shape=result (last is a tool result = model's turn to answer), yet
    #     otel=assistant_response (279s earlier) made state=wait.
    #   ⇒ 'Who has the ball' the transcript knows structurally (did a tool call go unanswered · is a tool result
    #     last · did it end with an assistant sentence). All OTel can add is **working**
    #     (tool·think), and only that is accepted. 'wait' either overlaps what the transcript knows or is wrong.
    #   ⚠Previously only `st0 in ("ask","tool")` was blocked, but the same reason applied to 'think' (shape=result) —
    #     missed twice by adding exceptions one at a time, so the rule is inverted.
    # ★2026-09-24: the `api_request` that carried a pending AskUserQuestion maps to 'think' and overrode `ask`
    #   (repo-S showed `Thinking` for 90s while waiting on the user). The transcript's `ask` wins.
    # ⚠A pending tool_use is structural; every OTel `think` belongs to the previous call (tool_result) or arrives at
    #   response end (api_request), so it says nothing about the pending tool. OTel `tool` (tool_decision) still applies.
    #   `api_request` also says nothing about an ended turn, so it must not turn `wait` into `think`.
    if (o and o.get("state") and o["state"] != "wait" and st0 not in ("done", "ask")
            and not (o["state"] == "think" and st0 == "tool")
            and not (o.get("ev") == "api_request" and st0 == "wait")
            and (o.get("at") or 0) >= mt - 5):      # only when the event is as new as the transcript
        # ★Distrust **only when the evidence is a real prompt** (2026-09-04, long-running work still misdetected).
        #   The original bug (2026-09-03) was a single `user_prompt` overriding a transcript dead for 26 min —
        #   receiving a prompt and writing not a single line is not what working looks like. That is what `gotPrompt` means and
        #   the UI text is "Prompt received".
        #   But event kinds were not distinguished, so **long-running work** all got caught here:
        #     · a 7-min response generation — `api_request` carries output_tokens·cost and arrives **at the end**, so
        #       there is no new event during generation. The last event is the previous turn's `tool_result`.
        #     · Bash running over 5 min — writes one line at start and the transcript does not move until it ends.
        #   In both cases `now - mt > 300`, so got was set and the screen said **"Prompt received · no record for N min"**
        #   even though no prompt had been received (the last event was tool_result).
        #   ⇒ Distrust only on `user_prompt`. Otherwise use the OTel state as-is —
        #     if quiet for long the screen says `Thinking for N min` **with the time attached**, so death is not hidden.
        # ★The distrust criterion is **the real last activity** (actAt), **not file mtime**
        #   (measured 2026-09-08 — the same row showed `Thinking` with age `42 min ago`,
        #    the two sources contradicting each other).
        #   Slash commands (`/mcp`·`/usage-credits`) and the CLI's `!command` write noise `user` lines to the transcript
        #   and **bump the file mtime to now** → `now - mt` is under a minute, disabling this guard entirely,
        #   and the `user_prompt` event those commands emit overrides the state with `Thinking`.
        #   Measured: repo-C-api (sid d4e5f6a7) idle 42 min · repo-C-proxy (sid e5f6a7b8) idle 15 min, yet
        #     a single `/mcp` pinned state=think · gotPrompt=0 (= proof the guard did not fire).
        #   ⇒ Noise `user` lines are already excluded from `actAt` by the first fix (_noise_user) — use that.
        #     A real prompt writes a real `user` line at that moment so actAt≈now, the guard does not fire, and OTel's
        #     `Thinking` is adopted as-is (= the same correct behavior as now). Noise cannot push actAt, so it gets caught.
        #     i.e. this one line **separates real prompts from noise.**
        #   ⚠**Leave** the freshness gate above (`o.at >= mt - 5`) and the discard condition in the `else` below **as-is**. When noise
        #     pushes mt, legitimate events get discarded as stale (opposite direction), but the result falls back to the transcript
        #     decision, which is safe. Changing those to act would let events up to 5 min stale **override again** a transcript
        #     silent for long (the exact shape of 2026-09-03), reviving the symptom being fixed now.
        act = int(p.get("actAt") or 0) or mt        # without actAt, fall back to the previous behavior (mt)
        if o.get("ev") == "user_prompt" and (now - act) > OTEL_TRUST_S:
            got = int(now - (o.get("at") or now))   # seconds since the prompt was received
        else:
            st0 = o["state"]
    else:
        o = None if (o and (o.get("at") or 0) < mt - 5) else o
    return st0, o, got, dead


def _wf_tok(fp):
    """Tokens of one agent transcript from the usage index (refreshed by its own loop; up to ~30 s behind)."""
    with _uidx_lock:
        h = (_uidx["files"].get(fp) or {}).get("h") or {}
        return sum(int(v[0]) + int(v[1]) + int(v[2]) + int(v[3])
                   for mm in h.values() if isinstance(mm, dict) for v in mm.values())


def _wf_sets(fp, now, dead):
    """(wf, wfh): `wf` = running runs + ones finished within WF_KEEP_S (tree, «Running», attention, saver read it);
    `wfh` = older finished runs within WF_HIST_S, newest first, at most WF_HIST_N, never `run` (pipeline-tab Workflow view only).
    ⚠Metadata only — labels/phases/counts/times/tokens; journal result text never leaves agents.wf_runs."""
    sd = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
    if not os.path.isdir(os.path.join(sd, "subagents", "workflows")):
        return [], []
    try:
        runs = wf_runs(sd, now, tokf=_wf_tok, since=now - WF_HIST_S)
    except Exception as e:
        warn_once("wfrows", "Could not read workflow runs ({err})", vars={"err": type(e).__name__}, soft=True)
        return [], []
    live = [] if dead else [r for r in runs if r["run"] or now - r["end"] < WF_KEEP_S]
    ids = set(r["id"] for r in live)
    # ⚠A dead session's run can still look `run` (fresh mtime) — history forces it done so no live dot is drawn.
    hist = sorted((dict(r, run=False) for r in runs if r["id"] not in ids and r["name"] != "pipeline"),
                  key=lambda r: -r["end"])[:WF_HIST_N]
    return wf_public(live), wf_public(hist)


def _team_row(fp):
    """Agent-team node when this session leads one (agents.team_info; metadata only)."""
    try:
        return team_info(fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp)
    except Exception as e:
        warn_once("teamrow", "Could not read agent-team files ({err})", vars={"err": type(e).__name__}, soft=True)
        return None


def _row_children(fp, p, now, dead, act="run"):
    """sub·bgs·mon·runmin (+ wf, team) — what is running under the session right now."""
    # ⚠The demo builder (sidereus/demo.py) mirrors this key set, `wf` included (tests/test_demo_data.py).
    #   `team` is added only when the session leads a team, so rows without one keep the mirrored set.
    team = None if dead else _team_row(fp)
    plm = None if dead else plm_of(p.get("sid") or "", now)   # main agent's [pl:] stage (agents.plm_of); added only when live
    sub = _bg_show(p.get("sub"), now, dead)
    plrun = []
    try:   # pipeline run model (pl_runs.pl_model); added only when present
        plrun = pl_runs.pl_model(p.get("sid") or "", fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp, sub, plm, now, act,
                         _bg_show(p.get("sub"), now, False) if dead else ())
    except Exception as e:
        warn_once("plmodel", "Could not build the pipeline run model ({err})",
                  vars={"err": type(e).__name__}, soft=True)
    wf, wfh = _wf_sets(fp, now, dead)
    try:   # added only when true (demo-mirrored key set)
        ploff = _pl_off(p.get("cwd") or "", fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp, sub,
                        p.get("targ") if p.get("tool") in _DESC_TOOLS else "", now)
    except Exception:
        ploff = False
    # `wfh` is added only when present, so rows without history keep the demo-mirrored key set.
    return dict({"wf": wf}, **({"wfh": wfh} if wfh else {}), **({"team": team} if team else {}), **({"plm": plm} if plm else {}),
                **({"plrun": plrun} if plrun else {}), **({"plOff": True} if ploff else {}), **{
        # ★Ended sessions show nothing running — no process, so no tasks either (only old notifications linger).
        "sub": sub,   # subagents — elapsed counted **now** (not frozen in the cache)
        "bgs": _bg_show(p.get("bgs"), now, dead),   # background commands
        # ★mon in the same shape as sub·bgs — previously `[label, time]` pairs went out as-is and broke on screen
        #   (it only went unnoticed because no session had a running watcher).
        "mon": _mon_rows(fp, p.get("mon"), now, dead),      # persistent watchers — processes are the source of truth for mailbox watchers
        "runmin": {} if dead else {"sub": _bg_age(p.get("sub"), now),
                                   "bg": _bg_age(p.get("bgs"), now)},   # longest elapsed per kind (min)
    })


def _row_ctx(p, win, win_src):
    """ctx·model·win·winSrc·winN — context size and window."""
    return {
        "ctx": p.get("ctx") or 0,         # context size of the last response (tokens)
        "model": _model_label(p.get("model")),
        "win": win,                       # context window (0 = unknown → no %)
        "winSrc": win_src,                # obs=proven by that session · model=learned from measurements of the same model
        "winN": _model_win(p.get("model"))[1] if win_src == "model" else 0,
    }


def _row_status(st0, o, p, now, mt):
    """state·blocked·otel·otelEv."""
    return {
        "state": st0,
        # ★Stuck spot — **sessions where an approval·choice prompt is up and a person must press to proceed**.
        #   The transcript cannot tell (nothing is written while a permission prompt is up) → only the two grounds below:
        #     (1) a fast tool (Edit/Write/Read/Grep…) has been pending past BLOCK_GRACE_S — these tools
        #        finish within 1s once approved, so pending for long means waiting.
        #     (2) Bash, but **that session has no running process** (tool_busy). But if a background command is running
        #        its process is caught and the check blurs — then do not claim at all.
        #   MCP tools can legitimately take long (browser control), so they are excluded. If unknown, do not set.
        "blocked": _blocked(st0, p.get("tool") or "", int(now - mt), p.get("cwd") or "",
                            len(p.get("bgs") or []), p.get("pmode") or ""),
        "pmode": p.get("pmode") or "",    # permission mode (metadata; auto/bypass/dontAsk never prompt)
        "otel": bool(o),                  # is this row's state **event-based** (not inferred)
        "otelEv": (o or {}).get("ev") or "",
        "otelAt": int((o or {}).get("at") or 0),   # time of otelEv (perm_marks: a decision after the prompt clears it)
    }


def _session_row(fp, mt, now, live, p, stale=False):
    """Merge the parse result (fixed) + current state (process·git·window) into one screen row. **Row assembly happens only here.**

    stale=True means "a process exists at this path but a newer transcript has already taken that slot".
    The result is the same as no process (ended), so it is frozen to done here — so that "currently running" things
    like sub·bgs·mon are emptied too (preserving the property that row assembly happens in one place)."""
    # ⚠Key order and call order match the pre-split literal (helpers are splatted in place).
    win, win_src = _ctx_window(p.get("model"), p.get("ctx") or 0, fp)
    st0, o, got, dead = _row_state(mt, now, live, p, stale)
    return {
        "id": _sid8(p.get("sid") or os.path.basename(fp)),
        "sid": p.get("sid") or "",        # ★full session id — used to build the `claude --resume` command (8 chars is not enough)
        "project": _proj_name(p.get("cwd")) or "?",   # name and «root» come from the git root (ident._proj_root)
        "root": _proj_root(p.get("cwd")),
        # seconds the prompt was received but the transcript did not move — 0 means not applicable
        "gotPrompt": got,
        # context per request · burn per minute (tokens/min) · requests per minute — based on the recent tail span
        "creq": p.get("creq") or 0, "burn": p.get("burn") or 0, "rpm": p.get("rpm") or 0,
        "cwd": p.get("cwd") or "",
        "branch": "" if p.get("branch") in (None, "HEAD") else p.get("branch"),
        "tool": ((o or {}).get("tool") if (o and o.get("state") == "tool") else None) or p.get("tool") or "",
        # ⚠Only an Agent call's one-line description — other targets are tool input (Bash command, path): rule 1, 2026-09-25.
        "targ": (p.get("targ") or "") if p.get("tool") in _DESC_TOOLS else "",
        **_row_children(fp, p, now, dead, pl_runs.pl_act(st0, st0 == "tool" and perm_wait(p.get("sid") or "", p.get("actAt") or mt, now), dead)),
        "kind": p.get("kind") or "",
        # ★Measured from **last activity**, not file mtime — so noise records (away_summary) touching the file
        #   do not look like "just worked". If the tail window has no activity at all, fall back to mtime.
        "ageSec": int(now - (p.get("actAt") or mt)),
        "bytes": (lambda: (os.path.getsize(fp) if os.path.exists(fp) else 0))(),  # transcript size
        "repos": session_repos(fp, mt, p.get("cwd")),   # git repositories this session touched
        "wt": _wt_of(p.get("cwd")),       # {root, main, name} — Branches tab work unit + sidebar worktree chip
        # mbox = this session's mailbox id (including guesses) · mboxSrc = its source (weak = not an invite target); one lookup per row
        **dict(zip(("mbox", "mboxSrc"), mbox_of(p.get("cwd")))),
        "cost": round(_projcost_of(p.get("cwd")), 2),   # ★project total (not per session — comment above)
        **_row_ctx(p, win, win_src),
        # ⚠No `task`/`reply` (human instruction · assistant reply text) — message bodies (rule 1, 2026-09-25).
        #   `sessions()` hands `task` to the transition check server-side only (to skip /exit·/clear); cards carry no text.
        "git": _git_state(p.get("cwd")),  # unpushed·dirty — how far the output got
        # ★Leftovers — count of uncommitted files left by dead agents in this cwd. Reads only the value stamped by `_fail_loop` (60s).
        "wreck": _WRECK_BY_CWD.get(p.get("cwd") or "", 0),
        **_row_status(st0, o, p, now, mt),
        "err": bool(p.get("err")),
        "rep": p.get("rep") or {"n": 0, "tool": ""},   # consecutive identical tool calls at the tail (loop signal)
        "plat": "cc",                     # ★platform marker — the only key separating external CLI rows (`ext_rows`)
        **_row_acct(p.get("sid") or os.path.basename(fp)[:-6], fp),
    }


def _row_acct(sid, fp):
    """acct·acctDir — account label + dir only for a non-primary account; absent otherwise (single-root rows unchanged)."""
    lab, d = claude_roots.acct_of(sid, fp)
    return {"acct": lab, "acctDir": d} if lab else {}


def sessions(max_age_h=12, cap=40):
    """Work state of recently active Claude sessions. Failure does not kill the page (empty list)."""
    dflt = max_age_h == 12 and cap == 40
    if dflt:                              # in-flight count lets sessions_snapshot_wait() join instead of recomputing
        with _SNAP_CV:
            _SNAP["busy"] += 1
    try:
        return _sessions(max_age_h, cap)
    finally:
        if dflt:
            with _SNAP_CV:
                _SNAP["busy"] -= 1
                _SNAP_CV.notify_all()


def _sessions(max_age_h, cap):
    out, said = [], []

    try:
        now = time.time()
        live = live_cwds()
        # ★Transcripts dropped by age are revived if their path is alive (see _recent_transcripts comment below)
        # ★Assign per-path live slots starting from the newest transcript (_recent_transcripts is newest first).
        #   With 2 processes only the newest 2 count as alive; the rest are frozen as ended.
        #   Without this, dead shells of the same path linger in the list as `Awaiting input`.
        slots = dict(live) if isinstance(live, dict) else {}
        for mt, fp in _recent_transcripts(now, max_age_h, live)[:cap]:
            # ★Put **the subagents directory time** into the cache key too (2026-09-02: a subagent's nested Explore
            #   showed up late on screen).
            #   Depth-1 ones stamp a `tool_use` in the session transcript, so the file changes and they are caught immediately.
            #   But **the line launching a nested agent exists only in the parent agent's log** — the session file
            #   does not change a single byte meanwhile. So the cache kept hitting, and the revival block
            #   (lower part of _running_bg) that picks up nested Explore **never ran at all**. They appeared only when the session
            #   next wrote something (usually the parent's completion notice — minutes later).
            #   Measured: meta.json and jsonl appear **simultaneously** (median -0.1s) — the lag was here, not in the harness.
            # ★Sessions with something running are re-read at least every 30s — to take down finished nested agents.
            sd = fp[:-len(".jsonl")] if fp.endswith(".jsonl") else fp
            key = (mt, _subs_mt(sd))
            with _parse_lock:
                hit = _parse_cache.get(fp)
            # ⚠`_subs_newer` too: with every row popped (`_bg_open` empty) a resumed agent's log growth is invisible otherwise.
            fresh = bool(hit) and hit[0] == key and (
                now - hit[2] < 30 or (not _bg_open.get(fp) and not _subs_newer(sd, hit[2])))
            if fresh:
                p = hit[1]                 # if the file did not change, **skip parsing** (cold ~124ms · hit ~1ms)
            else:
                p = _parse_transcript(fp)   # ★parse outside the lock — holding hundreds of ms here is not allowed
                p["contd"] = _continued(fp)  # 16 KB tail, only on cache miss (file changed)
                with _parse_lock:
                    _parse_cache.put(fp, (key, p, time.time()))
            cwd = p.get("cwd") or ""
            stale = False
            if sid_alive(p.get("sid")):
                pass                     # confirmed by id — neither uses nor loses a path slot
            elif p.get("contd") and isinstance(live, dict) and cwd in live:
                stale = True             # continued elsewhere (`_continued`) — leave the slot to the successor
            elif isinstance(live, dict) and cwd in live:
                if slots.get(cwd, 0) > 0:
                    slots[cwd] -= 1          # this transcript takes that process's slot
                else:
                    stale = True             # slots are full — an old session of the same path
            row = _session_row(fp, mt, now, live, p, stale)
            _note_bg_done(fp, row)          # finished ones become cards here (after the row is built, so project·cwd are known)
            out.append(row)
            said.append({"task": p.get("task") or ""})   # server-side only: end-command check in _note_transition
    except Exception as e:                        # emptying silently would be misread as "no sessions"
        warn_once("sessions", "Could not read session state ({err})", vars={"err": f"{type(e).__name__}: {e}"})
    # ★Sort by state first — the purpose of the screen is "is it my turn", so those rows must be on top.
    # ★Transition decisions happen **inside a dedicated lock** (2026-09-07). This spot reads-and-modifies `_prev_state`, so
    #   overlapping shows the same card twice. Previously `state()`'s `_lock` happened to serialize polls, but
    #   that lock was narrowed (AUDIT cause 4), so the owner lock lives here.
    #   ⚠Timeline·work history·git·leftovers·wkuse·invites already called `sessions()` without `_lock` before
    #     ⇒ this spot **was already overlapping**. This lock plugs that hole too.
    with _note_lock:
        for info, txt in zip(out, said):
            _note_transition(dict(info, **txt))
            _note_ctx(info)
    # ⚠External CLI rows are merged **after** the `_note_*` above — feeding them in would raise cards (transition·context) wrongly.
    try:
        ext_children(out)                         # Gemini runs launched by a Claude session hang under it
    except Exception as e:
        warn_once("ext-children", "Could not attach child Gemini runs ({err})",
                  vars={"err": f"{type(e).__name__}: {e}"})
    out.extend(ext_rows())
    out.extend(ext_rollout_rows())                # Codex without hooks: fresh rollout -> coarse row (hook row wins)
    try:   # ⚠after ext_rows: external rows need `term` too (before, Codex rows always showed «Copy command»)
        term_attach(out)                          # row.term = {app, tty} for «To terminal» (metadata only)
    except Exception as e:
        warn_once("term-attach", "Could not attach terminal tab info ({err})",
                  vars={"err": type(e).__name__}, soft=True)
    rank = {"ask": 0, "abort": 1, "tool": 2, "think": 3, "wait": 4, "unknown": 5, "done": 6}
    out.sort(key=lambda r: (rank.get(r.get("state"), 9), r.get("ageSec", 0)))
    # ★Fill the session id → project map. Live top3 uses it to turn OTel's session.id into a human-readable
    #   name (this already runs every poll, so no extra cost).
    # ⚠`list(_sid_proj)` during cap cleanup raises `RuntimeError: dictionary changed
    #   size during iteration` the moment someone else inserts a key (a pitfall already hit in `_parse_cache`) ⇒ do it inside the same lock.
    with _note_lock:
        for r in out:
            if r.get("sid"):
                _sid_proj.put(r["sid"], r.get("project") or r.get("id") or "")
    if max_age_h == 12 and cap == 40:
        _SNAP["at"], _SNAP["rows"] = time.time(), out
    return out


# ★Last default-args result, refreshed by every state() poll. Readers that tolerate staleness use it instead of
#   paying a 0.25-1 s sessions() call on a request path (2026-09-24: /api/branches stalled ~1 s in wt_signals).
_SNAP = {"at": 0, "rows": [], "busy": 0}   # busy = default sessions() calls in flight
_SNAP_CV = threading.Condition()


def sessions_snapshot(max_age=60):
    """Rows from the last default sessions() call if it is at most `max_age` s old, else None. ⚠Do not mutate."""
    at, rows = _SNAP["at"], _SNAP["rows"]
    return rows if at and time.time() - at <= max_age else None


def sessions_snapshot_wait(timeout=8.0, max_age=60):
    """sessions_snapshot(), but if a default sessions() call is in flight wait up to `timeout` s for it.
    ★2026-09-28: right after a restart the first «Structure» request ran a second cold sessions() beside the page's
      first /api/state (module-measured 1.1 s vs 0.06 s once the snapshot exists). None = nothing in flight/timeout."""
    end = time.time() + timeout
    with _SNAP_CV:
        while (_SNAP["busy"] or _REFRESH["on"]) and sessions_snapshot(max_age) is None:
            left = end - time.time()
            if left <= 0:
                break
            _SNAP_CV.wait(left)
    return sessions_snapshot(max_age)


_REFRESH = {"on": False}   # one background refresh at a time (guarded by _SNAP_CV)


def _refresh_run():
    try:
        sessions()             # never raises (warns itself)
    finally:
        with _SNAP_CV:
            _REFRESH["on"] = False
            _SNAP_CV.notify_all()


def sessions_cached(wait=0.5, max_age=60, cold_wait=None):
    """`(rows, fresh)` for request/hook paths — ⚠never runs sessions() in the calling thread.
    ★2026-09-29: cold sessions() took 40 s when spawns were slow; request/hook callers timed out.
    Stale -> start one background refresh, wait <=`wait` s (`cold_wait` before any snapshot), else the last rows or []."""
    rows = sessions_snapshot(max_age)
    if rows is not None:
        return rows, True
    with _SNAP_CV:
        kick, _REFRESH["on"] = not _REFRESH["on"], True
    if kick:
        threading.Thread(target=_refresh_run, name="sessions_refresh", daemon=True).start()
    rows = sessions_snapshot_wait(cold_wait if cold_wait is not None and not _SNAP["at"] else wait, max_age)
    return (rows, True) if rows is not None else (_SNAP["rows"] if _SNAP["at"] else [], False)


def sessions_rows(wait=0.5, max_age=60):
    """Rows only of `sessions_cached()` — the drop-in for request-path `sessions()` calls. ⚠Do not mutate."""
    return sessions_cached(wait, max_age)[0]
