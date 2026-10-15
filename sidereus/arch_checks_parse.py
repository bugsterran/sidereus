"""Project-check report parsers (split from sidereus/arch_checks.py for the size cap) + per-rule help.

Each parser turns one tool's output into [{file, line, rule, sev, help?}] with file as the tool wrote it;
ValueError = unreadable. `help` = {desc, url} from the tool's own rule metadata (generic rule text, never the
per-finding message). Stdlib only; no sidereus imports.
"""
import json
import re
import xml.etree.ElementTree as ET

SEVS = ("error", "warning")
HELP_DESC_MAX, HELP_URL_MAX = 140, 300
_URL_BAD = re.compile(r"[\s\x00-\x1f\x7f\"'<>\\]")
_VET = frozenset("appends asmdecl assign atomic bools buildtag cgocall composites copylocks defers directive errorsas "
                 "framepointer httpresponse ifaceassert loopclosure lostcancel nilfunc printf shift sigchanyzer slog "
                 "stdmethods stringintconv structtag testinggoroutine tests timeformat unmarshal unreachable unsafeptr "
                 "unusedresult".split())


def clean_help(desc, url):
    """{desc, url} with desc control-free and <= HELP_DESC_MAX, url https-only and <= HELP_URL_MAX; None if both empty."""
    d = "".join(c for c in desc if ord(c) >= 32 and ord(c) != 127).strip()[:HELP_DESC_MAX] if isinstance(desc, str) else ""
    u = url if isinstance(url, str) and url.startswith("https://") and len(url) <= HELP_URL_MAX \
        and not _URL_BAD.search(url) else ""
    return {"desc": d, "url": u} if d or u else None


def checkstyle_url(source):
    """Docs URL of a built-in checkstyle check class (custom checks: "")."""
    m = re.fullmatch(r"com\.puppycrawl\.tools\.checkstyle\.checks\.(?:([a-z]+)\.)?([A-Za-z0-9]+?)Check", source or "")
    if not m:
        return ""
    if not m.group(1):
        return "https://checkstyle.org/checks.html"
    return "https://checkstyle.org/checks/%s/%s.html#%s" % (m.group(1), m.group(2).lower(), m.group(2))


def _item(f, line, rule, sev, url=None, desc=None):
    try:
        ln = int(line)
    except (TypeError, ValueError):
        ln = 0
    x = {"file": f if isinstance(f, str) else "", "line": max(0, ln), "rule": rule if isinstance(rule, str) else "",
         "sev": sev}
    h = clean_help(desc, url)
    if h:
        x["help"] = h
    return x


def _xml(text, root):
    """Root element of the `<root>…</root>` part of text. ⚠DOCTYPE / ENTITY are refused before parsing (no expansion)."""
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
        raise ValueError("doctype refused")
    a, b = text.find("<" + root), text.rfind("</%s>" % root)
    if a < 0 or b < a:
        raise ValueError("no %s report (truncated?)" % root)
    try:
        return ET.fromstring(text[a:b + len(root) + 3])
    except ET.ParseError as e:
        raise ValueError("bad xml: %s" % type(e).__name__)


def _tag(e):
    return e.tag.rsplit("}", 1)[-1] if isinstance(e.tag, str) else ""


def parse_checkstyle(text):
    out = []
    for f in _xml(text, "checkstyle").iter():
        if _tag(f) != "file":
            continue
        for e in f:
            sev = e.get("severity") or "warning"
            if _tag(e) == "error" and sev != "ignore":
                src = e.get("source") or ""
                out.append(_item(f.get("name"), e.get("line"), src.rsplit(".", 1)[-1],
                                 "error" if sev == "error" else "warning", checkstyle_url(src)))
    return out


def parse_pmd(text):
    """PMD 6/7 XML: priority 1-2 -> error, 3-5 -> warning."""
    out = []
    for f in _xml(text, "pmd").iter():
        if _tag(f) != "file":
            continue
        for v in f:
            if _tag(v) != "violation":
                continue
            try:
                pr = int(v.get("priority") or 3)
            except ValueError:
                pr = 3
            out.append(_item(f.get("name"), v.get("beginline"), v.get("rule"), "error" if pr <= 2 else "warning",
                             v.get("externalInfoUrl")))
    return out


def _json(text):
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError("bad json")


def parse_ruff(text):
    j = _json(text)
    if not isinstance(j, list):
        raise ValueError("ruff: not a list")
    out = []
    for x in j:
        if isinstance(x, dict):
            u = x.get("url") if isinstance(x.get("url"), str) else ""
            slug = u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ") if u else ""   # rule name from the docs URL
            out.append(_item(x.get("filename"), (x.get("location") or {}).get("row"), x.get("code") or "syntax",
                             "warning" if x.get("code") else "error", u, slug))
    return out


