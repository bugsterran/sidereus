"""«Stage catalog» for the pipeline canvas: stage templates read from sidereus/stage_catalog.json, each validated as a stage
(pipeline_schema.validate on a one-stage pipeline), plus tool availability by `shutil.which` only (nothing is run).
GET /api/pipelines returns `catalog()`. Templates are config text written in this repo, not conversation (rule 1).
"""
import json
import os
import re
import shlex
import shutil

from sidereus import config
from sidereus.config import CODE_DIR
from sidereus.pipeline_schema import MODELS, validate

CAT_FILE = os.path.join(CODE_DIR, "sidereus", "stage_catalog.json")
GROUPS = ("understand", "research", "design", "build", "test", "quality", "security", "consistency", "verify", "review", "release", "ops")
ROLES = ("triage", "design", "fix", "build", "check", "review", "live", "probe", "ux")   # = sidereus/pipeline.py _ROLES keys
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_BIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,59}")
_TITLE_BAD = re.compile(r"[/\]|\r\n\x00-\x1f]")   # same rule as pipeline.title_err (tag and shell marker safe)
_which = shutil.which                             # ⚠tests patch this; availability never runs the tool


def _line(x, mx, empty=True):
    return isinstance(x, str) and len(x) <= mx and "\n" not in x and "\r" not in x and (empty or bool(x.strip()))


def _subst(s, sidereus):
    return s.replace("{sidereus}", sidereus) if isinstance(s, str) else s


def stage_of(t, sidereus="/sidereus"):
    """Template -> the stage it adds (agent = the role's fallback; the page resolves roles to project agents)."""
    s = {"title": t["title"]["ko"], "agent": t.get("agent") or "general-purpose"}
    for k in ("model", "task", "gate"):
        if t.get(k):
            s[k] = _subst(t[k], sidereus)
    return s


def errors(t, sidereus="/sidereus"):
    """Why template `t` is not usable ([] = ok). The stage it adds must pass the runner schema as-is."""
    if not isinstance(t, dict):
        return ["template: object"]
    e = []
    if not (isinstance(t.get("id"), str) and _ID.fullmatch(t["id"])):
        e.append("id")
    if t.get("group") not in GROUPS:
        e.append("group")
    ti = t.get("title")
    if not (isinstance(ti, dict) and _line(ti.get("ko"), 24, False) and _line(ti.get("en"), 40, False)) or _TITLE_BAD.search(ti["ko"]):
        return e + ["title"]
    if "role" in t and t["role"] not in ROLES:
        e.append("role")
    if "agent" in t and "role" in t:
        e.append("agent|role: one of them")
    if "model" in t and t["model"] not in MODELS:
        e.append("model")
    if not _line(t.get("gate"), 200) or not _line(t.get("gateHint"), 160) or not _line(t.get("asserts"), 200):
        e.append("gate/gateHint/asserts: one line")
    lp = t.get("loop")
    if lp is not None and not (isinstance(lp, dict) and set(lp) == {"to", "max"} and isinstance(lp["to"], list)
                               and all(_line(x, 40, False) for x in lp["to"]) and isinstance(lp["max"], int) and 1 <= lp["max"] <= 5):
        e.append("loop")
    tools = t.get("tools")
    if not isinstance(tools, list) or not all(
            isinstance(x, dict) and set(x) == {"id", "bin", "install", "net"} and _ID.fullmatch(str(x["id"])) and _BIN.fullmatch(str(x["bin"]))
            and _line(x["install"], 120, False) and isinstance(x["net"], bool) for x in tools):
        e.append("tools")
    P = {"v": 1, "name": "catalog", "title": "catalog", "defaults": {"model": "inherit", "retry": 0}, "stages": [stage_of(t, sidereus)]}
    return e + ["stage: " + x for x in validate(P, "catalog")]


def load():
    """{groups, templates} from CAT_FILE; empty on a read/parse error."""
    try:
        with open(CAT_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"groups": [], "templates": []}
    if not isinstance(d, dict):
        return {"groups": [], "templates": []}
    gs = [g for g in d.get("groups") or [] if isinstance(g, dict) and g.get("id") in GROUPS and _line(g.get("en"), 30, False)]
    return {"groups": gs, "templates": [t for t in d.get("templates") or [] if isinstance(t, dict)]}


def catalog():
    """Body `catalog` of GET /api/pipelines: valid templates only, `{sidereus}` = this repo path (shell-quoted), `instr` for task
    (page code never reads a `task` key), each tool with `avail`. ⚠A template whose filled-in gate breaks the schema is dropped."""
    d, sidereus = load(), shlex.quote(CODE_DIR)
    items, seen = [], set()
    for t in d["templates"]:
        if errors(t, sidereus) or t["id"] in seen or t["title"]["ko"] in seen:
            continue
        if not config.IS_CLONE and any("{sidereus}" in str(t.get(k) or "") for k in ("gate", "task")):
            continue   # pipx/uv install: {sidereus}/scripts and .claude/ are not shipped, so the gate would fail
        seen.update((t["id"], t["title"]["ko"]))
        it = {k: t[k] for k in ("id", "group", "title", "role", "agent", "model", "gateHint", "asserts", "loop") if k in t}
        it["gate"] = _subst(t["gate"], sidereus)
        if t.get("task"):
            it["instr"] = _subst(t["task"], sidereus)
        it["tools"] = [dict(x, avail=bool(_which(x["bin"]))) for x in t["tools"]]
        items.append(it)
    return {"groups": d["groups"], "items": items}
