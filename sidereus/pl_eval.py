"""Pipeline evaluation: do a pipeline's stages catch known defects (seeds), do their gates go red on a broken repo
(red check), and are their gate results stable (flaky)?

Store under DATA_DIR/eval/ — never the target repo:
  <key>/seeds.json            {v:1, seeds:[{id, kind, file, line?, rule?, pkg?, expectStage, holdout?}]} (0600)
  <key>/<commit>/eval.json    {v:1, repo, commit, pipeline, at, stages:[{title, n, caught, missed:[ids]}], holdout:{n, caught}}
  redcheck.json               {v:1, gates:{sha1(gate)[:16]: {pipeline, stage, mode, key, verdict, why, at, ms}}}
key = arch_verify.repo_key. ⚠Holdout seed ids never leave seeds.json: eval.json, output and API carry counts only.
Metadata only (seed ids, file:line, rule ids, counts). No subprocess here: scripts/pl_eval.py runs the clones.
"""
import hashlib
import json
import os
import re

from sidereus import config
from sidereus import arch_verify as AV
from sidereus import stage_catalog
from sidereus.bus import _atomic_write
from sidereus.pipeline_schema import gate_mode

EVAL_DIR = os.path.join(config.DATA_DIR, "eval")
EVAL_EV_FILE = os.path.join(config.DATA_DIR, "evidence.jsonl")   # same file scripts/check.sh appends to
EVAL_EV_READ_MAX = 512 * 1024
EVAL_FLAKY_DAYS = 14
EVAL_LINE_K = 2              # a finding within line ±K of the seed counts (tools and agents report nearby lines)
EVAL_SEEDS_MAX = 500
EVAL_RED_MAX = 200           # redcheck.json entries kept (newest by `at`)
SEED_KINDS = ("secret", "dep", "sast", "logic")
KIND_TOOLS = {"secret": ("gitleaks",), "dep": ("npm-audit", "osv-scanner"),
              "sast": ("semgrep", "bandit"), "logic": ()}   # logic seeds match --findings only
CHECKS_FILES = {"checks-security": "checks-security.json"}
VERDICTS = ("pass", "fail", "skip")
SEED_ID = re.compile(r"[a-z0-9-]{1,40}")
_RULE = re.compile(r"[A-Za-z0-9_./@:-]{1,60}")     # = arch_checks.RULE_RE
_PKG = re.compile(r"[A-Za-z0-9@/._+:-]{1,100}")    # = sec_checks.PKG_RE
_KEY = re.compile(r"[0-9a-f]{16}")
_SEED_KEYS = {"id", "kind", "file", "line", "rule", "pkg", "expectStage", "holdout"}


def _nat(x, lo=0):
    return isinstance(x, int) and not isinstance(x, bool) and x >= lo


def _line(x, mx):
    return isinstance(x, str) and 0 < len(x.strip()) and len(x) <= mx and not any(ord(c) < 32 for c in x)


def seed_errors(d):
    """Why a seeds.json dict is unusable ([] = ok). Unknown keys are refused so no text rides along."""
    if not isinstance(d, dict) or set(d) != {"v", "seeds"} or d.get("v") != 1 or not isinstance(d.get("seeds"), list):
        return ["top level: {v:1, seeds:[...]}"]
    if len(d["seeds"]) > EVAL_SEEDS_MAX:
        return ["seeds: at most %d" % EVAL_SEEDS_MAX]
    e, seen = [], set()
    for i, s in enumerate(d["seeds"]):
        at = "seeds[%d]" % i
        if not isinstance(s, dict) or set(s) - _SEED_KEYS:
            e.append(at + ": keys")
            continue
        if not (isinstance(s.get("id"), str) and SEED_ID.fullmatch(s["id"])) or s["id"] in seen:
            e.append(at + ".id")
        seen.add(s.get("id"))
        if s.get("kind") not in SEED_KINDS:
            e.append(at + ".kind: " + "|".join(SEED_KINDS))
        if AV.safe_rel(s.get("file")) != s.get("file"):
            e.append(at + ".file: repo-relative path")
        if "line" in s and not _nat(s["line"], 1):
            e.append(at + ".line")
        if "rule" in s and not (isinstance(s["rule"], str) and _RULE.fullmatch(s["rule"])):
            e.append(at + ".rule")
        if "pkg" in s and not (isinstance(s["pkg"], str) and _PKG.fullmatch(s["pkg"])):
            e.append(at + ".pkg")
        if not _line(s.get("expectStage"), 40):
            e.append(at + ".expectStage")
        if "holdout" in s and not isinstance(s["holdout"], bool):
            e.append(at + ".holdout")
    return e


