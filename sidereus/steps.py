"""Transcript step extraction for the work views: languages, edit targets, step scanning."""
import json
import os
import re
from sidereus.transcript import _lines_until, _tail_lines, _tool_target
from sidereus.config import IS_WIN
from sidereus.gitinfo import _git_root
from sidereus.redact import redact


AGENT_STEPS_MAX = 400      # cap on one agent's tool footprints — if longer, keep the tail (recent)
AGENT_TEXT_MAX = 20_000    # instruction cap
AGENT_SAY_MAX = 4_000      # cap per utterance
AGENT_SAYS_MAX = 60        # utterance count cap — beyond it, recent only
AGENT_EDIT_MAX = 6_000     # cap for each of before/after of one edit
AGENT_ARG_MAX = 220        # cap per tool-argument line
AGENT_RES_LINES = 6        # result preview lines — same slot as `⎿` in the Claude Code console
# ★Edit-body chars per popup response: one MultiEdit step can carry 20×2×6000 = 240k, so 2M still fits ~8 full
#   MultiEdits; without it a 400-step session measured ~96 MB. ⚠Bodies past it are dropped, steps are kept.
AGENT_EDIT_BUDGET = 2_000_000


def _cap_edit_bodies(steps, budget=None):
    """Spend the edit-body budget newest step first; older steps lose `edit`/`edits` (metadata stays). Returns the count cut."""
    left = AGENT_EDIT_BUDGET if budget is None else budget
    cut = 0
    for st in reversed(steps):
        e, es = st.get("edit"), st.get("edits")
        if not e and not es:
            continue
        n = (len(e.get("old", "")) + len(e.get("new", ""))) if e else 0
        n += sum(len(x.get("old", "")) + len(x.get("new", "")) for x in (es or []))
        if n <= left:
            left -= n
            continue
        st.pop("edit", None)
        st.pop("edits", None)
        st["editCut"] = True
        cut += 1
    return cut


# ★Whether a result is code is judged **by the command only**. Guessing from content catches things like Korean
#   commit messages in `git log` as code and paints random words as keywords (worse than nothing).
#   When unclear, treat as not code: not painting is less harmful when wrong.
# ★Language is determined by extension (2026-08-31). A plain code/not-code flag uses one keyword bundle, so
#   SQL's SELECT and Java's class get mixed and mispainted in each other's code.
_EXT_LANG = {
    ".java": "java", ".kt": "java", ".gradle": "java", ".cs": "java", ".scala": "java",
    ".sql": "sql",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js", ".ts": "js", ".tsx": "js",
    ".py": "py",
    ".sh": "sh", ".bash": "sh", ".zsh": "sh",
    ".go": "go", ".rs": "go",
    ".rb": "rb", ".php": "js",
    ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c",
    ".xml": "xml", ".html": "xml", ".jsp": "xml", ".g4": "g4",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".properties": "props", ".css": "css",
    # ★Prose and logs get **no keyword painting** (measured 2026-08-31: `pass`·`npm` were painted as keywords
    #   in docs/*.md). Unknown extensions fall to the combined set, so these are listed explicitly as empty.
    ".md": "none", ".txt": "none", ".log": "none", ".patch": "none", ".diff": "none",
    ".csv": "none", ".rst": "none", ".adoc": "none",
}
_PATH_RE2 = re.compile(r"[\w./\-]+\.[A-Za-z0-9]{1,8}")


def _lang_of(text):
    """Extract the language from a path string. With several paths in a command, use **the last**
    (the target comes last, as in `cd /x && cat a/b/Foo.java`)."""
    hit = ""
    for m in _PATH_RE2.finditer(text or ""):
        ext = os.path.splitext(m.group(0))[1].lower()
        if ext in _EXT_LANG:
            hit = _EXT_LANG[ext]
    return hit


_READ_CMD = re.compile(r"\b(cat|bat|sed\s+-n|head|tail)\b")


def _res_is_code(tool, arg):
    """(is code, language). Decided by **extension** — no content guessing."""
    a = arg or ""
    lang = _lang_of(a)
    if tool in ("Read", "NotebookRead"):
        return bool(lang), lang                       # no readable extension ⇒ not code
    if tool == "Bash" and _READ_CMD.search(a.lower()):
        return bool(lang), lang
    return False, ""


