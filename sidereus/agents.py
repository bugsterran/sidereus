"""Subagent metadata: meta/last/tools/finish lookups, boot time, Workflow-tool runs."""
import glob
import json
import os
import re
import subprocess
import time
from sidereus.config import DATA_DIR, IS_MAC
from sidereus import claude_roots
from sidereus.warn import warn_once
from sidereus.memo import BoundedMemo
from sidereus.redact import redact
from sidereus.wf_meta import phase_titles, script_name
from sidereus.transcript import CLAUDE_PROJECTS, _tail_incr, _tail_lines


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


_BOOT = [0.0]


def boot_time():
    """Last boot time (unix seconds). 0 if unreadable — then this check is not used at all.

    ★Why needed (measured 2026-08-27): a reboot orphaned subagents, and
      neither the main session nor the viewer knew. No completion notice could come (the process was gone), and the last record
      was a tool call so `_agent_ended` saw it as 'still working'. So it stayed 'running' for 63 min.
    ★Boot time is **not a guess** — a process cannot survive a reboot. If the last activity is
      before boot, that agent is certainly dead. Unlike other checks in this file, there is no gray zone here."""
    if _BOOT[0]:
        return _BOOT[0]
    if not IS_MAC:
        return 0.0      # ⚠non-Mac — no `kern.boottime`. At 0 the orphan check is not used at all
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=3).stdout
        m = re.search(r"sec\s*=\s*(\d+)", out)
        if m:
            _BOOT[0] = float(m.group(1))
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
        if len(it) > 6 and it[6]:
            row["aid"] = it[6]          # that agent's own id
        if len(it) > 7 and it[7]:
            row["par"] = it[7]          # id of the agent that launched it (absent if the session launched it)
        if len(it) > 8 and it[8]:
            row["busy"] = 1             # last tool call still has no result — a quiet log is a long tool, not idle
        elif len(it) > 8 and it[8] is None:
            row.pop("idle", None)       # ⚠log unreadable: without idle the screen shows no «Idle»/«quiet» claim
        out.append(row)
    return out


# ── Workflow-tool runs ────────────────────────────────────────────────────────
# ★2026-09-26: the Workflow tool keeps its agents one level deeper than plain subagents —
#     <session>/subagents/workflows/wf_<id>/agent-<aid>.jsonl (+ .meta.json without toolUseId)
#     <session>/subagents/workflows/wf_<id>/journal.jsonl   {"type": launched|started|result|failed, agentId, label, phase}
#   Every `subagents/*.jsonl` glob missed them: invisible in the tree/timeline and absent from token totals.
# ⚠journal "result" lines carry the agent's report text — only type/agentId/label/phase are read (AGENTS.md rule 1).
# ⚠The two globs never overlap (`*` does not cross `/`), so adding the second one cannot double count.
WF_LIVE_S = 120        # a run whose journal or agent log moved this recently counts as running (phase gaps are seconds)
WF_KEEP_S = 300        # a finished run stays in the session tree this long, like a just-finished row
WF_HIST_S = 6 * 3600   # finished runs kept for the pipeline-tab Workflow view (`wfh`), same window as pl_runs.PLR_KEEP_S
WF_HIST_N = 10         # newest finished runs per session in `wfh` — bounds the /api/state payload


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


_WF_JOURNAL = BoundedMemo(400)   # journal path -> ((mtime, size), parsed)
_WF_NAME = BoundedMemo(400)      # run dir -> name, or ("", transcript size, tried at) while unresolved


def _wf_journal(fp):
    """{"order": [aid...], "ag": {aid: {lab, phase, st}}, "phase": latest started phase}; st = run|done|fail."""
    try:
        sig = _stat_sig(fp)
    except OSError:
        return {"order": [], "ag": {}, "phase": ""}
    hit = _WF_JOURNAL.get(fp, stamp=sig)
    if hit is not None:
        return hit
    out = {"order": [], "ag": {}, "phase": ""}
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(e, dict):
                    continue
                typ, aid = e.get("type"), str(e.get("agentId") or "")[:40]
                if not aid:
                    continue                  # launch bookkeeping / a failed launch with no agent
                if typ == "started":
                    if aid not in out["ag"]:
                        out["order"].append(aid)
                    out["ag"][aid] = {"lab": redact(str(e.get("label") or ""))[:60], "phase": str(e.get("phase") or "")[:40],
                                      "st": "run"}
                    out["phase"] = out["ag"][aid]["phase"]
                elif typ in ("result", "failed") and aid in out["ag"]:
                    out["ag"][aid]["st"] = "done" if typ == "result" else "fail"
    except OSError:
        return out                            # vanished mid-read — not cached, the next poll retries
    return _WF_JOURNAL.put(fp, out, stamp=sig)


_WF_SCRIPT = re.compile(rb'\\nScript file: ((?:[^"\\]|\\\\)+?)\.js')   # `\\` pair = a JSON-escaped Windows separator