def counts(d):
    """{n, public, holdout} of a valid seeds dict (what the CLI prints — never ids)."""
    h = sum(1 for s in d["seeds"] if s.get("holdout"))
    return {"n": len(d["seeds"]), "public": len(d["seeds"]) - h, "holdout": h}


def _dir(repo_key, commit=None):
    if not (isinstance(repo_key, str) and _KEY.fullmatch(repo_key)):
        raise ValueError("repo key")
    if commit is None:
        return os.path.join(EVAL_DIR, repo_key)
    if not (isinstance(commit, str) and AV.COMMIT_RE.fullmatch(commit)):
        raise ValueError("commit must be a full hex id")
    return os.path.join(EVAL_DIR, repo_key, commit)


def _read(fp):
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _dump(fp, obj, mode):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    _atomic_write(fp, (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
                  prefix=".eval-", mode=mode)


def save_seeds(repo, d):
    """Validated seeds -> eval/<key>/seeds.json (0600: holdout ids live only here). ValueError on invalid."""
    errs = seed_errors(d)
    if errs:
        raise ValueError("; ".join(errs[:5]))
    _dump(os.path.join(_dir(AV.repo_key(repo)), "seeds.json"), d, 0o600)


def load_seeds(repo):
    """Stored seeds dict of repo, None when missing or invalid. ⚠Contains holdout ids: CLI-internal only."""
    d = _read(os.path.join(_dir(AV.repo_key(repo)), "seeds.json"))
    return d if d is not None and not seed_errors(d) else None


# ── matching ──

def stage_index(expect, stages, templates=None):
    """Index of the pipeline stage a seed's expectStage names, or None. Resolution: the stage title itself, else a
    catalog template (id or title.ko) -> its title, else the first stage whose gate has that template's gate mode."""
    titles = [s.get("title") if isinstance(s, dict) else None for s in stages]
    if expect in titles:
        return titles.index(expect)
    ts = stage_catalog.load()["templates"] if templates is None else templates
    t = next((t for t in ts if isinstance(t, dict) and (t.get("id") == expect or (t.get("title") or {}).get("ko") == expect)),
             None)
    if t is None:
        return None
    ko = (t.get("title") or {}).get("ko")
    if ko in titles:
        return titles.index(ko)
    m = gate_mode(t.get("gate") or "")
    if m is None:
        return None
    return next((i for i, s in enumerate(stages) if isinstance(s, dict) and gate_mode(s.get("gate") or "") == m), None)


def _clean(x, tool_ok):
    """{tool, file, line, rule, pkg} of one finding, None if malformed. Findings without a tool get tool ""."""
    if not isinstance(x, dict):
        return None
    f, ln, r, pk, tool = x.get("file"), x.get("line"), x.get("rule"), x.get("pkg"), x.get("tool", "")
    if AV.safe_rel(f) != f or not _nat(ln) or (r is not None and not (isinstance(r, str) and _RULE.fullmatch(r))):
        return None
    if pk is not None and not (isinstance(pk, str) and _PKG.fullmatch(pk)):
        return None
    if not tool_ok(tool):
        return None
    return {"tool": tool, "file": f, "line": ln, "rule": r, "pkg": pk}


def clean_findings(xs):
    """Agent/extra findings [{file, line, rule?}] (tool-less), malformed ones dropped."""
    return [c for c in (_clean(x, lambda t: t == "") for x in (xs if isinstance(xs, list) else [])) if c]


def checks_items(repo, commit, mode):
    """Findings of a checks-* gate mode from the arch store (HEAD commit dir); [] when absent or another mode."""
    fn = CHECKS_FILES.get(mode)
    if not fn:
        return []
    try:
        j = AV.read_json(os.path.join(AV.store_dir(repo, commit), fn))
    except (OSError, ValueError):
        return []
    its = j.get("items") if isinstance(j, dict) else None
    return [c for c in (_clean(x, lambda t: isinstance(t, str) and t != "") for x in (its if isinstance(its, list) else []))
            if c]


def _rule_key(seed, r):
    """Rule id as compared: sast keeps a dotted semgrep id's own name (as sec_checks._it shortens long ones)."""
    return r.rsplit(".", 1)[-1] if seed.get("kind") == "sast" and isinstance(r, str) else r


def matches(seed, item):
    """Seed caught by this finding: kind -> tool (logic: tool-less findings), same file, same rule/pkg, line ±K."""
    tools = KIND_TOOLS.get(seed.get("kind"))
    if tools is None or (item["tool"] not in tools if tools else item["tool"] != ""):
        return False
    # An advisory belongs to the package: npm audit reports the lockfile even when the seed names package.json
    if seed.get("kind") != "dep" and item["file"] != seed.get("file"):
        return False
    if "rule" in seed and _rule_key(seed, item["rule"]) != _rule_key(seed, seed["rule"]):
        return False
    if "pkg" in seed and item["pkg"] != seed["pkg"]:
        return False
    return "line" not in seed or abs(item["line"] - seed["line"]) <= EVAL_LINE_K


def score(seeds, stages, items_of, extra=(), templates=None):
    """(stages [{title, n, caught, missed}], holdout {n, caught}, unresolved count). items_of(i) = findings of stage i.
    ⚠Holdout seeds count only in `holdout`; `missed` lists public ids only. Unresolved seeds count as missed."""
    out = [{"title": s.get("title") if isinstance(s, dict) else "", "n": 0, "caught": 0, "missed": []} for s in stages]
    hold, unres, cache = {"n": 0, "caught": 0}, 0, {}
    for s in seeds:
        i = stage_index(s["expectStage"], stages, templates)
        if i is not None and i not in cache:
            cache[i] = list(items_of(i)) + list(extra)
        hit = i is not None and any(matches(s, x) for x in cache[i])
        if s.get("holdout"):
            hold["n"] += 1
            hold["caught"] += int(hit)
        elif i is None:
            unres += 1
        else:
            out[i]["n"] += 1
            out[i]["caught"] += int(hit)
            if not hit:
                out[i]["missed"].append(s["id"])
    return out, hold, unres


def save_eval(repo, commit, pipeline, at, stages, hold):
    d = {"v": 1, "repo": os.path.realpath(repo), "commit": commit, "pipeline": pipeline, "at": at,
         "stages": stages, "holdout": hold}
    _dump(os.path.join(_dir(AV.repo_key(repo), commit), "eval.json"), d, 0o600)
    return d


def load_eval(repo_key, commit):
    """eval.json of (repo key, commit) with whitelisted fields, None when missing/invalid. Counts and public ids only."""
    try:
        j = _read(os.path.join(_dir(repo_key, commit), "eval.json"))
    except ValueError:
        return None
    if not isinstance(j, dict) or j.get("v") != 1 or not isinstance(j.get("stages"), list):
        return None
    st = []
    for s in j["stages"]:
        if isinstance(s, dict) and isinstance(s.get("title"), str) and _nat(s.get("n")) and _nat(s.get("caught")):
            ms = [x for x in s.get("missed") or [] if isinstance(x, str) and SEED_ID.fullmatch(x)]
            st.append({"title": s["title"], "n": s["n"], "caught": s["caught"], "missed": ms})
    h = j.get("holdout") if isinstance(j.get("holdout"), dict) else {}
    return {"commit": commit, "pipeline": j.get("pipeline") if isinstance(j.get("pipeline"), str) else "",
            "at": j.get("at") if isinstance(j.get("at"), (int, float)) and not isinstance(j.get("at"), bool) else 0,
            "stages": st, "holdout": {"n": h.get("n") if _nat(h.get("n")) else 0,
                                      "caught": h.get("caught") if _nat(h.get("caught")) else 0}}


# ── evidence rows ──

def eval_row(repo, head, stages, ts):
    """Evidence row kind "eval" (readers keyed on kind "check" ignore it). rc 0 only if every public seed was caught."""
    steps = [{"name": "s%d" % i, "rc": 0 if not s["missed"] else 1, "n": s["n"], "failed": len(s["missed"]), "secs": 0}
             for i, s in enumerate(stages) if s["n"]]
    return {"v": 1, "kind": "eval", "ts": int(ts), "mode": "eval-catch", "repo": os.path.realpath(repo), "head": head,
            "dirty": False, "rc": 0 if all(s["rc"] == 0 for s in steps) else 1, "steps": steps}


def red_row(repo, head, mode, verdict, ts):
    rc = {"pass": 0, "fail": 1}.get(verdict, 2)   # skip = 2: never reads as a pass
    return {"v": 1, "kind": "red", "ts": int(ts), "mode": "redcheck", "repo": os.path.realpath(repo), "head": head,
            "dirty": False, "rc": rc, "steps": [{"name": mode, "rc": rc, "n": 1, "failed": int(rc != 0), "secs": 0}]}


# ── red check store ──

def gate_key(gate):
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- persisted ledger key, not a security use
    return hashlib.sha1(gate.encode("utf-8", "surrogateescape"), usedforsecurity=False).hexdigest()[:16]


def _red_file():
    return os.path.join(EVAL_DIR, "redcheck.json")


def _red_gates():
    j = _read(_red_file())
    g = j.get("gates") if isinstance(j, dict) and j.get("v") == 1 else None
    return g if isinstance(g, dict) else {}


def save_red(gate, entry):
    """Record one red-check verdict under sha1(gate)[:16]; keeps the newest EVAL_RED_MAX."""
    if entry.get("verdict") not in VERDICTS:
        raise ValueError("verdict")
    g = _red_gates()
    g[gate_key(gate)] = entry
    keep = sorted(g.items(), key=lambda kv: -(kv[1].get("at") or 0) if isinstance(kv[1], dict) else 0)[:EVAL_RED_MAX]
    _dump(_red_file(), {"v": 1, "gates": dict(keep)}, 0o644)


def redcheck_status(pipeline_name, stages):
    """{stage title: {verdict, why, at, mode}} for stages whose gate has a red-check entry (keyed by gate text, so the
    same gate in another pipeline shares it; pipeline_name is kept for callers that filter by the recording pipeline)."""
    g, out = _red_gates(), {}
    for s in stages or []:
        if not (isinstance(s, dict) and isinstance(s.get("gate"), str) and s["gate"].strip()):
            continue
        e = g.get(gate_key(s["gate"]))
        if isinstance(e, dict) and e.get("verdict") in VERDICTS:
            out[s.get("title")] = {"verdict": e["verdict"], "why": e.get("why") if isinstance(e.get("why"), str) else "",
                                   "at": e.get("at") if isinstance(e.get("at"), (int, float)) else 0,
                                   "mode": e.get("mode") if isinstance(e.get("mode"), str) else "",
                                   "same": e.get("pipeline") == pipeline_name}
    return out


# ── flaky gates ──

def flaky(rows, now, days=EVAL_FLAKY_DAYS):
    """Gate modes that both passed and failed on the same clean commit of the same repo within `days` (sorted)."""
    seen, out = {}, set()
    for d in rows:
        if not isinstance(d, dict) or d.get("kind") != "check" or d.get("dirty") is not False:
            continue
        ts, rc = d.get("ts"), d.get("rc")
        if not isinstance(ts, (int, float)) or ts < now - days * 86400 or not isinstance(rc, int) or isinstance(rc, bool):
            continue
        if not d.get("head") or not isinstance(d.get("mode"), str):
            continue
        k = (d.get("repo"), d["mode"], d["head"])
        seen.setdefault(k, set()).add(rc == 0)
        if len(seen[k]) == 2:
            out.add(d["mode"])
    return sorted(out)


def _ev_rows():
    try:
        with open(EVAL_EV_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - EVAL_EV_READ_MAX))
            lines = f.read(EVAL_EV_READ_MAX).split(b"\n")
    except OSError:
        return []
    if size > EVAL_EV_READ_MAX:
        lines = lines[1:]   # ⚠first line of a mid-file seek is partial
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln.decode("utf-8")))
        except ValueError:
            continue
    return out