# ★Subagents **rarely use the Edit tool** (measured 2026-08-31: one agent's 54 steps were Bash 53 · Read 1).
#   Auto mode instructs "make file changes with sed, heredocs or short scripts". So building +/- from tool_use
#   old_string/new_string almost never applies in practice.
#   → Instead **pick only the write-target files out of the command**, and take their +/- from git.
#     (No interpreting Python code inside the command to guess old/new — that yields plausible falsehoods.)
_WRITE_SIG = re.compile(
    r"""open\(\s*[^)]*['"][wa]b?['"]"""       # python open(p,"w")
    r"""|\.write_(text|bytes)\(|\.writelines\(|writeFileSync"""
    r"""|\bsed\s+-i\b|\btee\b|\bpatch\b"""
    r"""|>\s*['"]?[\w./~-]+\.[A-Za-z0-9]{1,8}"""   # redirect (targets with an extension only — excludes 2>&1)
    r"""|\b(cp|mv)\s+[\w./~-]+\s""")
def _path_res(win):
    """(cd regex, write-target path regex). ⚠Windows adds `C:` and `\\`; on POSIX a `\\` is a shell escape, so it stays out."""
    if win:                                       # `~` too: 8.3 short names like `RUNNER~1`
        return (re.compile(r"\bcd\s+(?:/[dD]\s+)?((?:[A-Za-z]:)?[\w./\\~-]+)"),   # cmd `cd /d C:\x`: skip the flag
                re.compile(r"(?:[A-Za-z]:)?[\w./\\~-]+\.[A-Za-z0-9]{1,8}"))
    return re.compile(r"\bcd\s+([\w./~-]+)"), _PATH_RE2


_CD_RE, _WPATH_RE = _path_res(IS_WIN)
_BUILD_DIRS = {"build", "target", "node_modules", "dist", "out", "coverage", ".gradle",
               ".git", "__pycache__", ".venv", "vendor", ".next", ".cache"}


def _outside(rel):
    """True when a root-relative path escapes the root (`..` or `../x`); `..foo/x` is a real in-repo name."""
    return rel == ".." or rel.startswith("../")


def _edit_target(path):
    """Absolute path of Edit/Write -> `{cwd: git root, path: root-relative path}`. None outside a repo.
    ★Returns **the same shape** as `_wrote_files` — so the UI (tree, inline diff) needs only one format."""
    if not path or not os.path.isabs(path):
        return None
    root = _git_root(os.path.dirname(path))
    if not root:
        return None
    try:
        rel = os.path.relpath(path, root).replace(os.sep, "/")   # output is always `/`-separated (Windows relpath uses `\`)
    except ValueError:
        return None
    if _outside(rel) or any(seg in _BUILD_DIRS for seg in rel.split("/")):
        return None
    return {"cwd": root, "path": rel}


def _wrote_files(cmd):
    """Files the command **appears to have modified**. Empty list when unsure (wrong is worse than missing).
    Whether the returned paths really changed, the UI asks git — this only picks candidates."""
    if not cmd or not _WRITE_SIG.search(cmd):
        return []
    m = _CD_RE.search(cmd)
    work = os.path.abspath(os.path.expanduser(m.group(1))) if m else ""
    repo = _git_root(work) if work else ""
    # ★If the `cd` target is known but not a git repo, **drop the candidates**. Leaving it empty makes the caller
    #   fall back to the session repo, and if that repo happens to have the same relative path it shows
    #   **the diff of an unrelated file** — wrong is worse than missing.
    if work and not repo:
        return []
    seen, out = set(), []
    for pm in _WPATH_RE.finditer(cmd):
        rel = pm.group(0).strip("'\"")
        if os.sep == "\\":
            rel = rel.replace("\\", "/")          # one separator for the checks below; ntpath accepts `/`
        if os.path.splitext(rel)[1].lower() not in _EXT_LANG:
            continue
        if rel.startswith(("./",)):
            rel = rel[2:]
        # ★A URL is not a file — it carries `.html`·`.json` extensions, and left alone a doc link shows up
        #   as a "modified file" (measured 2026-08-26: docs.oracle.com/.../create_index.html).
        if pm.start() >= 2 and ("//" in cmd[max(0, pm.start() - 12):pm.start()]
                                or "http" in cmd[max(0, pm.start() - 12):pm.start()]):
            continue
        # ★Drop build output — git filters it anyway, but a string of "no changes" notes clutters the screen
        if any(seg in _BUILD_DIRS for seg in rel.split("/")):
            continue
        # ★Drop tokens without `/` — fragments like `java.sql` from `import java.sql.*` or `Probe.java`
        #   were taken as files by extension alone (measured 2026-08-31). Real targets nearly always have a path.
        if "/" not in rel:
            continue
        if rel in seen or rel.count("/") > 12:
            continue
        seen.add(rel)
        # rewrite the path **relative to the root** — if the working dir was a subdirectory, prefix it
        #   (e.g. cd .../frontend + src/a.tsx  ->  frontend/src/a.tsx)
        # ⚠Drop anything that resolves outside the repo (same rule as `_edit_target`): an absolute path used to
        #   pass through raw as {"cwd": repo, "path": "/abs/..."}, and `../x` escaped the root unchecked.
        out_path, out_cwd = rel, repo
        if os.path.isabs(rel):
            if repo:
                try:
                    out_path = os.path.relpath(os.path.normpath(rel), repo).replace(os.sep, "/")
                except ValueError:
                    continue
                if _outside(out_path):
                    continue
            else:
                # no `cd`: the file names its own repo — resolve it exactly like an Edit target
                t = _edit_target(os.path.normpath(rel))
                if not t:
                    continue
                out_path, out_cwd = t["path"], t["cwd"]
        elif repo and work:
            try:
                out_path = os.path.relpath(os.path.normpath(os.path.join(work, rel)), repo).replace(os.sep, "/")
            except ValueError:
                continue
            if _outside(out_path):
                continue
        elif ".." in rel.split("/"):
            continue                              # base dir unknown: `..` could land anywhere
        out.append({"cwd": out_cwd, "path": out_path})
        if len(out) >= 6:
            break
    return out


