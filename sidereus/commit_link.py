"""Commit -> Claude session link: which session/agent made each commit and what it cost (branch tab)."""
import glob
import json
import os
import re
import threading
import time
import zlib
from sidereus.config import DATA_DIR
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.transcript import CLAUDE_PROJECTS, _line_ts
from sidereus.agents import sub_paths, sub_sess_dir
from sidereus.claude_roots import projects_dirs
from sidereus.ident import _proj_name
from sidereus.gitinfo import _git_root, _git_run, _wt_main
from sidereus.usage_index import _req_cost
from sidereus.git import _branch_ok


# Each branch-tab commit row shows the session/agent that made it and what it cost.
# ⚠Metadata only (sha · sid · agent type · project · tokens · $) — commands and outputs are parsed here, never returned.
# ⚠Cost is an ATTRIBUTION ESTIMATE: all tokens of that transcript file between its previous commit in the same repo
#   (or file start) and this commit's tool_result. A session that also did unrelated work charges it to the next commit.
#   Priced with usage_index._req_cost (tier + 1h cache TTL) and deduped by message.id+requestId like the usage index (per-request, not hour buckets).
# ★`git commit -q` prints no `[branch sha]` (measured 2026-09-24: every orchestrator commit in this repo used -q),
#   so a commit without a sha in the output is kept by subject and matched later to `git log` by subject + time.
CL_ROOT = CLAUDE_PROJECTS
CL_INDEX = os.path.join(DATA_DIR, "commit-links.json")
CL_DAYS = 30            # transcripts older than this are not scanned; links older than this are not returned
CL_TTL = 20             # incremental refresh at most this often
CL_KEYS = 16            # per-file dedup window (usage index measured 99.73% of duplicates on the very next line)
CL_PEND = 50            # pending commit tool_uses kept per file while waiting for their tool_result
CL_CMD = 4000           # command prefix kept while pending (enough for -C/cd and the message)
CL_CM_MAX = 500         # records kept per file
CL_MATCH_S = 900        # subject fallback: tool_result may come up to this long after the commit time
CL_LOG_N = 200          # git log depth for the subject fallback
CL_CHUNK = 32 << 20     # ⚠ bytes scanned per lock hold; a 1 GB rescan continues in the background, not in the request
CL_SAVE_S = 300         # offset-only progress is flushed at most this often (new records/files flush at once)
_cl = {"files": {}, "at": 0.0, "loaded": False, "busy": False, "more": False, "saved": 0.0}
_cl_lock = threading.Lock()
_cl_git = {}            # repo -> (at, [(sha, ct, subject)])

_GIT_COMMIT_RE = re.compile(
    r"""\bgit((?:\s+(?:-C\s+(?:"[^"]*"|'[^']*'|[^\s;&|]+)|-c\s+\S+|--[\w-]+(?:=\S+)?))*)\s+commit\b""")
_C_RE = re.compile(r"""-C\s+("[^"]*"|'[^']*'|[^\s;&|]+)""")
_CD_RE = re.compile(r"""(?:^|[;&|(\n])\s*cd\s+("[^"]*"|'[^']*'|[^\s;&|)]+)""")
_OUT_RE = re.compile(r"^\[([^\]\n]+?) ([0-9a-f]{7,40})\] ?(.*)$", re.M)
_HEREDOC_RE = re.compile(r"""<<-?\s*(['"]?)(\w+)\1[^\n]*\n(.*?)(?:\n\s*\2\s*(?:\n|$)|$)""", re.S)
_MSG_RE = re.compile(r"""(?:^|\s)(?:-[a-zA-Z]*m|--message)(?:\s+|=)("(?:[^"\\]|\\.)*"|'[^']*'|[^\s;&|]+)""")
_SHA_RE = re.compile(r"^[0-9a-f]{4,40}$")
_NOTHING = ("nothing to commit", "no changes added to commit", "nothing added to commit")


def _unq(s):
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1]
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return re.sub(r'\\(["\\$`])', r"\1", s[1:-1])
    return s


def _abs(p, cwd):
    p = os.path.expanduser(_unq(p))
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd or "/", p))


def _subject(rest):
    """First line of the commit message in the command after `commit` ('' if none)."""
    hd = _HEREDOC_RE.search(rest)
    if hd and re.search(r"(?:-F\s*-|--file[=\s]-|\$\(cat)", rest[:hd.start() + 2]):
        body = hd.group(3)
    else:
        m = _MSG_RE.search(rest)
        if not m:
            return ""
        body = _unq(m.group(1))
    for ln in body.split("\n"):
        if ln.strip():
            return ln.strip()[:200]
    return ""


