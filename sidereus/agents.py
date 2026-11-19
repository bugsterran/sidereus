"""Subagent metadata: meta/last/tools/finish lookups, boot time, transcript globs, stage marks."""
import glob
import json
import os
import re
import subprocess
import time
from sidereus.config import DATA_DIR, IS_MAC
from sidereus.warn import warn_once
from sidereus.memo import BoundedMemo
from sidereus.redact import redact
from sidereus.transcript import _tail_incr, _tail_lines


# ★**What a subagent is doing now** (2026-08-27, wanted to see in Sidereus what task each is on).
#   Basis: subagents also write their own transcripts —
#     <session>/subagents/agent-<id>.jsonl        conversation (all tool calls are recorded)
#     <session>/subagents/agent-<id>.meta.json    {agentType, description, toolUseId, spawnDepth, parentAgentId}
#   `toolUseId` **links 1:1** to the parent's Agent call id — so they pair without guessing.
# ★Cost: meta is under 200 bytes, cheap to read all. Bodies read only the tail, cached by (path, mtime).
#   Measured 2026-08-27: scan 820 meta + tail reads only for running ones.
_AGENT_META = {}          # session dir → (scan time, {toolUseId: {...}})
_DESC_TOOLS = ("Agent", "Task")   # tools whose `description` is the allowed one-line agent label
# ★Measured 2026-09-25: agent files a timeline touches = 244 (24h) / 639 (72h) / 842 (168h max window), 3087 on disk;
#   ~400-500 B per entry. The old 200/200/400 caps thrashed on every poll. ⇒ 4000 per cache (~2 MB each worst case).
# ⚠Keyed by file, not (file, mtime): the old key left one dead entry per mtime change of a live agent, and
#   insertion-order eviction then threw out the stable finished-agent entries → next poll paid the cold 1-7s.
#   ⇒ A new mtime/size replaces the entry in place; hits move to the end so eviction is LRU.
AGENT_CACHE_MAX = 4000
_AGENT_LAST = BoundedMemo(AGENT_CACHE_MAX)   # file → ((mtime, size), ("tool" or "Agent · description", tool pending?))


def _stat_sig(fp):
    """(mtime, size) of `fp`; raises OSError if missing."""
    st = os.stat(fp)
    return st.st_mtime, st.st_size


def _subs_mt(sess_dir):
    """Modification time of that session's `subagents/` directory.

    ★Changes **only when a new agent appears** (lines appended to existing files do not change it). So
      'is there a newly launched agent' is known with a single stat — no need to scan all files."""
    try:
        return os.path.getmtime(os.path.join(sess_dir, "subagents"))
    except OSError:
        return 0.0


def _subs_newer(sess_dir, t):
    """True if any subagent log of that session was written after `t`.
    ★2026-09-24: a resumed agent appends to its **existing** log, so neither the session file nor `subagents/` mtime
      changes; with `_bg_open` empty the parse cache stayed «fresh» and revival never ran (b8c9d0e1 showed sub=[])."""
    for m in _agent_meta(sess_dir).values():
        try:
            if os.path.getmtime(m.get("_file") or "") > t:
                return True
        except OSError:
            continue
    return False


def _agent_meta(sess_dir, ttl=20):
    dmt = _subs_mt(sess_dir)
    hit = _AGENT_META.get(sess_dir)
    # ★If the directory changed, re-read **ignoring the TTL** (2026-09-02: nested Explore showed up
    #   late on screen). It means a new agent appeared, so no reason to wait 20s.
    if hit and hit[2] == dmt and time.time() - hit[0] < ttl:
        return hit[1]
    out = {}
    d = os.path.join(sess_dir, "subagents")
    try:
        for fn in os.listdir(d):
            if not fn.endswith(".meta.json"):
                continue
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    m = json.load(f)
            except (OSError, ValueError) as e:
                warn_once("agmeta1", "Could not read one agent meta file ({err}) — that row is missing",
                          vars={"err": type(e).__name__}, soft=True)
                continue
            tid = m.get("toolUseId")
            if tid:
                m["_file"] = os.path.join(d, fn[:-len(".meta.json")] + ".jsonl")
                m["_id"] = fn[len("agent-"):-len(".meta.json")]   # the file name is the agent id
                out[tid] = m
    except OSError:
        pass                               # no subagents dir yet
    except Exception as e:                 # e.g. a non-dict meta.json — aborts this session's list
        warn_once("agmeta", "Could not read agent metadata ({err}) — some agent rows are missing",
                  vars={"err": type(e).__name__}, soft=True)
    _AGENT_META[sess_dir] = (time.time(), out, dmt)
    return out


