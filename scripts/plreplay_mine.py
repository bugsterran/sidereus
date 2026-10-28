#!/usr/bin/python3
"""Mine a session transcript into a pl_flow replay fixture skeleton (tests/fixtures/plreplay/*.json).

Offline and metadata only: per tool call it keeps the tool name, the stage tag, subagent_type, model,
background yes/no, a re-numbered agent id, git commit yes/no, error/deny yes/no and a relative time.
⚠Never descriptions, prompts, commands, messages or results — text is only regex-matched, then dropped.
Ids are re-numbered (session -> sess-0001, agents -> a01.., agent types -> ag1..), cwd -> "proj",
the pipeline name -> --name. "cp" is left empty: expectations are written by a person, never generated.

usage: plreplay_mine.py SESSION.jsonl --pipeline PIPE.json [--subagents DIR] [--name pipe] [-o OUT]
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

# Any pipeline marker; the name part is re-numbered below.
TAG = re.compile(r"\[pl(-skip|-model|-end)?:(?:(-)|([a-z0-9-]{1,40})/([^\]\n]{1,80}))\]")
# Shell marks at the command start (copy of pl_flow MARK, the only place «|fail» is read).
MARK = re.compile(r"""^\s*(?:echo\s+|#\s*|:\s+)?["']?(\[pl(-end)?:(?:(-)|([a-z0-9-]{1,40})/([^\]\n|]{1,40})(\|fail)?)\])""")
# ⚠Copies of hooks/pl_flow.py _COMMIT_RE, _DRY_RE and BG_RE; keep them identical or replays drift from the hook.
COMMIT_RE = re.compile(r"(?:^|[\s;&|(])(?:\S*/)?git(?:\s+(?:-C\s+(\"[^\"]*\"|'[^']*'|\S+)|-c\s+\S+|--[\w-]+(?:=\S+)?))*\s+commit(?![\w-])")
DRY_RE = re.compile(r"\scommit(?![\w-])[^;&|\n]*?\s--dry-run(?![\w-])")
BG_RE = re.compile(r"async_launched|Async agent launched|Resuming agent|resumed from transcript|resumedAgentId|"
                   r"Message queued")
DENY_RE = re.compile(r"^(?:Error:\s*)?(?:PreToolUse:\S*\s+hook\s+(?:error|denied)|Hook PreToolUse\S*\s+denied)")
# ⚠A hook deny is often the bare reason ("You skipped ...", "[pl:x/y] expects ...") with no PreToolUse prefix.
#   So a deny = an error from a tool that never ran (toolUseResult a plain string, not a run failure) minus the
#   known non-hook refusals below; matching deny texts alone missed the skip guard.
RAN_RE = re.compile(r"^(?:Error:\s*)?Exit code \d")
NOT_RUN_RE = re.compile(r"^(?:Error:\s*)?(?:<tool_use_error>|User rejected|The user doesn't want|Permission for|"
                        r"\[Request interrupted|Interrupted|The server-side|API Error)")


def _denied(txt, tur):
    s = txt.strip()
    if DENY_RE.match(s):
        return True
    if RAN_RE.match(s) or NOT_RUN_RE.match(s):
        return False
    return isinstance(tur, str) or tur is None   # a tool that ran leaves a structured toolUseResult
TOOLS = ("Agent", "Task", "SendMessage", "Bash")
FIELD = {"Bash": "description", "Agent": "description", "Task": "description", "SendMessage": "summary"}
BUILTIN = ("", "main", "claude", "general-purpose", "Explore", "Plan", "statusline-setup", "output-style-setup",
           "claude-code-guide")
STAGE_KEYS = ("title", "agent", "model", "skill", "gate", "onFail", "onError", "onlyOnJump", "fanout", "produces")


class Ids(object):
    def __init__(self, prefix, width):
        self.prefix, self.width, self.m = prefix, width, {}

    def get(self, k):
        if not isinstance(k, str) or not k:
            return None
        if k not in self.m:
            self.m[k] = "%s%0*d" % (self.prefix, self.width, len(self.m) + 1)
        return self.m[k]


def _ts(s):
    if not isinstance(s, str):
        return None
    for f in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return (datetime.datetime.strptime(s, f) - datetime.datetime(1970, 1, 1)).total_seconds()
        except ValueError:
            pass
    return None


def _lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict):
                yield d