def flaky_modes(repo_root, now):
    """flaky() over the evidence tail of one repo (realpath match)."""
    root = os.path.realpath(repo_root)
    return flaky([d for d in _ev_rows() if isinstance(d, dict) and d.get("repo") == root], now)


def agreement(rows, now, head, days=EVAL_FLAKY_DAYS):
    """{mode: (k, n)} — n clean runs of each gate mode at `head` (else the commit of its newest row) and k that match the
    majority verdict. Same row filter as flaky(), so k < n here implies the mode is in flaky()."""
    by = {}
    for d in rows:
        if not isinstance(d, dict) or d.get("kind") != "check" or d.get("dirty") is not False:
            continue
        ts, rc = d.get("ts"), d.get("rc")
        if not isinstance(ts, (int, float)) or ts < now - days * 86400 or not isinstance(rc, int) or isinstance(rc, bool):
            continue
        if not d.get("head") or not isinstance(d.get("mode"), str):
            continue
        by.setdefault(d["mode"], []).append((ts, d["head"], rc == 0))
    out = {}
    same = lambda a, b: isinstance(a, str) and isinstance(b, str) and len(min(a, b, key=len)) >= 4 and (a.startswith(b) or b.startswith(a))
    for mode, rs in by.items():   # ⚠check.sh records `rev-parse --short` while callers pass a full sha: match by prefix
        h = head if head and any(same(r[1], head) for r in rs) else max(rs, key=lambda r: r[0])[1]
        ok = [r[2] for r in rs if same(r[1], h)]
        out[mode] = (max(ok.count(True), ok.count(False)), len(ok))
    return out


