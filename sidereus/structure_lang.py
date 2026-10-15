"""Structure treemap language scanners: per-language function extraction (Python ast, JS/Go brace scan, Java/Kotlin depth scan, JSP one cell) and `_struct_one_file`."""
import ast
import hashlib
import os
import re
import warnings
from sidereus.structure_plug import lang_for, plug_lang

# ⚠ast.parse of user code prints SyntaxWarning (invalid escapes) to viewer.err on 3.12+; filter by pseudo-filename (catch_warnings is not thread-safe).
_USER_SRC = "<user-src>"
warnings.filterwarnings("ignore", category=SyntaxWarning, module=re.escape(_USER_SRC) + "$")


STRUCT_JS_EXTS = (".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".mts", ".cts")   # ES-module/CommonJS variants too
# ★Projects whose core is Java were missing entirely — measured 2026-09-22 repo-B java 1,675 ·
#   repo-A java 1,352 + jsp 400. So the 562,705 lines were almost all static js assets.
STRUCT_JAVA_EXTS = (".java", ".kt")
# JSP has no function units ⇒ one file becomes one cell.
STRUCT_JSP_EXTS = (".jsp", ".jspf", ".tag")
# Go: `func` declarations scanned by brace matching; `_test.go` counts as test (same dir as its source).
STRUCT_GO_EXTS = (".go",)


def _struct_py_fns(src):
    """Python functions — `ast` FunctionDef/AsyncFunctionDef (including nested). Empty list on failure."""
    try:
        tree = ast.parse(src, filename=_USER_SRC)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []               # user code that does not parse (or nests too deep): no function cells
    lines = src.splitlines()
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = n.lineno
        b = getattr(n, "end_lineno", None) or a
        body = "\n".join(lines[a - 1:b])
        out.append({"name": n.name, "lang": "py", "line": a, "lines": max(1, b - a + 1),
                    "h": hashlib.md5(body.encode("utf-8", "replace")).hexdigest()[:12]})
    return out


# ⚠JS has no parser, so count braces. Skip strings·templates·comments; regex literals are
#   split by «the previous non-space character» (standard heuristic). If depth does not close or exceeds 900 lines, that function
#   is dropped — missing it is better than emitting a wrong large number.
_JS_RE_PREV = "(,=:[!&|?{};+-*<>~^\n\t "


def _js_block_end(s, i):
    """Index of the `}` matching the first `{` after `s[i]`. For an expression arrow, the `;` position; -1 if not found."""
    n = len(s)
    while i < n and s[i] != "{":
        if s[i] == ";":
            return i                  # expression-body arrow (`const g = u => f(u);`)
        i += 1
    if i >= n:
        return -1
    depth = 0
    prev = "\n"
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "'\"`":
            q = c
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == q:
                    break
                i += 1
            i += 1
            prev = q
            continue
        if c == "/" and prev in _JS_RE_PREV:
            i += 1
            while i < n and s[i] != "\n":
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == "/":
                    break
                i += 1
            i += 1
            prev = "/"
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        if not c.isspace():
            prev = c
        i += 1
    return -1


_JS_FN = re.compile(
    r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(|"
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
    r"(?:async\s*)?(?:function\b|\([^()]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")


def _js_mask(s):
    """`s` with comment, string/template and regex-literal contents blanked to spaces (newlines and length kept),
    so `_JS_FN` does not match `function x() {}` inside them. Same lexing heuristics as `_js_block_end`."""
    out = list(s)
    n = len(s)
    i = 0
    prev = "\n"

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            j = s.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2          # ⚠unclosed block comment blanks to the end
            blank(i, j)
            i = j
            continue
        if c in "'\"`" or (c == "/" and prev in _JS_RE_PREV):
            q, j = c, i + 1
            while j < n:
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == q or (q != "`" and s[j] == "\n"):
                    break
                j += 1
            blank(i + 1, j)                    # keep the delimiters, blank the contents
            i = j + 1
            prev = q
            continue
        if not c.isspace():
            prev = c
        i += 1
    return "".join(out)


def _js_scan(blk, base):
    out = []
    for m in _JS_FN.finditer(_js_mask(blk)):   # match on the mask; body/hash/lines still from `blk` (same offsets)
        nm = m.group(1) or m.group(2)
        if not nm:
            continue
        end = _js_block_end(blk, m.end())
        if end < 0:
            continue
        body = blk[m.start():end + 1]
        ln = body.count("\n") + 1
        if ln > 900:
            continue
        out.append({"name": nm, "lang": "js", "line": base + blk[:m.start()].count("\n"),
                    "lines": ln,
                    "h": hashlib.md5(body.encode("utf-8", "replace")).hexdigest()[:12]})
    return out


# ⚠Minified files only get line counts, no function extraction — vendor output like `ace-builds/src-min`
#   covers the treemap with thousands of «one-line functions» (measured 2026-09-22 repo-A n=2,572).
#   The only test is «is there a very long line» — less wrong than extension·path rules.
STRUCT_MINIFIED_COL = 2000

# ── Java/Kotlin — no AST, so count «brace depth» directly ──────────────────────
# ★2026-09-22: projects whose core is Java were not seen at all (repo-B 1,675 files).
# ⚠The principle is «miss rather than catch wrongly» — blocks whose signature cannot be read are just skipped, and files with
#   mismatched depth are abandoned entirely (return `None` → the caller counts it as `skipped`). Generics `<>`·annotations·
#   lambdas·anonymous classes·nested classes break easily, and one file must not kill the whole thing.
_JAVA_NOTNAME = {"if", "for", "while", "switch", "catch", "synchronized", "return",
                 "new", "do", "else", "try", "finally", "assert", "throw", "case"}
_JAVA_CLSDECL = re.compile(r"\b(?:class|interface|enum|record|object)\s+(?!(?:class|interface)\b)([A-Za-z_$][\w$]*)")  # ⚠Kotlin `enum class X`
_JAVA_TAILID = re.compile(r"([A-Za-z_$][\w$]*)$")
_JAVA_NEWTAIL = re.compile(r"\bnew$")


def _java_sig(seg):
    """Declaration header fragment -> method name. None if unreadable (= that block is dropped).
    ⚠Annotations·generics are mixed in, so find «the last matching parenthesis» from the end and use the identifier before it."""
    s = seg.strip()
    j = s.rfind(")")
    if j < 0:
        return None
    tail = s[j + 1:].strip()
    # ⚠`:` = Kotlin return type (`fun f(x: Int): Int {`) — without it every typed Kotlin function was dropped.
    if tail and not tail.startswith(("throws", ":")):
        return None                        # `-> {` lambdas, tails after `= new X()`, etc.
    d, i = 0, j
    while i >= 0:
        if s[i] == ")":
            d += 1
        elif s[i] == "(":
            d -= 1
            if d == 0:
                break
        i -= 1
    if i < 0:
        return None
    head = s[:i].rstrip()
    m = _JAVA_TAILID.search(head)
    if not m:
        return None
    nm = m.group(1)
    if nm in _JAVA_NOTNAME:
        return None
    before = head[:m.start()].rstrip()
    if before.endswith(".") or _JAVA_NEWTAIL.search(before):
        return None                        # `new Foo() {` anonymous class
    # ⚠Drop annotation arguments first: `@GetMapping(value = "/x") void f() {` has `=` but is a method.
    while re.search(r"\([^()]*\)", before):
        before = re.sub(r"\([^()]*\)", " ", before)
    if "=" in before:
        return None                        # field initializer
    return nm


def _java_scan(src, lang="java"):
    """[{name,lang,line,lines,h}] or None (abandon the whole file).
    `name` is **Class.method** — same-named methods across classes are common.
    ⚠Only blocks starting at class-body depth are considered. Inside anonymous classes·static initializer blocks
      depth goes one level deeper, so they drop out naturally (deliberately so)."""
    n = len(src)
    i, line = 0, 1
    depth = 0
    buf = []                               # current declaration fragment holding «code only» without comments·strings
    seg_line = 1
    clses = []                             # [(name, body depth)]
    opens = []                             # [(depth, name, start line, start index)]
    out = []
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            if buf:
                buf.append(" ")            # ⚠a newline separates tokens (Kotlin has no `;`: `Marker\ndata` glued into one name)
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j < 0:
                return None
            line += src.count("\n", i, j)
            i = j + 2
            continue
        if c == '"':
            if src.startswith('"""', i):   # text block (Java 15+)
                j = src.find('"""', i + 3)
                if j < 0:
                    return None
                line += src.count("\n", i, j)
                i = j + 3
            else:
                i += 1
                while i < n and src[i] != '"':
                    if src[i] == "\\":
                        i += 1
                    elif src[i] == "\n":
                        return None        # unclosed string — the scanner is already out of sync
                    i += 1
                i += 1
            buf.append('"')
            continue
        if c == "'":
            i += 1
            while i < n and src[i] != "'":
                if src[i] == "\\":
                    i += 1
                elif src[i] == "\n":
                    return None
                i += 1
            i += 1
            buf.append("'")
            continue
        if c == "{":
            seg = "".join(buf)
            depth += 1
            mc = None
            for mc in _JAVA_CLSDECL.finditer(seg):   # last one owns the `{` (bodyless Kotlin decls precede it)
                pass
            if mc:
                clses.append((mc.group(1), depth))
            elif clses and depth == clses[-1][1] + 1:
                nm = _java_sig(seg)
                if nm:
                    opens.append((depth, clses[-1][0] + "." + nm, seg_line, i))
            buf = []
            i += 1
            seg_line = line
            continue
        if c == "}":
            if opens and opens[-1][0] == depth:
                _d, nm, ln0, i0 = opens.pop()
                body = src[i0:i + 1]
                out.append({"name": nm, "lang": lang, "line": ln0,
                            "lines": max(1, line - ln0 + 1),
                            "h": hashlib.md5(body.encode("utf-8", "replace")).hexdigest()[:12]})
            while clses and clses[-1][1] == depth:
                clses.pop()
            depth -= 1
            if depth < 0:
                return None
            buf = []
            i += 1
            seg_line = line
            continue
        if c == ";":
            buf = []
            i += 1
            seg_line = line
            continue
        if not c.isspace():
            if not buf:
                seg_line = line
            buf.append(c)
        elif buf:
            buf.append(" ")
        i += 1
    if depth != 0 or opens:
        return None
    return out


_GO_FN = re.compile(r"(?m)^func[ \t]+(?:\(([^)]*)\)[ \t]*)?([A-Za-z_]\w*)[ \t]*(?:\[[^\]\n]*\][ \t]*)?\(")


def _go_body_open(s, i):
    """Index of the body `{` after a Go signature starting inside its parameter list, or -1 (no body)."""
    depth, n = 1, len(s)
    while i < n:
        c = s[i]
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "\n" and depth == 0:
            return -1                          # ⚠Go needs `{` on the signature line — a newline means a bodiless decl
        elif c == "{" and depth == 0:
            if re.search(r"\b(?:interface|struct)[ \t]*$", s[max(0, i - 12):i]):
                j = _js_block_end(s, i)        # `interface{}` / `struct{...}` in a type, not the body
                if j is None or j < 0:
                    return -1
                i = j + 1
                continue
            return i
        i += 1
    return -1


def _go_scan(src):
    out = []
    for m in _GO_FN.finditer(src):
        recv = re.findall(r"[A-Za-z_]\w*", re.sub(r"\[.*", "", m.group(1) or ""))
        nm = (recv[-1] + "." if recv else "") + m.group(2)
        a = _go_body_open(src, m.end())
        end = _js_block_end(src, a) if a >= 0 else -1
        if end is None or end < 0:
            continue
        body = src[m.start():end + 1]
        ln = body.count("\n") + 1
        if ln > 900:
            continue
        out.append({"name": nm, "lang": "go", "line": src[:m.start()].count("\n") + 1, "lines": ln,
                    "h": hashlib.md5(body.encode("utf-8", "replace")).hexdigest()[:12]})
    return out


def _struct_flat_fns(rel, src):
    """Files without function units (JSP etc.) — **one file as one cell**. `line` is always 1."""
    return [{"name": os.path.basename(rel), "lang": "jsp", "line": 1,
             "lines": src.count("\n") + 1,
             "h": hashlib.md5(src.encode("utf-8", "replace")).hexdigest()[:12]}]


# ⚠Do not write the opening/closing script tags **as literals in the source** — this file itself embeds the screen JS
#   with that tag, so the gate's «embedded script extraction» and this very function read Python comments as JS
#   (measured 2026-09-22: node --check blew up on a Korean docstring). Hence the fragments are concatenated.
_STRUCT_SCRIPT = re.compile("<" + "script>(.*?)</" + "script>", re.S)
# ⚠Same concatenation trap as above: never a literal script tag in this file.
# ⚠Open and close are searched separately, never one `<script\b([^>]*)>(.*?)</script\s*>`: on an unclosed tag that
#   regex rescans to EOF from every later `<script` (quadratic; ★12000 tags = 4.5-13 s, now < 0.1 s).
_HTML_OPEN = re.compile("<" + r"script\b", re.I)
_HTML_CLOSE = re.compile("</" + r"script\s*>", re.I)
_HTML_JS_TYPE = re.compile(r"""\btype\s*=\s*["']?(?!module\b|text/javascript\b|application/javascript\b)""", re.I)


def html_scripts(s):
    """HTML -> same-length text with only inline script bodies kept (no `src=`, JS types only); the rest is blanked
    to spaces with newlines kept, so offsets and line numbers match the page."""
    out, at, pos = [], 0, 0
    while True:
        m = _HTML_OPEN.search(s, pos)
        gt = s.find(">", m.end()) if m else -1
        c = _HTML_CLOSE.search(s, gt + 1) if gt >= 0 else None
        if c is None:                      # no `>` or no close after it: no later tag can match either
            break
        pos, attrs = c.end(), s[m.end():gt]
        if re.search(r"\bsrc\s*=", attrs, re.I) or _HTML_JS_TYPE.search(attrs):
            continue
        out.append(re.sub(r"[^\n]", " ", s[at:gt + 1]))
        out.append(s[gt + 1:c.start()])
        at = c.start()
    out.append(re.sub(r"[^\n]", " ", s[at:]))
    return "".join(out)


def _struct_one_file(rel, src):
    """One file -> (line count, function list, skipped count). `.py` also looks at ast + embedded scripts."""
    if rel.endswith(STRUCT_JS_EXTS):       # ⚠minified check for js family only — long lines are normal in java
        for ln in src.split("\n", 400)[:400]:
            if len(ln) > STRUCT_MINIFIED_COL:
                return src.count("\n") + 1, [], 0
    skip = 0
    if rel.endswith(".py"):
        fns = _struct_py_fns(src)
        for m0 in _STRUCT_SCRIPT.finditer(src):
            fns += _js_scan(m0.group(1), src[:m0.start(1)].count("\n") + 1)
    elif rel.endswith(STRUCT_JAVA_EXTS):
        fns = _java_scan(src, "kt" if rel.endswith(".kt") else "java")
        if fns is None:                    # ⚠a broken file silently drops only that file
            fns, skip = [], 1
    elif rel.endswith(STRUCT_JSP_EXTS):
        fns = _struct_flat_fns(rel, src)
    elif rel.endswith(STRUCT_GO_EXTS):
        fns = _go_scan(src)
    elif not rel.endswith(STRUCT_JS_EXTS) and lang_for(rel) is not None:   # language plug-in (structure_plug); None = parse failure, like java
        sp = lang_for(rel)
        fns = sp["scan"](src) if sp["scan"] else []
        if fns is None:
            fns, skip = [], 1
        lg = plug_lang(sp, rel, src) if fns else ""
        for f in fns:
            f.setdefault("lang", lg)
    else:
        fns = _js_scan(src, 1)
    for f in fns:
        f["file"] = rel
    return src.count("\n") + 1, fns, skip