_CUT_MARGIN = 2048         # longer than any token/DSN pattern; _PEM matches to \Z so a cut PEM still masks


def _cut(s, n):
    """Redact, then cut to n. ⚠Never cut before redacting: a secret straddling the cut loses its anchor (`@`, closing quote) and leaks."""
    s = s or ""
    head = s[:n + _CUT_MARGIN]
    r = redact(head)
    if len(r) < n < len(s):               # masking shrank the head below n: text past it would show unredacted
        r = redact(s)
    return r[:n]


def _agent_arg(b):
    """**The actual argument** as printed in the console. The command, path or pattern itself, not the description.

    ★2026-08-27: must read like `Bash(cd /path && git log --oneline -3)`.
      description is a label someone attached; it does not say "what was run"."""
    a = b.get("input") if isinstance(b.get("input"), dict) else {}
    for k in ("command", "file_path", "notebook_path", "path", "pattern", "url", "query", "prompt"):
        v = a.get(k)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return _cut(v, AGENT_ARG_MAX)
    return _cut(a.get("description") or "", AGENT_ARG_MAX)
# ★Code changes sit inside `Edit`/`Write` calls as is (old_string/new_string · content).
#   Showing only the tool name does not tell "what was changed" (2026-08-27), so the content goes along.
_EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


SESS_TAIL = 600            # tail lines read from a session transcript — recent work only (the whole is 1GB)


def _open_or_tail(fp, tail=0, at=None):
    """Line supplier. With tail>0 read **only the tail lines** — session transcripts exceed 1GB and
    scanning them whole freezes the screen (measured 2026-08-26: repo-A 910MB, tail read 1ms).
    `at` (epoch) = the same-size window ending at that moment instead of at EOF (retro failure drill-down)."""
    if tail and at:
        return _lines_until(fp, at, nbytes=tail * 3_000, limit=tail)
    if tail:
        return _tail_lines(fp, nbytes=tail * 3_000, limit=tail)
    return open(fp, encoding="utf-8", errors="ignore")


