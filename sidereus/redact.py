"""Mask secrets in raw text the work log carries (tool results, args, says, prompt)."""
import re

MASK = "•••"

_PEM = re.compile(r"(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----)[\s\S]*?(-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)")
# ⚠Order matters: sk-ant- before generic sk-, so the kept prefix is the specific one.
_TOKENS = re.compile(
    r"(?P<p>sk-ant-|sk-(?:proj-)?|ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|xox[abposr]-|AKIA|ASIA)"
    r"[A-Za-z0-9_\-]{8,}")
_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}")
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=\-]{6,}")
_NAME = r"[A-Za-z0-9_.\-]*(?:key|secret|token|passw(?:or)?d|credential|auth)[A-Za-z0-9_.\-]*"
_JSONKV = re.compile(r"(?i)(\"" + _NAME + r"\"\s*:\s*\")((?:[^\"\\]|\\.)+)(\")")
_ENVKV = re.compile(r"(?i)(\b" + _NAME + r"\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s\"',;&|]+)")
# URL userinfo password (postgresql://user:PASS@host): the user name stays, the password is masked.
#   ⚠No keyword hint in a DSN, so _HINT must match "://" too or the pre-check skips it.
_USERINFO = re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^\s/:@\"'<>]*:)([^\s/@\"'<>]+)(@)")
_HINT = re.compile(r"(?i)sk-|gh[pousr]_|github_pat_|xox|AKIA|ASIA|eyJ|bearer|PRIVATE KEY|key|secret|token"
                   r"|passw|credential|auth|://")


def redact(s):
    """Return s with secret values replaced by MASK (prefix / name kept). Non-str passes through."""
    if not isinstance(s, str) or not s or not _HINT.search(s):   # cheap pre-check: most lines skip all regexes
        return s
    s = _PEM.sub(lambda m: m.group(1) + MASK + (m.group(2) or ""), s)
    s = _USERINFO.sub(lambda m: m.group(1) + MASK + m.group(3), s)
    s = _TOKENS.sub(lambda m: m.group("p") + MASK, s)
    s = _JWT.sub("eyJ" + MASK, s)
    s = _BEARER.sub(lambda m: m.group(1) + MASK, s)
    s = _JSONKV.sub(lambda m: m.group(1) + MASK + m.group(3), s)
    s = _ENVKV.sub(lambda m: m.group(1) + MASK, s)
    return s


def redact_rooms(rooms):
    """Copy of a rooms.json dict with each room `topic` redacted (free text typed by people/agents, shown as a label)."""
    if not isinstance(rooms, dict):
        return rooms
    return {k: (dict(r, topic=redact(r["topic"])) if isinstance(r, dict) and r.get("topic") else r)
            for k, r in rooms.items()}


def redact_lines(lines):
    """Per-line redact, plus a joined pass so multi-line PEM blocks spanning lines are masked too."""
    if not lines:
        return lines
    joined = "\n".join(x if isinstance(x, str) else "" for x in lines)
    if "PRIVATE KEY-----" in joined:
        return redact(joined).split("\n")
    return [redact(x) for x in lines]


def redact_work(payload):
    """Redact every raw text field of a session_work/agent_work payload in place; returns it."""
    if not isinstance(payload, dict) or not payload.get("ok"):
        return payload
    for k in ("prompt", "desc"):
        payload[k] = redact(payload.get(k))
    for sy in payload.get("says") or ():
        if isinstance(sy, dict):
            sy["text"] = redact(sy.get("text"))
    for st in payload.get("steps") or ():
        if not isinstance(st, dict):
            continue
        for k in ("arg", "targ"):
            if k in st:
                st[k] = redact(st[k])
        for ed in ([st["edit"]] if isinstance(st.get("edit"), dict) else []) + list(st.get("edits") or ()):
            if isinstance(ed, dict):
                for k in ("old", "new"):
                    if isinstance(ed.get(k), str):
                        ed[k] = "\n".join(redact_lines(ed[k].split("\n")))
        r = st.get("res")
        if isinstance(r, dict) and r.get("lines"):
            r["lines"] = redact_lines(r["lines"])
    return payload
