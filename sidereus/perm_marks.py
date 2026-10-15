"""Permission-prompt markers (hooks/perm_mark.py) -> row `blocked`. Split from live_probe; owns PERM_DIR, PERM_MAX_S."""
import json
import os
import re
import time
from sidereus.config import DATA_DIR
from sidereus.live_probe import _UUID_RE, tool_busy


# Permission-prompt markers from hooks/perm_mark.py (Notification permission_prompt): {sid, t} only.
# ⚠Covers what _blocked() cannot see (auto/bypass modes, MCP, background Bash); valid only while newer than the row's last activity.
PERM_DIR = os.path.join(DATA_DIR, "permwait")
# Horizon of the _DEC_AT decision memo only. ⚠Never an age cap on a marker: an unanswered prompt shows until newer
#   activity, a decision, or the session ends (row state leaves tool/wait); a dead Claude process makes the row `done`.
PERM_MAX_S = 7 * 86400
# Subagent markers: <sid>.<agent_id>.json = {sid, t, k, aid[, tool]} (hooks/perm_mark.py).
_SUB_NAME = re.compile(r"^([0-9a-zA-Z-]{8,64})\.([0-9a-zA-Z_-]{1,64})\.json$")
_SUB_STATES = ("run", "think", "tool", "ask", "wait")
# ★Agent logs are flushed ~0.1 s after a line's timestamp (185 logs: median 0.102 s, max 0.559 s) — PreToolUse hook lines
#   written just before the dialog can land after the PermissionRequest marker (measured 52 ms apart), so allow this slack.
_SUB_FLUSH_S = 1.0