_BOOT = [None]     # None = not computed yet; 0.0 = unavailable (cached so a failing sysctl runs once)


def boot_time():
    """Last boot time (unix seconds). 0 if unreadable — then this check is not used at all.

    ★Why needed (measured 2026-08-27): a reboot orphaned subagents, and
      neither the main session nor the viewer knew. No completion notice could come (the process was gone), and the last record
      was a tool call so `_agent_ended` saw it as 'still working'. So it stayed 'running' for 63 min.
    ★Boot time is **not a guess** — a process cannot survive a reboot. If the last activity is
      before boot, that agent is certainly dead. Unlike other checks in this file, there is no gray zone here."""
    if _BOOT[0] is not None:
        return _BOOT[0]
    if not IS_MAC:
        return 0.0      # ⚠non-Mac — no `kern.boottime`. At 0 the orphan check is not used at all
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"],  # nosec B607 -- PATH lookup on purpose: the tool's location differs per OS
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=3).stdout
        m = re.search(r"sec\s*=\s*(\d+)", out)
        _BOOT[0] = float(m.group(1)) if m else 0.0
    except Exception as e:
        warn_once("boottime", "Could not read boot time ({err}) — orphan-agent check is off",
                  vars={"err": type(e).__name__}, soft=True)
        _BOOT[0] = 0.0
    return _BOOT[0]