def _main_checkout_of(d):
    """Main checkout path for a dir (worktrees fold into their main repo), realpath'd."""
    if not d:
        return ""
    root = _git_root(d) or ""
    k = (_wt_main(root) or root) if root else d
    i = k.find("/.claude/worktrees/")
    if i > 0:
        k = k[:i]                    # deleted worktree: fall back to the path shape
    try:
        return os.path.realpath(k)
    except (OSError, ValueError):
        return k                     # NUL byte / unresolvable path: the raw key still groups


def _tool_text(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(str(b.get("text") or "") for b in c if isinstance(b, dict))
    return ""


def _cl_records(cmd, cwd, out, err, ts):
    """Commit records from one Bash call: [{sha, subj, ts, dir, rk}] (sha '' = match by subject later)."""
    m = _GIT_COMMIT_RE.search(cmd or "")
    if not m:
        return []
    c = _C_RE.search(m.group(1) or "")
    if c:
        d = _abs(c.group(1), cwd)
    else:
        cds = list(_CD_RE.finditer(cmd[:m.start()]))
        d = _abs(cds[-1].group(1), cwd) if cds else (cwd or "")
    rk = _main_checkout_of(d)
    hits = _OUT_RE.findall(out or "")
    if hits:
        return [{"sha": s[:7], "subj": sj.strip()[:200], "ts": ts, "dir": d, "rk": rk} for _b, s, sj in hits]
    low = (out or "").lower()
    if err or any(x in low for x in _NOTHING):
        return []
    sj = _subject(cmd[m.end():])
    return [{"sha": "", "subj": sj, "ts": ts, "dir": d, "rk": rk}] if sj else []


def _cl_new(fp):
    ent = {"off": 0, "sz": -1, "mt": 0.0, "tok": 0, "usd": 0.0, "cwd": "", "scwd": "",
           "keys": [], "pend": {}, "last": {}, "cm": []}
    sub = os.sep + "subagents" + os.sep in fp
    if sub:
        ent["sid"] = os.path.basename(sub_sess_dir(fp))   # plain or Workflow-tool agent (one level deeper)
        try:
            with open(fp[:-6] + ".meta.json", encoding="utf-8") as f:
                mt = json.load(f) or {}
            ent["agent"] = str(mt.get("agentType") or "agent")[:60]
            ent["tuid"] = str(mt.get("toolUseId") or "")[:80]
        except Exception:
            ent["agent"], ent["tuid"] = "agent", ""
    else:
        ent["sid"] = os.path.basename(fp)[:-6]
        ent["agent"], ent["tuid"] = "", ""
    return ent


def _cl_key(mid, rid):
    # 8-hex crc of message.id|requestId: the old full strings were half of commit-links.json (1.0 of 2.0 MB)
    return "%08x" % (zlib.crc32((mid + "|" + rid).encode("utf-8")) & 0xffffffff)


def _cl_scan(fp, ent, limit=0):
    """Read only the appended tail of one transcript (at most `limit` bytes when > 0; the rest on the next call).
    Returns bytes read. Shrunk file -> rescan from 0."""
    st = os.stat(fp)
    off = int(ent.get("off") or 0)
    if st.st_size < off:
        ent.update({k: v for k, v in _cl_new(fp).items() if k not in ("sid", "agent", "tuid")})
        off = 0
    keys, pend, last, cm = ent["keys"], ent["pend"], ent["last"], ent["cm"]
    tok, usd, cwd = int(ent.get("tok") or 0), float(ent.get("usd") or 0.0), ent.get("cwd") or ""
    end, cut = off, False
    with open(fp, "rb") as f:
        f.seek(off)
        while True:
            if limit and end - off >= limit:
                cut = True
                break
            raw = f.readline()
            if not raw or not raw.endswith(b"\n"):
                break                                    # tail still being written — next refresh
            end += len(raw)
            if not (b'"usage"' in raw or (pend and b'tool_result' in raw) or (not ent.get("scwd") and b'"cwd"' in raw)):
                continue
            try:
                e = json.loads(raw)
            except Exception:
                continue
            if not isinstance(e, dict):
                continue
            if e.get("cwd"):
                cwd = e["cwd"]
                if not ent.get("scwd"):
                    ent["scwd"] = cwd
            m = e.get("message")
            if not isinstance(m, dict):
                continue
            u = m.get("usage")
            if isinstance(u, dict):
                mid, rid = m.get("id") or "", e.get("requestId") or ""
                key = _cl_key(mid, rid) if mid and rid else ""
                if not key or key not in keys:
                    if key:
                        keys.append(key)
                        del keys[:-CL_KEYS]
                    t, c = _req_cost(m.get("model"), u)
                    tok += t
                    usd += c
            body = m.get("content")
            if not isinstance(body, list):
                continue
            for b in body:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") == "Bash":
                    cmd = (b.get("input") or {}).get("command")
                    if isinstance(cmd, str) and _GIT_COMMIT_RE.search(cmd) and b.get("id"):
                        pend[b["id"]] = [cmd[:CL_CMD], cwd]
                        while len(pend) > CL_PEND:
                            pend.pop(next(iter(pend)))
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in pend:
                    cmd, c0 = pend.pop(b["tool_use_id"])
                    first = True
                    for r in _cl_records(cmd, c0, _tool_text(b.get("content")), bool(b.get("is_error")),
                                         _line_ts(e, 0)):
                        p = last.get(r["rk"]) or [0, 0.0]
                        r["tok"], r["usd"] = (tok - p[0], round(usd - p[1], 4)) if first else (0, 0.0)
                        last[r["rk"]] = [tok, usd]
                        first = False
                        cm.append(r)
    del cm[:-CL_CM_MAX]
    # sz -1 keeps a cut file "changed" so the next call resumes at off
    ent.update({"off": end, "sz": -1 if cut else st.st_size, "mt": st.st_mtime, "tok": tok, "usd": usd, "cwd": cwd})
    return end - off


def _cl_paths():
    out = []
    for root in projects_dirs(CL_ROOT):
        out += glob.glob(os.path.join(root, "*", "*.jsonl")) + sub_paths(root)
    return out


def _cl_save():
    with _cl_lock:
        blob = json.dumps({"v": 1, "files": _cl["files"]}, ensure_ascii=False, separators=(",", ":"))
    try:
        _atomic_write(CL_INDEX, blob.encode("utf-8"), prefix=".commit-links.")
    except OSError as e:
        warn_once("cl-save", "commit link index save failed ({err}) — rescanned on restart",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)


def _cl_refresh(now=None, budget=None):
    """Bring the index up to date (changed files' tails only, at most `budget` bytes per call; leftover sets
    _cl["more"]). Returns (files scanned, bytes read)."""
    now = now or time.time()
    floor = now - CL_DAYS * 86400
    left = CL_CHUNK if budget is None else budget
    nch, rd, grew, more = 0, 0, False, False
    with _cl_lock:
        if not _cl["loaded"]:
            _cl["loaded"] = True
            try:
                with open(CL_INDEX, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and isinstance(d.get("files"), dict):
                    _cl["files"] = d["files"]
                    for ent in _cl["files"].values():   # v1 index: full "mid|rid" keys -> crc form
                        ks = ent.get("keys") or []
                        if any(len(k) != 8 for k in ks):
                            ent["keys"] = [k if len(k) == 8 else _cl_key(*(k.split("|", 1) + [""])[:2]) for k in ks]
                            grew = True
            except Exception:
                pass                                     # missing or corrupt -> full rescan
        files, seen = _cl["files"], set()
        for fp in _cl_paths():
            try:
                st = os.stat(fp)
            except OSError:
                continue
            if st.st_mtime < floor:
                continue
            seen.add(fp)
            ent = files.get(fp)
            if ent is None:
                ent = files[fp] = _cl_new(fp)
                grew = True
            if st.st_size == ent.get("sz") and abs(st.st_mtime - (ent.get("mt") or 0)) < 0.5:
                continue
            if left <= 0:
                more = True
                continue
            tail = ent["cm"][-1] if ent.get("cm") else None
            try:
                n = _cl_scan(fp, ent, left)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            rd, left, nch = rd + n, left - n, nch + 1
            more = more or ent.get("sz") == -1
            grew = grew or (ent["cm"][-1] if ent["cm"] else None) is not tail
        for fp in [k for k in files if k not in seen]:
            files.pop(fp, None)
            grew = True
        _cl["at"] = time.time()
        _cl["more"] = more
        _cl["dirty"] = _cl.get("dirty") or bool(rd) or grew
        # ⚠ offsets alone are not worth a 2 MB rewrite every CL_TTL; a lost unflushed tail is just rescanned
        save = _cl["dirty"] and (grew or now - (_cl.get("saved") or 0) >= CL_SAVE_S)
        if save:
            _cl["dirty"], _cl["saved"] = False, now
    if save:
        _cl_save()
    return nch, rd


def _cl_bg():
    try:
        while True:
            _cl_refresh()                                # one CL_CHUNK per lock hold
            if not _cl.get("more"):
                break
    except Exception as e:
        warn_once("commitlink", "Could not link commits to sessions ({err})", vars={"err": type(e).__name__})
    finally:
        _cl["busy"] = _cl["bg"] = False


def _cl_ensure():
    """True while the first (cold) scan runs in the background; otherwise refresh inline (incremental)."""
    if _cl["busy"]:
        return True
    if _cl.get("bg"):
        return False                                     # background catch-up running: serve what we have
    with _cl_lock:
        if _cl["at"] and time.time() - _cl["at"] < CL_TTL:
            return False
        cold = not _cl["loaded"] and not os.path.exists(CL_INDEX)
        if cold:
            _cl["busy"] = _cl["bg"] = True
    if cold:
        threading.Thread(target=_cl_bg, name="commit_link", daemon=True).start()
        return True
    _cl_refresh()
    if _cl.get("more"):                                  # big/shrunk file: finish it off the request path
        with _cl_lock:
            go = not _cl.get("bg")
            _cl["bg"] = True
        if go:
            threading.Thread(target=_cl_bg, name="commit_link", daemon=True).start()
    return False


def _cl_log(repo):
    """[(sha7, commit time, subject)] of the repo's recent commits (all refs), cached CL_TTL."""
    hit = _cl_git.get(repo)
    if hit and time.time() - hit[0] < CL_TTL:
        return hit[1]
    out = []
    try:
        r = _git_run(repo, ["log", "--all", "--date-order", "--abbrev=7", "-n", str(CL_LOG_N),
                            "--format=%h%x09%ct%x09%s"], 5)
        for ln in r.stdout.splitlines():
            p = ln.split("\t", 2)
            if len(p) == 3 and p[1].isdigit():
                out.append((p[0][:7], int(p[1]), p[2]))
    except Exception:
        pass                    # git missing/timeout: no commit links this TTL (decoration only)
    _cl_git[repo] = (time.time(), out)
    return out


def _cl_match(recs, commits, want, rk):
    """{sha: rec}. Exact sha7 from `[branch sha]` output first; else same repo + same subject + tool_result within
    CL_MATCH_S after the commit time (closest wins, each record used once)."""
    by = {}
    for r in recs:
        if r.get("sha"):
            o = by.get(r["sha"])
            if o is None or r["ts"] > o["ts"]:
                by[r["sha"]] = r
    info = {c[0]: c for c in commits}
    free = [r for r in recs if not r.get("sha") and r.get("rk") == rk]
    used, out = set(), {}
    for s in want:
        r = by.get(s[:7])
        if r is not None:
            out[s] = r
            continue
        c = info.get(s[:7])
        if not c:
            continue
        best, bd = None, None
        for i, x in enumerate(free):
            if i in used or not x.get("subj") or not (c[2] == x["subj"] or c[2].startswith(x["subj"])):
                continue
            dt = (x.get("ts") or 0) - c[1]
            # dt = record ts - commit time; ⚠ rank records at/after the commit first, then by |dt| —
            # plain min(dt) let a negative dt (an earlier same-subject commit's record) win.
            k = (dt < 0, abs(dt))
            if -60 <= dt <= CL_MATCH_S and (bd is None or k < bd):
                best, bd = i, k
        if best is not None:
            used.add(best)
            out[s] = free[best]
    return out


def commit_links(repo, shas=""):
    """(status, body) for /api/git/links. Body: {ok, busy, links: {sha: {sid, agent, proj, ts, tok, usd, tid, cwd}}}."""
    t0 = time.time()
    if not _branch_ok(repo):
        return 403, {"ok": False, "err": "This repository is not in the list"}
    if _cl_ensure():
        return 200, {"ok": True, "busy": True, "links": {}, "n": 0, "ms": int((time.time() - t0) * 1000)}
    busy = False
    commits = _cl_log(repo)
    want = [s for s in (shas or "").split(",") if _SHA_RE.match(s)][:200] or [c[0] for c in commits[:80]]
    floor = time.time() - CL_DAYS * 86400
    with _cl_lock:
        files = dict(_cl["files"])
        recs = []
        for fp, ent in files.items():
            for r in ent.get("cm") or []:
                if (r.get("ts") or 0) >= floor:
                    recs.append((r, fp, ent))
    idx = {id(r): (fp, ent) for r, fp, ent in recs}
    hit = _cl_match([r for r, _f, _e in recs], commits, want, _main_checkout_of(repo))
    links = {}
    for s, r in hit.items():
        fp, ent = idx[id(r)]
        sid, agent = ent.get("sid") or "", ent.get("agent") or ""
        if agent:
            # the /work popup takes the parent session's launch cwd for an agent tid (same form as the history tab)
            main = files.get(sub_sess_dir(fp) + ".jsonl") or {}
            cwd = main.get("scwd") or ent.get("scwd") or ""
            tid = (ent.get("tuid") + "|" + sid) if ent.get("tuid") else ""
        else:
            cwd = ent.get("scwd") or ""
            tid = ("sess:" + cwd + "|" + sid) if cwd else ""
        links[s] = {"sid": sid, "agent": agent, "proj": _proj_name(r.get("rk") or r.get("dir") or ""),
                    "ts": int(r.get("ts") or 0), "tok": int(r.get("tok") or 0), "usd": round(float(r.get("usd") or 0), 2),
                    "tid": tid, "cwd": cwd, "how": "sha" if r.get("sha") else "subj"}
    return 200, {"ok": True, "busy": busy, "links": links, "n": len(want), "ms": int((time.time() - t0) * 1000)}
