"""«Pipelines» schema (split from sidereus/pipeline.py at the 620-line cap): `validate(P, name)` — port of the runner's
validate block (`.claude/workflows/pipeline.js`) — and `dump(P)` (hand-written file style). Pure: no I/O, no sidereus imports.
"""
import json
import re

# ⚠Must equal the runner's recommended STAGE_TITLES (without the «Custom stage N» slots) / MODELS.
# Any other title is a custom stage (1-40 chars, needs `task`, at most CUSTOM_MAX — one runner phase slot each).
STAGE_TITLES = ("설계", "구현", "검증", "리뷰", "재검증", "재현", "원인", "수정", "회귀", "트리아지", "라이브 검증", "AI 설정 점검", "프롬프트 검증")
SLOT_PREFIX = "사용자 단계"
# Renamed recommended titles (old -> new): legacy files and runs keep matching. ⚠Same map in hooks/pl_flow.py, the runner and 48c PL_RENAMED.
RENAMED = {"최종 검증": "재검증"}
CUSTOM_MAX = 12
MODELS = ("inherit", "opus", "sonnet", "haiku")
_NAME = re.compile(r"[a-z0-9-]{1,40}")      # ⚠fullmatch only: Python `$` also matches before a trailing "\n"
_AGENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}")   # built-in agent types are capitalised (Explore, Plan)
_SKILL = re.compile(r"[a-z0-9-]{1,60}")
# Gate command -> evidence mode (scripts/evidence_rec.py rows); first match wins. guards.requireGates needs a match.
# ⚠Same table in hooks/pl_guard.py and the runner's validate block; tests/test_pl_guard.py pins all three equal.
GATE_MODES = (
    ("(?:^|[\\s/])check\\.sh\\s+--fast(?![\\w-])", "fast"),
    ("(?:^|[\\s/])check\\.sh\\s+--full(?![\\w-])", "full"),
    ("arch_checks\\.py(?=.*\\s--verify(?![\\w-])).*\\s--category[\\s=]+security(?![\\w-])", "checks-security"),
)
LOOP_MAX = 10


def gate_mode(gate):
    """Evidence mode recorded by `gate`'s run, or None (ungraded)."""
    if not isinstance(gate, str):
        return None
    return next((m for p, m in GATE_MODES if re.search(p, gate)), None)