def _wf_name(sess_dir, run_dir):
    """Workflow name = basename of the script file the launch result names for this run ('' if not found).
    ⚠Only the script basename is taken from the parent transcript — never args or result text."""
    hit = _WF_NAME.get(run_dir)
    if isinstance(hit, str):
        return hit
    tp = sess_dir + ".jsonl"
    try:
        sz = os.path.getsize(tp)
    except OSError:
        return ""
    if hit and (hit[1] >= sz or time.time() - hit[2] < 30):
        return ""
    rid = os.path.basename(run_dir).encode()
    keys = (b"workflows/" + rid, b"workflows\\\\" + rid)   # ⚠Windows: the JSON line holds a backslash escaped as `\\`
    name = ""
    try:
        with open(tp, "rb") as f:
            # ⚠Resume where the last miss stopped (minus one partial line) — never re-read a long transcript per poll.
            if hit and hit[1] > 65536:
                f.seek(hit[1] - 65536)
                f.readline()
            for ln in f:
                m = None
                for key in keys:
                    i = ln.find(key)
                    if i >= 0:
                        m = _WF_SCRIPT.match(ln, i + len(key))
                        break
                if m:
                    name = os.path.basename(m.group(1).replace(b"\\\\", b"/").decode("utf-8", "replace"))
                    # ⚠Saved copies are `<name>-<run_id>.js` (same as wf_meta.script_name) — drop the run-id suffix.
                    sfx = "-" + os.path.basename(run_dir)
                    name = (name[:-len(sfx)] if name.endswith(sfx) and len(name) > len(sfx) else name)[:60]
    except OSError:
        return ""
    _WF_NAME.put(run_dir, name if name else ("", sz, time.time()))
    return name


def _wf_dirs(sess_dir):
    d = os.path.join(sess_dir, "subagents", "workflows")
    try:
        return sorted(os.path.join(d, n) for n in os.listdir(d) if n.startswith("wf_"))
    except OSError:
        return []