def _text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and isinstance(x.get("text"), str))
    return ""


def _shell(ti):
    c = ti.get("command", ti.get("cmd"))
    if isinstance(c, list):
        c = " ".join(x for x in c if isinstance(x, str))
    return c if isinstance(c, str) else ""


class Miner(object):
    def __init__(self, name, real_names):
        self.name, self.real = name, set(real_names)
        self.aids, self.ags, self.skills = Ids("a", 2), Ids("ag", 0), Ids("sk", 0)
        self.titles = set()

    def agent(self, a):
        return a if (not isinstance(a, str) or a in BUILTIN) else self.ags.get(a)

    def _retag(self, m):
        kind, dash, nm, rest = m.group(1) or "", m.group(2), m.group(3), m.group(4)
        if dash:
            return "[pl%s:-]" % kind
        nm = self.name if nm in self.real else "other"
        # The stage part is either a pipeline title or a value we cannot vouch for: unknown text is replaced.
        title, _, extra = rest.partition("=") if kind == "-model" else rest.partition("|")
        title = title.strip()
        title = title if title in self.titles else "x"
        if kind == "-model":
            extra = extra if re.match(r"^[A-Za-z0-9._-]{1,40}$", extra) else "x"
            return "[pl-model:%s/%s=%s]" % (nm, title, extra)
        tail = "|fail" if extra == "fail" else ""
        return "[pl%s:%s/%s%s]" % (kind, nm, title, tail)

    def tags(self, txt):
        return " ".join(self._retag(m) for m in TAG.finditer(txt or ""))

    def pipe(self, d):
        out = {"v": d.get("v", 1), "name": self.name, "stages": []}
        for s in d.get("stages") or []:
            if not isinstance(s, dict) or not isinstance(s.get("title"), str):
                continue
            self.titles.add(s["title"])
        for s in d.get("stages") or []:
            if not isinstance(s, dict) or not isinstance(s.get("title"), str):
                continue
            o = {}
            for k in STAGE_KEYS:
                if k not in s:
                    continue
                v = s[k]
                if k == "agent":
                    v = self.agent(v)
                elif k == "skill":
                    v = self.skills.get(v)
                elif k == "gate":
                    v = "gate" if v else v   # only presence matters; the command is not kept
                elif k == "onFail" and isinstance(v, dict):
                    v = {x: v[x] for x in ("goto", "max", "then") if x in v}
                elif k in ("fanout", "produces"):
                    v = "slices"
                o[k] = v
            out["stages"].append(o)
        return out

    def events(self, path, aid):
        """Pre/post events of one transcript; aid = re-numbered id when it is a subagent file."""
        uses, out = {}, []
        for d in _lines(path):
            t = _ts(d.get("timestamp"))
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}
            content = msg.get("content")
            if not isinstance(content, list) or t is None:
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") in TOOLS:
                    ev = self._pre(b, t, aid)
                    if ev is not None:
                        uses[b.get("id")] = ev
                        out.append(ev)
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                    pre = uses.pop(b.get("tool_use_id"))
                    post = self._post(pre, b, d.get("toolUseResult"), t)
                    if post is not None:
                        out.append(post)
        return out

    def _pre(self, b, t, aid):
        tool, ti = b.get("name"), b.get("input") if isinstance(b.get("input"), dict) else {}
        tag = self.tags(ti.get(FIELD[tool]) if isinstance(ti.get(FIELD[tool]), str) else "")
        ev = {"t": t, "e": "pre", "tool": tool, "tag": tag, "sub": None, "model": None, "bg": 0, "aid": aid,
              "to": None, "commit": 0, "denied": 0}
        if tool in ("Agent", "Task"):
            ev["sub"] = self.agent(ti.get("subagent_type") or "general-purpose")
            ev["model"] = ti.get("model") if isinstance(ti.get("model"), str) and len(ti["model"]) <= 40 else None
            ev["bg"] = 1 if ti.get("run_in_background") is True else 0
        elif tool == "SendMessage":
            ev["to"] = self.aids.get(ti.get("to") or ti.get("recipient"))
        else:
            cmd = _shell(ti)
            m = MARK.match(cmd)
            if m:
                ev["mark"] = self._retag(TAG.match(m.group(1))) if TAG.match(m.group(1)) else ""
            cm = COMMIT_RE.search(cmd)   # same test as the hook's _commit_m
            ev["commit"] = 1 if cm and not DRY_RE.search(re.sub(r"\"[^\"]*\"|'[^']*'", "", cmd[cm.start():])) else 0
            if not (tag or ev["commit"] or ev.get("mark")):
                return None   # an ordinary shell call means nothing to pl_flow
        return ev

    def _post(self, pre, b, tur, t):
        txt = _text(b.get("content"))
        err = b.get("is_error") is True
        if err and _denied(txt, tur):
            pre["denied"] = 1
            return None   # a denied Pre never gets a Post hook
        if err and NOT_RUN_RE.match(txt.strip()):
            return None   # rejected/invalid before running: no Post hook either, but not a hook deny
        try:
            raw = json.dumps(tur, ensure_ascii=False) if tur is not None else ""
        except (TypeError, ValueError):
            raw = ""
        ev = dict(pre, t=t, e="post", err=1 if err else 0)
        ev["bg"] = 1 if pre["bg"] or BG_RE.search((raw + txt)[:4000]) else 0   # matched only, never stored
        if pre["tool"] in ("Agent", "Task") and isinstance(tur, dict):
            ev["to"] = self.aids.get(tur.get("agentId"))
            pre["to"] = ev["to"]
        return ev