def gate_agreement(pipeline_obj, repo_root, now, head):
    """{stage title: {k, n}} for gated stages whose gate mode has evidence rows in this repo (counts only)."""
    root = os.path.realpath(repo_root)
    ag = agreement([d for d in _ev_rows() if isinstance(d, dict) and d.get("repo") == root], now, head)
    out = {}
    for s in (pipeline_obj or {}).get("stages") or []:
        g = s.get("gate") if isinstance(s, dict) and isinstance(s.get("gate"), str) else ""
        m = gate_mode(g) if g.strip() else None
        if m in ag and isinstance(s.get("title"), str):
            out[s["title"]] = {"k": ag[m][0], "n": ag[m][1]}
    return out


def graded_summary(pipeline_obj, repo_root, now):
    """{n graded, m stages, unred: [titles with a gate but no red-check pass], unstable: [titles whose gate mode is
    flaky]}. Graded = has a gate AND red check passed AND its mode is not unstable."""
    stages = [s for s in (pipeline_obj or {}).get("stages") or [] if isinstance(s, dict)]
    red = redcheck_status((pipeline_obj or {}).get("name"), stages)
    bad = set(flaky_modes(repo_root, now)) if repo_root else set()
    n, unred, unstable = 0, [], []
    for s in stages:
        g = s.get("gate") if isinstance(s.get("gate"), str) else ""
        if not g.strip():
            continue
        ok_red = (red.get(s.get("title")) or {}).get("verdict") == "pass"
        shaky = gate_mode(g) in bad
        if not ok_red:
            unred.append(s.get("title"))
        if shaky:
            unstable.append(s.get("title"))
        n += int(ok_red and not shaky)
    return {"n": n, "m": len(stages), "unred": unred, "unstable": unstable}