def parse_eslint(text):
    """`-f json` (list) or `-f json-with-metadata` ({results, metadata.rulesMeta} -> rule docs)."""
    j = _json(text)
    meta = {}
    if isinstance(j, dict):
        md = j.get("metadata")
        meta = md.get("rulesMeta") if isinstance(md, dict) and isinstance(md.get("rulesMeta"), dict) else {}
        j = j.get("results")
    if not isinstance(j, list):
        raise ValueError("eslint: no results list")
    out = []
    for f in j:
        for m in (f.get("messages") or ()) if isinstance(f, dict) else ():
            if isinstance(m, dict):
                rm = meta.get(m.get("ruleId")) if isinstance(m.get("ruleId"), str) else None
                docs = rm.get("docs") if isinstance(rm, dict) and isinstance(rm.get("docs"), dict) else {}
                out.append(_item(f.get("filePath"), m.get("line"), m.get("ruleId") or "parse",
                                 "error" if m.get("severity") == 2 or m.get("fatal") else "warning",
                                 docs.get("url"), docs.get("description")))
    return out


_TSC = re.compile(r"^(.+?)(?:\((\d+),\d+\):|:(\d+):\d+ -) (error|warning) (TS\d+):")
_MYPY = re.compile(r"^(.+?\.pyi?):(\d+)(?::\d+)?: (error|warning|note): .*?(?:\[([a-z0-9-]+)\])?\s*$")
_GOVET = re.compile(r"^(?:vet: )?([^\s:#][^:]*\.go):(\d+)(?::\d+)?: (?:([a-z]+): )?")


def parse_tsc(text):
    out = []
    for ln in text.splitlines():
        m = _TSC.match(ln)
        if m:
            out.append(_item(m.group(1), m.group(2) or m.group(3), m.group(5), m.group(4)))
    return out


def parse_mypy(text):
    out = []
    for ln in text.splitlines():
        m = _MYPY.match(ln)
        if m and m.group(3) != "note":
            out.append(_item(m.group(1), m.group(2), m.group(4) or "mypy", m.group(3), m.group(4) and
                             "https://mypy.readthedocs.io/en/stable/error_code_list.html#code-" + m.group(4)))
    return out


def parse_govet(text):
    out = []
    for ln in text.splitlines():
        m = _GOVET.match(ln)
        if m:
            out.append(_item(m.group(1), m.group(2), m.group(3) if m.group(3) in _VET else "vet", "warning"))
    return out


def parse_clippy(text):
    """cargo --message-format=json lines; primary span only."""
    out = []
    for ln in text.splitlines():
        if not ln.startswith("{"):
            continue
        try:
            j = json.loads(ln)
        except ValueError:
            continue
        m = j.get("message") if isinstance(j, dict) and j.get("reason") == "compiler-message" else None
        if not isinstance(m, dict) or m.get("level") not in SEVS:
            continue
        sp = [s for s in m.get("spans") or () if isinstance(s, dict) and s.get("is_primary")]
        if sp:
            code = (m.get("code") or {}).get("code") if isinstance(m.get("code"), dict) else None
            url = "https://rust-lang.github.io/rust-clippy/master/#" + code[8:] \
                if isinstance(code, str) and code.startswith("clippy::") else None
            out.append(_item(sp[0].get("file_name"), sp[0].get("line_start"), code or "rustc", m["level"], url))
    return out


_MYPY_N = re.compile(r"\(checked (\d+) source files?\)|\bin (\d+) source files?\b")


def checkstyle_files(text):
    """<file> elements of a checkstyle report (it lists every file checked, clean ones too)."""
    return sum(1 for e in _xml(text, "checkstyle").iter() if _tag(e) == "file")


def eslint_files(text):
    j = _json(text)
    j = j.get("results") if isinstance(j, dict) else j
    return len(j) if isinstance(j, list) else 0


def mypy_files(text):
    """N from mypy's summary («checked N source files» / «in N source files»); 0 if absent."""
    m = _MYPY_N.search(text or "")
    return int(m.group(1) or m.group(2)) if m else 0


PARSERS = {"checkstyle": parse_checkstyle, "pmd": parse_pmd, "ruff": parse_ruff, "eslint": parse_eslint,
           "tsc": parse_tsc, "mypy": parse_mypy, "govet": parse_govet, "clippy": parse_clippy}