def _wf_meta(fp):
    """The agent's .meta.json (label/phase fallback before its journal line lands); {} if unreadable."""
    try:
        with open(fp[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return {}
    return m if isinstance(m, dict) else {}


def wf_agent_files(sess_dir):
    """Every workflow agent transcript of a session (for token scans that walk `_agent_meta`)."""
    out = []
    for rd in _wf_dirs(sess_dir):
        out += sorted(glob.glob(os.path.join(rd, "agent-*.jsonl")))
    return out


def wf_runs(sess_dir, now=None, tokf=None, since=0.0):
    """Workflow runs of one session, oldest first. Metadata only: name, phase, counts, times, tokens, labels.
    `tokf(path)` -> tokens of one agent transcript (the caller's index); runs quiet since `since` are skipped.
    Each agent carries a private `_file` — strip it (`wf_public`) before it reaches a payload."""
    now = time.time() if now is None else now
    out = []
    for rd in _wf_dirs(sess_dir):
        jp = os.path.join(rd, "journal.jsonl")
        files = {os.path.basename(p)[len("agent-"):-len(".jsonl")]: p
                 for p in glob.glob(os.path.join(rd, "agent-*.jsonl"))}
        stamps = []
        for p in [jp] + list(files.values()):
            try:
                st = os.stat(p)
                stamps.append((getattr(st, "st_birthtime", st.st_ctime), st.st_mtime))
            except OSError:
                continue
        if not stamps:
            continue
        start, end = min(s[0] for s in stamps), max(s[1] for s in stamps)
        if end < since:
            continue
        j = _wf_journal(jp)
        order = list(j["order"]) + sorted(a for a in files if a not in j["ag"])
        ags, boot = [], boot_time()
        for aid in order:
            fp = files.get(aid, "")
            ja = j["ag"].get(aid) or {}
            a = {"aid": aid, "lab": ja.get("lab") or "", "phase": ja.get("phase") or "", "st": ja.get("st") or "run",
                 "start": int(start), "end": int(start), "tok": 0, "_file": fp}
            if fp:
                try:
                    st = os.stat(fp)
                    a["start"], a["end"] = int(getattr(st, "st_birthtime", st.st_ctime)), int(st.st_mtime)
                except OSError:
                    a["end"] = int(end)
                if not a["lab"] or not a["phase"]:
                    m = _wf_meta(fp)
                    a["lab"] = a["lab"] or redact(str(m.get("description") or ""))[:60]
                    a["phase"] = a["phase"] or str(m.get("workflowPhase") or "")[:40]
                a["tok"] = int(tokf(fp) or 0) if tokf else 0
            if a["st"] == "run" and (now - a["end"] > WF_LIVE_S * 5 or (boot and a["end"] < boot)):
                a["st"] = "cut"               # no result line and a long-quiet log — ended without a report
            ags.append(a)
        done = sum(1 for a in ags if a["st"] == "done")
        live = any(a["st"] == "run" for a in ags) or now - end < WF_LIVE_S
        rid = os.path.basename(rd)
        phases = phase_titles(sess_dir, rid)   # declared order first, then journal phases not declared
        phases += [p for p in dict.fromkeys(ja["phase"] for ja in j["ag"].values() if ja["phase"]) if p not in phases]
        out.append({"id": rid, "name": _wf_name(sess_dir, rd) or script_name(sess_dir, rid), "phase": j["phase"],
                    "phases": phases,
                    "done": done, "fail": sum(1 for a in ags if a["st"] in ("fail", "cut")), "total": len(ags),
                    "start": int(start), "end": int(end), "run": bool(live and not (boot and end < boot)),
                    "tok": sum(a["tok"] for a in ags), "agents": ags})
    return out


def wf_public(runs):
    """Payload copy of `wf_runs` output — drops the private `_file` paths."""
    return [dict(r, agents=[{k: v for k, v in a.items() if not k.startswith("_")} for a in r["agents"]])
            for r in runs]


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


# ── Agent teams ───────────────────────────────────────────────────────────────
# ★2026-09-26: a team leader session keeps its task list and member inboxes outside the projects dir —
#     ~/.claude/tasks/<leader sid>/<N>.json            {id, subject, description, status, blocks, blockedBy, owner}
#     ~/.claude/teams/<leader sid>/inboxes/<member>.json [{from, text, timestamp, read, msg_id, ...}]
#   Teammates are the leader's subagents; their .meta.json carries `name` (= task owner = inbox file stem).
# ⚠Metadata only: task `description` and inbox `text` are never read into a row — subject, owner, status, counts.
TEAM_ROOT = os.path.dirname(CLAUDE_PROJECTS)   # ~/.claude (same base as the projects dir)
TEAM_KEEP_S = 1800     # a team with nothing open stays visible this long after its last write
_TEAM_ST = ("pending", "in_progress", "completed")


def _team_json(fp):
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def team_info(sess_dir, now=None):
    """Team node for a leader session, or None when it has no team files (or the team went quiet)."""
    now = time.time() if now is None else now
    sid = os.path.basename(sess_dir)
    base = claude_roots.root_of(sess_dir)[1] or TEAM_ROOT   # team files live in the transcript's own Claude root
    td, ib = os.path.join(base, "tasks", sid), os.path.join(base, "teams", sid, "inboxes")
    tfs, ifs = glob.glob(os.path.join(td, "*.json")), glob.glob(os.path.join(ib, "*.json"))
    if not tfs and not ifs:
        return None
    last, counts, cur = 0.0, dict.fromkeys(_TEAM_ST, 0), {}
    for fp in sorted(tfs):
        t = _team_json(fp)
        if not isinstance(t, dict):
            continue
        try:
            last = max(last, os.path.getmtime(fp))
        except OSError:
            continue
        st = t.get("status") if t.get("status") in _TEAM_ST else "pending"
        counts[st] += 1
        own = str(t.get("owner") or "")[:60]
        # current task per owner: in_progress wins over pending; completed tasks are not "current"
        if own and st != "completed" and (st == "in_progress" or own not in cur):
            cur[own] = str(t.get("subject") or "")[:80]
    unread = {}
    for fp in ifs:
        box = _team_json(fp)
        name = os.path.basename(fp)[:-len(".json")][:60]
        unread[name] = sum(1 for m in box if isinstance(m, dict) and not m.get("read")) if isinstance(box, list) else 0
        try:
            last = max(last, os.path.getmtime(fp))
        except OSError:
            continue
    members = {}
    for m in _agent_meta(sess_dir).values():
        name = str(m.get("name") or "")[:60]
        fp = m.get("_file") or ""
        if not name or not fp:
            continue
        try:
            mt = os.path.getmtime(fp)
        except OSError:
            continue
        last = max(last, mt)
        st = "done" if _agent_fin(fp) else ("run" if now - mt < WF_LIVE_S else "idle")
        members[name] = {"name": name, "st": st, "model": str(m.get("model") or "")[:40]}
    for name in (set(unread) | set(cur)) - {"team-lead"}:   # the leader's own inbox is the session, not a member
        members.setdefault(name, {"name": name, "st": "idle", "model": ""})
    # `tsub` (task subject, a one-line label) — not `task`, which the metadata-only arch rule reserves for bodies.
    rows = [dict(v, tsub=cur.get(k, ""), unread=unread.get(k, 0)) for k, v in sorted(members.items())]
    live = counts["pending"] or counts["in_progress"] or any(r["st"] == "run" for r in rows)
    if not live and now - last > TEAM_KEEP_S:
        return None
    return {"members": rows, "tasks": counts, "done": counts["completed"], "total": sum(counts.values()),
            "run": bool(live)}