def _agent_ended(fp):
    """Did that subagent **deliver its final report and end**. If the last line is assistant text without a tool call, it ended.

    ★Why needed (measured 2026-08-26): some agents **never get** a completion notice. One left its final report
      and ended, yet stayed 'running' for 24 min. The viewer principle is "do not declare
      death from quiet", but that principle was set when subagent activity **could not be seen**. Now that they have
      their own logs, silence is not guessed at; only **the log saying it ended** is used as evidence.
    ⚠The check looks only at the last line. If it keeps working after an interim report, later lines appear and this check flips.
    ★A run that reports through the `SubagentHandback` tool ends on that tool's (non-error) result, not on text —
      without this, every such agent read as «Stopped without a report» (90 of 94 rows in a 12h window, 2026-10-05)."""
    try:
        lines = _tail_lines(fp, nbytes=200_000, limit=40)
    except Exception as e:                 # _tail_lines already absorbs OSError — anything here is a fault
        warn_once("ag-ended", "agent end check failed ({err}) — shown as running",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return False
    done_ids = None                        # tool_use ids answered by the last tool_result record
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue                       # ⚠tail read: the first line is cut mid-record — expected
        c = (e.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        bs = [b for b in c if isinstance(b, dict)]
        kinds = {b.get("type") for b in bs}
        if done_ids is not None:
            # The record before the last tool_result: ended only if it called SubagentHandback and that call succeeded.
            return any(b.get("type") == "tool_use" and b.get("name") == "SubagentHandback" and b.get("id") in done_ids
                       for b in bs)
        if "tool_result" in kinds:
            ok = {b.get("tool_use_id") for b in bs if b.get("type") == "tool_result" and not b.get("is_error")}
            if not ok:
                return False
            done_ids = ok
            continue
        if "tool_use" in kinds:
            return False               # last event is a tool call — still working
        return "text" in kinds         # text without tools = final report
    return False


def _agent_last(fp):
    """One line of that subagent's **last tool call**. Empty string if none."""
    return _agent_last_busy(fp)[0]


def _agent_busy(fp):
    """True while that last tool call has no tool_result yet — the log is silent during a long tool, not idle."""
    return _agent_last_busy(fp)[1]


def _agent_last_busy(fp):
    try:
        mt, sz = _stat_sig(fp)
    except OSError:
        return "", None                # ⚠busy None = log unreadable: neither working nor idle is claimed
    hit = _AGENT_LAST.get(fp, stamp=(mt, sz))
    if hit is not None:
        return hit
    val, busy, res_ids, any_res = "", False, set(), False
    try:
        for line in reversed(_tail_lines(fp, nbytes=400_000, limit=400)):
            try:
                e = json.loads(line)
            except ValueError:
                continue                   # ⚠tail read: first line may be cut mid-record
            c = (e.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    any_res = True
                    res_ids.add(b.get("tool_use_id"))
            for b in reversed(c):
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                # ⚠Tool name only (+ a nested Agent's one-line description) — never the tool input (Bash command,
                #   path, pattern): AGENTS.md rule 1, enforced 2026-09-25. Shown in the sessions drawer and timeline.
                tgt = inp.get("description") if b.get("name") in _DESC_TOOLS else ""
                val = (b.get("name") or "?") + (" · " + redact(str(tgt))[:60] if tgt else "")
                # Pending = no later tool_result answers it (by id; id-less logs: no later result at all).
                busy = b.get("id") not in res_ids if b.get("id") else not any_res
                break
            if val:
                break
    except OSError:
        val, busy = "", None
    except Exception as e:
        warn_once("aglast", "Could not read an agent's current step ({err})", vars={"err": type(e).__name__}, soft=True)
        val, busy = "", None
    return _AGENT_LAST.put(fp, (val, busy), stamp=(mt, sz))


_AGENT_TOOLS = BoundedMemo(AGENT_CACHE_MAX)  # agent file → (start offset, end offset, cumulative tool call count)
_AGENT_FIN = BoundedMemo(AGENT_CACHE_MAX)    # file → ((mtime, size), ended with a final report?)
AGENT_TOOLS_NB = 64_000_000   # first-read cap — agent logs are ~1MB measured, so it reaches the whole file


def _agent_tools(fp):
    """**Number of tools that subagent actually called**. Counts `tool_use` blocks in the log (not an estimate).

    ★For the summary card to say "N tools" the row needs that count — without it `segs` (activity chunks)
      stood in (2026-09-22). ⚠Do not fill with estimates. If the source lacks it, dropping that line is better.
    ⚠Not counted by substring alone — if a report **quotes** `"type":"tool_use"` that becomes a count.
      Only candidate lines are parsed as JSON and counted from content blocks (measured 46 files 20.7MB cold 0.10s).
    ⚠Append-only, so **only the new tail** is added (`_tail_incr`) — 20MB is not re-read per request."""
    ent = _AGENT_TOOLS.get(fp)
    try:
        lines, bs, be, rs = _tail_incr(fp, AGENT_TOOLS_NB, (ent[0], ent[1]) if ent else None)
    except Exception as e:                 # _tail_incr already absorbs OSError — anything here is a fault
        warn_once("ag-tools", "agent tool count failed ({err}) — last value kept",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return ent[2] if ent else 0
    if bs is None:
        return ent[2] if ent else 0
    n = 0 if (rs or ent is None) else ent[2]
    for ln in lines:
        if '"type":"tool_use"' not in ln:
            continue
        try:
            e = json.loads(ln)
        except ValueError:
            continue                       # ⚠tail read: first line may be cut mid-record
        c = (e.get("message") or {}).get("content")
        if isinstance(c, list):
            n += sum(1 for b in c if isinstance(b, dict) and b.get("type") == "tool_use")
    _AGENT_TOOLS.put(fp, (bs, be, n))   # LRU, not clear(): a full clear re-read every log cold
    return n


def _agent_fin(fp):
    """Cached version of `_agent_ended` — keyed by (file, mtime). The agent row's `fin` uses this.

    ★The end state is not a «status field» in the source — all there is is **the shape of the last record**
      (2026-09-22). So the screen calls it "Stopped without a report" rather than "Abnormal exit"."""
    try:
        mt, sz = _stat_sig(fp)
    except OSError:
        return False
    hit = _AGENT_FIN.get(fp, stamp=(mt, sz))
    if hit is not None:
        return hit
    return _AGENT_FIN.put(fp, _agent_ended(fp), stamp=(mt, sz))


def _bg_show(items, now, dead):
    """[label, launch time] → list of `{lab, min}`.

    ★It used to be mashed into one string, dropping elapsed under 5 min. Seeing **per-item progress** in the tree
      always needs elapsed (1 min or 40 min), and coloring old ones needs a number.
      If the server builds screen strings the client must re-parse them, so the format is sent as data."""
    if dead or not items:
        return []
    out = []
    for it in items:
        lab, at = it[0], it[1]
        row = {"lab": lab, "min": int((now - at) / 60)}
        if len(it) > 2 and it[2]:
            row["now"] = it[2]          # the tool that agent is running now
        if len(it) > 3 and it[3] and it[3] > 1:
            row["depth"] = it[3]        # an agent launched by an agent
        if len(it) > 4 and it[4]:
            row["tid"] = it[4]          # the parent's tool_use id — the modal finds the log with this
        if len(it) > 5 and isinstance(it[5], int) and it[5] >= 0:
            row["idle"] = it[5]         # seconds since its own log was last updated — the only real proof of life
            if len(it) > 9 and it[9]:
                row["idleAt"] = it[9]   # ⚠absolute log mtime: `idle` is frozen in a stale snapshot, so `now - idle` drifts
        if len(it) > 6 and it[6]:
            row["aid"] = it[6]          # that agent's own id
        if len(it) > 7 and it[7]:
            row["par"] = it[7]          # id of the agent that launched it (absent if the session launched it)
        if len(it) > 8 and it[8]:
            row["busy"] = 1             # last tool call still has no result — a quiet log is a long tool, not idle
        elif len(it) > 8 and it[8] is None:
            row.pop("idle", None)       # ⚠log unreadable: without idle the screen shows no «Idle»/«quiet» claim
            row.pop("idleAt", None)
        out.append(row)
    return out


def sub_globs(root):
    """Glob patterns for every subagent transcript under a projects root: plain + workflow agents."""
    return (os.path.join(root, "*", "*", "subagents", "*.jsonl"),
            os.path.join(root, "*", "*", "subagents", "workflows", "*", "agent-*.jsonl"))


def sub_paths(root):
    out = []
    for pat in sub_globs(root):
        out += glob.glob(pat)
    return list(dict.fromkeys(out))   # the patterns cannot overlap; dedupe anyway so a stubbed glob stays exact


def slash(fp):
    """`fp` with `/` separators, for substring tests like "/subagents/" (Windows paths use `\\` or a mix)."""
    return fp if os.sep == "/" else fp.replace(os.sep, "/")


def sub_sess_dir(fp):
    """Session directory of a subagent transcript (plain or workflow); '' when `fp` is not one."""
    i = slash(fp).rfind("/subagents/")   # os.sep is one char, so the index holds for `fp`
    return fp[:i] if i >= 0 else ""


# Main-agent stage marks: hook pl-mark.py writes DATA_DIR/plmark/<sid>.json
#   {name, title, t, cwd} when the MAIN agent runs a Bash described "[pl:<name>/<stage>]". ⚠Only name/title/age reach the page.
PLM_DIR = os.path.join(DATA_DIR, "plmark")
# 300 s kept a finished stage lit; tagged Bash/Agent/SendMessage refresh it.
PLM_LIVE_S = 120       # same as bgtasks.SUB_LIVE_S; [pl:-] deletes
# ⚠Shell-marker marks ("hold": 1, non-Claude CLIs) get no per-tool refresh, so they live until [pl-end:] or this cap (= hooks/pl_flow.py LOST_S).
PLM_HOLD_S = 45 * 60
_PLM_SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")


def plm_of(sid, now):
    """{name, title, age} of the main agent's live [pl:] marker for `sid`, or None (missing/stale/bad file)."""
    if not sid or not _PLM_SID.match(sid):
        return None
    try:
        with open(os.path.join(PLM_DIR, sid + ".json"), "rb") as f:
            d = json.loads(f.read(4096))
        name, title, age = str(d.get("name") or "")[:40], str(d.get("title") or "")[:40], now - float(d.get("t") or 0)
        cap = PLM_HOLD_S if d.get("hold") == 1 else PLM_LIVE_S
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return {"name": name, "title": title, "age": int(age)} if name and title and 0 <= age <= cap else None