def _is_int(x, lo, hi):
    """JS Number.isInteger(x) && lo <= x <= hi (bool excluded, 2.0 counts)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    return float(x).is_integer() and lo <= x <= hi


# ⚠Mirrors the runner's validate block: JS `.length` counts UTF-16 units and `.trim()` strips its own whitespace set.
_JS_WS = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


def _ulen(x):
    return len(x.encode("utf-16-le", "surrogatepass")) // 2


def _trim(x):
    return x.strip(_JS_WS)


def _ren(t):
    return RENAMED.get(t, t) if isinstance(t, str) else t


def _one_line(x, mx):
    return isinstance(x, str) and _ulen(x) <= mx and "\r" not in x and "\n" not in x


_COLOR = re.compile(r"#[0-9a-f]{6}")     # stage.ui.color; fullmatch only


def _ui_ok(u):
    """Canvas position {x, y} + optional colour "#rrggbb" (editor only; the runner ignores it)."""
    return isinstance(u, dict) and {"x", "y"} <= set(u) <= {"x", "y", "color"} and all(
        not isinstance(u[k], bool) and isinstance(u[k], (int, float)) and abs(u[k]) <= 100000 for k in ("x", "y")) and (
        "color" not in u or (isinstance(u["color"], str) and bool(_COLOR.fullmatch(u["color"]))))


def validate(P, name):
    """Error list for pipeline dict P stored as `<name>.json` — a port of the runner's validate block."""
    if not isinstance(P, dict):
        return ["top level must be an object"]
    errs = []
    if not (_is_int(P.get("v"), 1, 1)):
        errs.append("v must be 1")
    if P.get("name") != name:
        errs.append('name must equal file stem "%s"' % name)
    if not _one_line(P.get("title"), 80) or not P.get("title"):
        errs.append("title: 1-80 chars, one line")
    if "use" in P and not (_one_line(P["use"], 120) and _trim(P["use"])):   # «when to use», read by hooks/pipelines_brief.py
        errs.append("use: one line, 1..120 chars")
    if "rules" in P and not (isinstance(P["rules"], str) and _ulen(P["rules"]) <= 2000):
        errs.append("rules: string <= 2000")
    if "after" in P and not (isinstance(P["after"], list) and all(_one_line(x, 200) for x in P["after"])):
        errs.append("after: array of one-line strings")
    if "readonly" in P and not isinstance(P["readonly"], bool):   # strict mode: a readonly run allows no edits (hooks/pl_flow.py)
        errs.append("readonly: true|false")
    if "catch" in P and P["catch"] != "person":   # bug-fix pipeline: its runs count as «Found by a person first» (harness_person)
        errs.append('catch: "person"')
    D =P.get("defaults") if isinstance(P.get("defaults"), dict) else {}
    if D.get("model") not in MODELS:
        errs.append("defaults.model: inherit|opus|sonnet|haiku")
    if not _is_int(D.get("retry"), 0, 3):
        errs.append("defaults.retry: 0..3")
    S = P["stages"] if isinstance(P.get("stages"), list) else []
    if not S or len(S) > 20:
        errs.append("stages: 1..20")

    def idx(t):
        return next((k for k, s in enumerate(S) if isinstance(s, dict) and _ren(s.get("title")) == _ren(t)), -1)   # runner renames before validating

    for i, s in enumerate(S):
        at = "stages[%d]" % i
        if not isinstance(s, dict):
            errs.append(at + ": object")
            continue
        t = s.get("title")
        if not _one_line(t, 40) or not _trim(t):
            errs.append(at + ".title: 1-40 chars, one line")
        elif t.startswith(SLOT_PREFIX):
            errs.append('%s.title "%s": «사용자 단계» names are reserved phase slots' % (at, t))
        elif _ren(t) not in STAGE_TITLES and not (isinstance(s.get("task"), str) and _trim(s["task"])):
            errs.append('%s.task: required for a custom stage "%s" (no default instruction)' % (at, t))
        if idx(s.get("title")) != i:
            errs.append(at + ".title duplicated")
        if not (isinstance(s.get("agent"), str) and _AGENT.fullmatch(s["agent"])):
            errs.append(at + ".agent: ^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$")
        if "skill" in s and not (isinstance(s["skill"], str) and _SKILL.fullmatch(s["skill"])):
            errs.append(at + ".skill: ^[a-z0-9-]{1,60}$")
        if "task" in s and not (isinstance(s["task"], str) and _ulen(s["task"]) <= 1000):
            errs.append(at + ".task: string <= 1000")
        if "model" in s and s["model"] not in MODELS:
            errs.append(at + ".model")
        if "retry" in s and not _is_int(s["retry"], 0, 3):
            errs.append(at + ".retry: 0..3")
        if "parallel" in s and not _is_int(s["parallel"], 1, 16):
            errs.append(at + ".parallel: 1..16")
        if "gate" in s and not (_one_line(s["gate"], 200) and s["gate"]):
            errs.append(at + ".gate: one line, 1..200 chars")
        if "produces" in s and s["produces"] != "slices":
            errs.append(at + '.produces: "slices"')
        if "fanout" in s:
            if s["fanout"] != "slices":
                errs.append(at + '.fanout: "slices"')
            elif not any(isinstance(t, dict) and t.get("produces") == "slices" for t in S[:i]):
                errs.append(at + '.fanout needs an earlier stage with produces:"slices"')
        if "onError" in s and s["onError"] not in ("stop", "continue"):
            errs.append(at + ".onError: stop|continue")
        if "onlyOnJump" in s and not isinstance(s["onlyOnJump"], bool):
            errs.append(at + ".onlyOnJump: boolean")
        if "ui" in s and not _ui_ok(s["ui"]):
            errs.append(at + ".ui: {x, y} numbers")
        if "onFail" in s:
            f = s["onFail"] if isinstance(s["onFail"], dict) else {}
            g = idx(f.get("goto"))
            if g < 0 or g >= i:
                errs.append(at + ".onFail.goto must name an earlier stage")
            if not _is_int(f.get("max"), 1, 5):
                errs.append(at + ".onFail.max: 1..5")
            if "then" in f and idx(f["then"]) <= i:
                errs.append(at + ".onFail.then must name a later stage")
            if "stopOn" in f and not (isinstance(f["stopOn"], list) and all(x == "unrelated" for x in f["stopOn"])):
                errs.append(at + '.onFail.stopOn: [] or ["unrelated"]')
    if "guards" in P:
        G = P["guards"] if isinstance(P["guards"], dict) else None
        if G is None or not set(G) <= {"requireGates", "maxLoopBacks"}:
            errs.append("guards: object with requireGates and/or maxLoopBacks")
        else:
            rq = G.get("requireGates", [])
            if not (isinstance(rq, list) and all(isinstance(t, str) for t in rq)):
                errs.append("guards.requireGates: array of stage titles")
            else:
                for t in rq:
                    k = idx(t)
                    if k < 0:
                        errs.append('guards.requireGates: no stage "%s"' % t)
                    elif not gate_mode(S[k].get("gate")):
                        errs.append('guards.requireGates: stage "%s" has no graded gate (check.sh --fast|--full, arch_checks.py --verify)' % t)
            if "maxLoopBacks" in G and not _is_int(G["maxLoopBacks"], 1, LOOP_MAX):
                errs.append("guards.maxLoopBacks: 1..%d" % LOOP_MAX)
    if S and isinstance(S[0], dict) and S[0].get("onlyOnJump"):
        errs.append("stages[0] cannot be onlyOnJump")
    if sum(1 for s in S if isinstance(s, dict) and _ren(s.get("title")) not in STAGE_TITLES) > CUSTOM_MAX:
        errs.append("at most %d custom stages (phase slots)" % CUSTOM_MAX)
    return errs


def _inline(v):
    """One-line JSON in the hand-written style: `{ "k": v }` for objects, compact `[...]` for arrays."""
    if isinstance(v, dict):
        return "{ " + ", ".join(json.dumps(k, ensure_ascii=False) + ": " + _inline(x) for k, x in v.items()) + " }" if v else "{}"
    if isinstance(v, list):
        return "[" + ", ".join(_inline(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def dump(P):
    """Serialize in the style of the shipped pipeline files, so an agent/model edit diffs as one or two lines.
    Top level and each stage one key per line; `after` one item per line; other nested values inline."""
    def block(d, ind):
        pad = " " * ind
        rows = []
        for k, v in d.items():
            key = pad + json.dumps(k, ensure_ascii=False) + ": "
            if ind == 2 and k == "stages" and isinstance(v, list) and all(isinstance(s, dict) for s in v) and v:
                rows.append(key + "[\n" + ",\n".join(pad + "  " + block(s, ind + 4) for s in v) + "\n" + pad + "]")
            elif ind == 2 and isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                rows.append(key + "[\n" + ",\n".join(pad + "  " + json.dumps(x, ensure_ascii=False) for x in v) + "\n" + pad + "]")
            else:
                rows.append(key + _inline(v))
        return "{\n" + ",\n".join(rows) + "\n" + " " * (ind - 2) + "}"
    return block(P, 2) + "\n"