def _span(path):
    """Timestamps of a subagent transcript (activity only, no content)."""
    return sorted(x for x in (_ts(d.get("timestamp")) for d in _lines(path)) if x is not None)


def mine(session, pipeline, subdir=None, name="pipe"):
    with open(pipeline, encoding="utf-8") as fh:
        pd = json.load(fh)
    real = {pd.get("name")} if isinstance(pd.get("name"), str) else set()
    real.add(os.path.splitext(os.path.basename(pipeline))[0])
    mn = Miner(name, real)
    pipe = mn.pipe(pd)
    evs = mn.events(session, None)
    if subdir is None:
        subdir = os.path.join(os.path.splitext(session)[0], "subagents")
    spans = {}
    for p in sorted(glob.glob(os.path.join(subdir, "agent-*.jsonl"))):
        real_id = os.path.basename(p)[len("agent-"):-len(".jsonl")]
        aid = mn.aids.get(real_id)
        evs += mn.events(p, aid)
        spans[aid] = _span(p)
    # A background dispatch is done when its agent's activity stops before the next dispatch to it.
    disp = sorted((e["t"], e["to"]) for e in evs if e["e"] == "post" and e["bg"] and e["to"])
    for i, (t0, aid) in enumerate(disp):
        nxt = min([t for t, a in disp[i + 1:] if a == aid] or [float("inf")])
        ts = [x for x in spans.get(aid, []) if t0 <= x < nxt]
        if ts:
            evs.append({"t": ts[-1], "e": "bgdone", "tool": "Agent", "tag": "", "sub": None, "model": None, "bg": 1,
                        "aid": None, "to": aid, "commit": 0, "denied": 0})
    evs.sort(key=lambda e: e["t"])
    t0 = evs[0]["t"] if evs else 0
    for e in evs:
        e["t"] = round(e["t"] - t0, 1)
    return {"v": 1, "sid": "sess-0001", "cwd": "proj", "pipe": pipe, "ev": evs, "cp": []}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("session")
    ap.add_argument("--pipeline", required=True)
    ap.add_argument("--subagents")
    ap.add_argument("--name", default="pipe")
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    if not re.match(r"^[a-z0-9-]{1,40}$", a.name):
        ap.error("--name must match [a-z0-9-]{1,40}")
    out = json.dumps(mine(a.session, a.pipeline, a.subagents, a.name), ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    else:
        sys.stdout.write(out + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