def _read(name):
    """Marker dict or None."""
    try:
        with open(os.path.join(PERM_DIR, name), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _mark_t(sid, act_at, now, skip_ask=False):
    """Marker time if a permission prompt was raised after the session's last activity (any age); else 0."""
    if not sid or not _UUID_RE.fullmatch(sid):
        return 0
    d = _read(sid + ".json")
    try:
        t = float((d or {}).get("t") or 0)
    except (ValueError, TypeError):
        return 0
    # ⚠A main AskUserQuestion prompt is the main turn asking the user, never a subagent waiting.
    if skip_ask and (d or {}).get("tool") == "AskUserQuestion":
        return 0
    return t if act_at < t <= now + 5 else 0


# agent id -> its own log path, filled by bgtasks at each parse-cache refresh (bgtasks sits after this module, so it calls in).
_SUB_LOG = {}
_SUB_LOG_MAX = 2000


def note_sub_log(aid, path):
    """Record where agent `aid` writes its log (bgtasks._lab)."""
    if not aid or not path:
        return
    if len(_SUB_LOG) >= _SUB_LOG_MAX and aid not in _SUB_LOG:
        _SUB_LOG.clear()
    _SUB_LOG[str(aid)] = path


def _sub_act(s, now):
    """Absolute last-activity time of sub row s (its log mtime), else None.
    ⚠`idle` is relative to the parse-cache refresh, so `now - idle` drifts forward until the next refresh and
    passed a waiting sub's marker (badge missing 44/120 polls); stat the log itself, `now - idle` only as a fallback."""
    if not isinstance(s, dict) or not isinstance(s.get("idle"), int):
        return None
    path = _SUB_LOG.get(str(s.get("aid") or ""))
    try:
        return os.path.getmtime(path) if path else now - s["idle"]
    except OSError:
        return now - s["idle"]          # log gone (rotated/removed): the snapshot value is the only evidence left


def _sole_shell_owner(r, aid):
    """True when sub `aid` is the only agent of row r that could own a Bash shell in its cwd (fail toward the badge)."""
    if r.get("state") == "tool" and r.get("tool") == "Bash":
        return False
    for s in r.get("sub") or []:
        if isinstance(s, dict) and str(s.get("aid") or "") != aid \
                and str(s.get("now") or "").split(" · ")[0].strip() == "Bash":
            return False
    return not any(isinstance(a, dict) and a.get("st") == "run" and str(a.get("aid") or "") != aid
                   for w in (r.get("wf") or []) if isinstance(w, dict) for a in (w.get("agents") or []))


_DUP_MAIN_S = 15      # a tool-less main marker this soon after a sub marker is the Notification fallback of that prompt


def _main_open(r, subs, now):
    """True when the session's main marker is an open prompt of its own (not the Notification duplicate of a sub prompt)."""
    sid = r.get("sid") or ""
    mt = _mark_t(sid, now - int(r.get("ageSec") or 0), now)
    if not mt:
        return False
    if (_read(sid + ".json") or {}).get("tool"):
        return True
    return not any(-_SUB_FLUSH_S <= mt - t <= _DUP_MAIN_S for t, _tool, _aid in subs)


def _sub_decided(r, acts, subs, now):
    """True when the session's sole open prompt (a sub marker) has a matching OTel decision no other agent can own."""
    if len(subs) != 1 or _main_open(r, subs, now):
        return False                  # several prompts open: a decision cannot be attributed (never drop a real wait)
    t, tool, aid = subs[0]
    # ⚠OTel decisions are session-wide (auto-approved tools emit them too), so a decision only counts when no other writer
    #   exists since the prompt: every agent writes its tool_use line before its own decision, and the waiting sub writes nothing.
    if not tool or ((_DEC_AT.get(r.get("sid") or "") or {}).get("tools") or {}).get(tool, 0) <= t:
        return False
    if now - int(r.get("ageSec") or 0) >= t + _SUB_FLUSH_S:
        return False                  # the main turn wrote after the prompt: the decision may be its own
    if len([s for s in (r.get("sub") or []) if isinstance(s, dict)]) != len(
            [s for s in (r.get("sub") or []) if isinstance(s, dict) and str(s.get("aid") or "") in acts]):
        return False                  # a sub with unknown activity could own the decision
    return all(a < t + _SUB_FLUSH_S for k, (a, _b) in acts.items() if k != aid)


def _sub_badge(r, files, now):
    """Newest marker time of a subagent of row r still waiting on its own prompt, else 0.
    ⚠Compared with that agent's own activity, not the main transcript: the main turn keeps writing while a sub waits."""
    _note_dec(r, now)
    acts = {}
    for s in r.get("sub") or []:
        a = _sub_act(s, now) if isinstance(s, dict) and s.get("aid") else None
        if a is not None:
            acts[str(s["aid"])] = (a, (str(s.get("now") or "").split(" · ")[0].strip() == "Bash"))
    for w in r.get("wf") or []:
        for a in (w.get("agents") or []) if isinstance(w, dict) else []:
            if isinstance(a, dict) and a.get("aid") and isinstance(a.get("end"), int):
                acts.setdefault(str(a["aid"]), (a["end"], False))
    subs = []
    for aid, name in files:
        if aid not in acts:
            continue                  # unknown or finished agent: no evidence it is still waiting
        d = _read(name)
        try:
            t = float((d or {}).get("t") or 0)
        except (ValueError, TypeError):
            continue
        act, bash = acts[aid]
        if not (act < t + _SUB_FLUSH_S and t <= now + 5):
            continue
        # ⚠Never cleared via _answered: OTel decisions are session-wide, a main-turn decision says nothing about this sub
        #   (_sub_decided accepts one only when it is attributable to this sub).
        # ⚠The shell probe is per process cwd and carries no agent id, so a live shell clears the badge only when this sub
        #   is the sole possible owner: not while the parent runs its own Bash or another sub/workflow agent could run one.
        #   An approved Bash writes nothing to the sub log until its result, so the probe cannot simply be dropped.
        if bash and _sole_shell_owner(r, aid) and _bash_running(dict(r, tool="Bash")):
            continue
        tool = (d or {}).get("tool")
        subs.append((t, tool if isinstance(tool, str) else "", aid))
    if _sub_decided(r, acts, subs, now):
        return 0
    return max([t for t, _tool, _aid in subs] or [0])


# sid -> {"t": newest OTel tool_decision/tool_result time, "tools": {tool name: newest tool_decision time}};
#   kept here because _otel holds only the latest event.
# ⚠After PERM_MAX_S (7 days) with no new activity a decided marker can reappear as blocked (accepted: low risk).
_DEC_AT = {}


def _note_dec(r, now):
    """Record the row's latest OTel decision/result. Reads row otelEv/otelAt/tool (sessions.py) — otel sits after
    perm_marks in STAGE3 order, so no import. On a tool_decision the row `tool` is the decision's tool_name."""
    sid = r.get("sid") or ""
    if r.get("otelEv") in ("tool_decision", "tool_result") and isinstance(r.get("otelAt"), int):
        e = _DEC_AT.setdefault(sid, {"t": 0, "tools": {}})
        e["t"] = max(e["t"], r["otelAt"])
        tool = r.get("tool")
        if r["otelEv"] == "tool_decision" and isinstance(tool, str) and tool:
            if len(e["tools"]) >= 64 and tool not in e["tools"]:
                e["tools"].clear()
            e["tools"][tool] = max(e["tools"].get(tool, 0), r["otelAt"])
    for k in [k for k, v in _DEC_AT.items() if now - v["t"] > PERM_MAX_S]:
        _DEC_AT.pop(k, None)


def _answered(r, t, now):
    """True when an OTel tool_decision/tool_result for the row's session came after marker time t (approved or denied)."""
    _note_dec(r, now)
    return (_DEC_AT.get(r.get("sid") or "") or {}).get("t", 0) > t


def _bash_running(r):
    """True when the row's pending Bash has a live shell child in its cwd (approved and running, not waiting)."""
    if r.get("tool") != "Bash" or r.get("bgs"):
        return False                  # ⚠a background command in the same cwd would look like the pending one running
    busy = tool_busy()
    return isinstance(busy, dict) and bool(r.get("cwd")) and r["cwd"] in busy


def perm_wait(sid, act_at, now):
    """True if a permission prompt was raised after the session's last activity."""
    return bool(_mark_t(sid, act_at, now))


def _wf_wait_act(r, now):
    """Activity time of a `wait` row whose running Workflow has a running agent, else None (row not eligible)."""
    ends = [a.get("end") for w in (r.get("wf") or []) if isinstance(w, dict) and w.get("run")
            for a in (w.get("agents") or []) if isinstance(a, dict) and a.get("st") == "run"]
    if not ends or not all(isinstance(e, int) for e in ends):
        return None
    return max(ends)


def perm_rows(rows, now=None):
    """rows with `blocked` set from permission markers (copies changed rows; the cached snapshot stays untouched)."""
    now = time.time() if now is None else now
    try:
        names = os.listdir(PERM_DIR)
    except OSError:
        return rows
    if not names:
        return rows
    subs_by_sid = {}
    for n in names:
        m = _SUB_NAME.match(n)
        if m:
            subs_by_sid.setdefault(m.group(1), []).append((m.group(2), n))
    out = []
    for r in rows:
        # ageSec is from the snapshot's clock; a stale snapshot only makes the marker look older (never a false badge).
        if not isinstance(r, dict) or r.get("blocked"):
            out.append(r)
            continue
        sid, act = r.get("sid") or "", now - int(r.get("ageSec") or 0)
        # ⚠`think` + a named tool counts too: with parallel tool calls the first tool_result is the newest transcript line
        #   (shape result -> think) while the other call waits on its prompt; that prompt's marker is newer than the result line.
        if r.get("state") == "tool" or (r.get("state") == "think" and r.get("tool")):
            t = _mark_t(sid, act, now)
            # ⚠An approved long tool writes nothing until its result, so the marker stays newer than activity: clear on decision/running shell.
            if t and not _answered(r, t, now) and not _bash_running(r):
                tool = r.get("tool") or ""
                base = tool.split("__")[-1] if tool.startswith("mcp__") else tool
                # blockedAt = marker time: a stable episode id for attention `since` / OS-notify (a new prompt = a new episode).
                # blockedTool = tool name alone so the client translates the fixed phrase; `blocked` keeps the old English form.
                r = dict(r, blocked=(base + " waiting for approval") if base else "waiting for approval", blockedAt=int(t),
                         blockedTool=base)
        elif r.get("state") == "wait":
            # A background subagent's or Workflow agent's prompt lands after the main turn ended; their latest log writes count as activity.
            # ⚠Only rows with a running sub / running wf agent — an idle row would turn any old marker into a false badge.
            subs = r.get("sub") or []
            sacts = [_sub_act(s, now) for s in subs]
            wfa = _wf_wait_act(r, now)
            # ⚠A sub without an int idle (or a wf agent without an int end) has unknown activity — skip (fail toward no badge).
            if (subs or wfa is not None) and all(a is not None for a in sacts):
                acts = [act] + ([max(sacts)] if sacts else []) + ([wfa] if wfa is not None else [])
                t = _mark_t(sid, max(acts), now, skip_ask=True)
                if t and not _answered(r, t, now):
                    r = dict(r, blocked="subagent waiting for approval", blockedAt=int(t))
        if not r.get("blocked") and r.get("state") in _SUB_STATES and sid in subs_by_sid:
            t = _sub_badge(r, subs_by_sid[sid], now)
            if t:
                r = dict(r, blocked="subagent waiting for approval", blockedAt=int(t))
        out.append(r)
    return out
