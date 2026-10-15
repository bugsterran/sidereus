"""Declared phase titles of a Workflow-tool run, read from its saved script's `export const meta = {...}`.
⚠Only `meta.phases[].title` string literals and the script basename leave this module — never the script body."""
import glob
import os
import re

from sidereus.memo import BoundedMemo
from sidereus.redact import redact

HEAD_MAX = 16384      # ⚠meta sits at the top of the script; never read past this
TITLES_MAX = 12
TITLE_LEN = 40
_RUN_ID = re.compile(r"^wf_[0-9A-Za-z-]{1,40}$")
_META = "export const meta ="
_WORD = re.compile(r"[^\s'\"`{}\[\]():,]+")
_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
_META_MEMO = BoundedMemo(200)   # script path -> ((mtime, size), [titles])


def script_path(sess_dir, run_id):
    """`<sess>/workflows/scripts/<name>-<run_id>.js`, or '' (bad id / no file)."""
    if not _RUN_ID.match(str(run_id or "")):
        return ""
    hits = sorted(glob.glob(os.path.join(glob.escape(sess_dir), "workflows", "scripts", "*-" + run_id + ".js")))
    return hits[0] if hits else ""


def script_name(sess_dir, run_id):
    """Script basename minus `-<run_id>.js` ('' when there is no script)."""
    p = script_path(sess_dir, run_id)
    return os.path.basename(p)[:-len("-" + run_id + ".js")][:60] if p else ""


def _string(src, i):
    """(decoded literal, index after the closing quote, saw `${`) for a quote at src[i]; raises ValueError if unclosed."""
    q, out, j, n, tpl = src[i], [], i + 1, len(src), False
    while j < n:
        c = src[j]
        if c == "\\":
            if j + 1 >= n:
                break
            e = src[j + 1]
            if e == "u":
                m = re.match(r"\{([0-9a-fA-F]{1,6})\}|([0-9a-fA-F]{4})", src[j + 2:j + 10])
                if not m:
                    raise ValueError("bad escape")
                out.append(chr(int(m.group(1) or m.group(2), 16)))
                j += 2 + m.end()
                continue
            if e == "\n":
                j += 2                        # line continuation
                continue
            out.append(_ESC.get(e, e))
            j += 2
            continue
        if c == q:
            return "".join(out), j + 1, tpl
        if q == "`" and c == "$" and src[j + 1:j + 2] == "{":
            tpl = True
        if q != "`" and c == "\n":
            break
        out.append(c)
        j += 1
    raise ValueError("unclosed string")


def _tokens(src, i):
    """Tokens of the brace-balanced object starting at src[i] == '{': ("s", text) | ("p", char) | ("w", word)."""
    toks, depth, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
        elif src.startswith("//", i):
            k = src.find("\n", i)
            i = n if k < 0 else k + 1
        elif src.startswith("/*", i):
            k = src.find("*/", i + 2)
            if k < 0:
                raise ValueError("unclosed comment")
            i = k + 2
        elif c in "'\"`":
            s, i, tpl = _string(src, i)
            if tpl:
                raise ValueError("template substitution")
            toks.append(("s", s))
        elif c in "{[(":
            depth += 1
            toks.append(("p", c))
            i += 1
        elif c in "}])":
            depth -= 1
            toks.append(("p", c))
            i += 1
            if depth == 0:
                return toks
        elif c in ":,":
            toks.append(("p", c))
            i += 1
        else:
            m = _WORD.match(src, i)
            toks.append(("w", m.group(0)))
            i = m.end()
    raise ValueError("unbalanced meta")


def _titles(toks):
    """`phases[].title` literals from the meta token list; raises ValueError on a non-literal title."""
    out, k, n = [], 0, len(toks)
    while k + 2 < n:
        if toks[k][0] in ("w", "s") and toks[k][1] == "phases" and toks[k + 1] == ("p", ":") and toks[k + 2] == ("p", "["):
            break
        k += 1
    else:
        return out
    depth, k = 0, k + 2
    while k < n:
        t = toks[k]
        if t[0] == "p" and t[1] in "{[(":
            depth += 1
        elif t[0] == "p" and t[1] in "}])":
            depth -= 1
            if depth == 0:
                return out
        elif depth == 2 and t[0] in ("w", "s") and t[1] == "title" and k + 1 < n and toks[k + 1] == ("p", ":"):
            if k + 3 >= n or toks[k + 2][0] != "s" or toks[k + 3] not in (("p", ","), ("p", "}")):
                raise ValueError("non-literal title")
            out.append(toks[k + 2][1])
            k += 2
        k += 1
    return out


def phase_titles(sess_dir, run_id):
    """Declared phase titles of run `run_id` (<=12, each <=40 chars, redacted); [] on any doubt."""
    p = script_path(sess_dir, run_id)
    if not p:
        return []
    try:
        st = os.stat(p)
    except OSError:
        return []
    sig = (st.st_mtime, st.st_size)
    hit = _META_MEMO.get(p, stamp=sig)
    if hit is not None:
        return list(hit)
    try:
        with open(p, "rb") as f:
            src = f.read(HEAD_MAX).decode("utf-8", "replace")
    except OSError:
        return []
    out = []
    i = src.find(_META)
    if i >= 0:
        j = src.find("{", i + len(_META))
        if j >= 0 and not src[i + len(_META):j].strip():
            try:
                out = [redact(t)[:TITLE_LEN] for t in _titles(_tokens(src, j))[:TITLES_MAX]]
            except (ValueError, AttributeError):
                out = []
    return list(_META_MEMO.put(p, out, stamp=sig))