def _scan_blocks(c, steps, results, cwd, says, ts):
    """One message's content blocks -> appends to steps/says, fills results (mutates the passed list/dict)."""
    for b in c:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_result":
            # ★result (`⎿`) — what the tool returned. Without it there are footprints but no answers.
            c2 = b.get("content")
            txt = c2 if isinstance(c2, str) else (
                "\n".join(x.get("text", "") for x in c2
                           if isinstance(x, dict) and x.get("type") == "text")
                if isinstance(c2, list) else "")
            txt = (txt or "").strip()
            if b.get("tool_use_id") and (txt or b.get("is_error")):   # an empty error still counts as an error
                ls = [l for l in txt.splitlines()][:AGENT_RES_LINES]
                more = len(txt.splitlines()) - len(ls)
                results[b["tool_use_id"]] = {
                    "lines": [_cut(l, AGENT_ARG_MAX) for l in ls],
                    "more": max(0, more),
                    "err": bool(b.get("is_error")),
                }
            continue
        if b.get("type") == "tool_use":
            st = {"t": (ts or ""), "tool": b.get("name") or "?",
                  "targ": _tool_target(b), "arg": _agent_arg(b), "id": b.get("id")}
            if st["tool"] == "Bash":
                # ★Judge by **the original command** — st["arg"] is truncated for display, losing
                #   write signals near the end like open(p,"w") (measured 2026-08-31: all 76 steps missed).
                _bi = b.get("input") if isinstance(b.get("input"), dict) else {}
                w = _wrote_files(str(_bi.get("command") or ""))
                for _x in w:                      # without cd, assume the session's repo
                    if not _x["cwd"]:
                        _x["cwd"] = cwd or ""
                if w:
                    st["wrote"] = w
            if st["tool"] in _EDIT_TOOLS:
                a = b.get("input") if isinstance(b.get("input"), dict) else {}
                old_s = a.get("old_string")
                new_s = a.get("new_string")
                if new_s is None:
                    new_s = a.get("content")      # Write has only content
                # ★Language is set by the edited **file's extension** (2026-08-31) — so the UI paints only that
                #   language's keywords. Edit·MultiEdit target one file, so one per step suffices.
                if old_s or new_s:
                    st["elang"] = _lang_of(a.get("file_path") or a.get("notebook_path") or "")
                    # ★Edit targets also go into `wrote` (2026-09-01) — the "modified files" tree reads
                    #   only `wrote`. Step rendering prefers edit, so inline blocks do not
                    #   overlap (order edit → edits → wrote).
                    _ew = _edit_target(a.get("file_path") or a.get("notebook_path") or "")
                    if _ew:
                        st.setdefault("wrote", []).append(_ew)
                    st["edit"] = {
                        "path": a.get("file_path") or a.get("notebook_path") or "",
                        "old": _cut(old_s, AGENT_EDIT_MAX),
                        "new": _cut(new_s, AGENT_EDIT_MAX),
                        "cut": max(len(old_s or ""), len(new_s or "")) > AGENT_EDIT_MAX,
                    }
                # MultiEdit is an edits array — report the count only (bodies are long, so folded)
                eds = a.get("edits")
                if isinstance(eds, list) and eds:
                    st["elang"] = _lang_of(a.get("file_path") or "")
                    _ew = _edit_target(a.get("file_path") or "")
                    if _ew and not st.get("wrote"):
                        st["wrote"] = [_ew]
                    st["edits"] = [{"old": _cut(str(x.get("old_string") or ""), AGENT_EDIT_MAX),
                                    "new": _cut(str(x.get("new_string") or ""), AGENT_EDIT_MAX)}
                                   for x in eds[:20]]
            steps.append(st)
        elif b.get("type") == "text" and (b.get("text") or "").strip():
            says.append({"t": (ts or ""), "text": _cut(b["text"], AGENT_SAY_MAX)})


def _work_scan(_src, cwd=""):
    """Scrape tool footprints, results, utterances and instruction in one pass. Subagent logs and session transcripts
    share **the same format**, so they share the parser (2026-08-26: main sessions shown in the same view).
    ⚠Session transcripts exceed 1GB — callers must pass **only the tail** (opening the whole freezes the screen).
    ★cwd is the repo fallback for commands without `cd` — a refactor dropped this name from scope, raising NameError,
      and the parser swallowed it so **one session silently showed a blank screen** (measured 2026-08-26)."""
    steps, says = [], []
    results = {}          # tool_use_id -> result preview
    prompt = luser = ""
    first = last = None
    try:
        for line in _src:
            if not line.startswith("{"):
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            ts = e.get("timestamp")
            if ts:
                first = first or ts
                last = ts
            c = (e.get("message") or {}).get("content")
            # ★Instruction extraction sits **before** the list check — the first user message is usually **a string**,
            #   so after it the message was filtered out and the instruction was always empty (measured 2026-08-27: 0 chars).
            if e.get("type") == "user":
                _u = c if isinstance(c, str) else (" ".join(
                    b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    if isinstance(c, list) else "")
                _u = _cut(_u, AGENT_TEXT_MAX)
                if not prompt:
                    prompt = _u
                # ★Keep **the last** human utterance too. For an agent the first instruction is the task, but
                #   a session is read only from the tail, so its "first user" is some mid-conversation line — not an instruction.
                if _u.strip():
                    luser = _u
                # ⚠tool_result blocks arrive on `user` lines — the bare `continue` here dropped every result, so the
                #   work log always said «0 errors» and showed no `⎿`. Only tool_result blocks: user text is not a «says».
                if isinstance(c, list):
                    _scan_blocks([b for b in c if isinstance(b, dict) and b.get("type") == "tool_result"],
                                 steps, results, cwd, says, ts)
                continue
            if not isinstance(c, list):
                continue
            _scan_blocks(c, steps, results, cwd, says, ts)
    except Exception as e:
        return None, {"msg": "Could not read the record ({err})", "vars": {"err": type(e).__name__}}   # TV reply part
    finally:
        # ⚠_open_or_tail(tail=0) hands over a bare file object; unclosed it leaks an fd per popup poll.
        if hasattr(_src, "close"):
            _src.close()

    return (steps, says, results, prompt, first, last, luser), None
