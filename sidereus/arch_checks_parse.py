"""Severity names and per-rule help cleaning shared by the security checks (sidereus/sec_checks.py,
sidereus/arch_checks.py). `help` = {desc, url} from a tool's own rule metadata (generic rule text, never the
per-finding message). Stdlib only; no sidereus imports.
"""
import re

SEVS = ("critical", "high", "medium", "low")   # most severe first; the single owner of the level names
LEGACY = {"error": "high", "warning": "medium"}   # v1 checks files and old security-log lines
SEV_RANK = {s: i for i, s in enumerate(SEVS)}
HELP_DESC_MAX, HELP_URL_MAX = 140, 300
_URL_BAD = re.compile(r"[\s\x00-\x1f\x7f\"'<>\\]")


def level(s):
    """A level name as is, a legacy name (error/warning) mapped, anything else None."""
    if not isinstance(s, str):
        return None
    return s if s in SEV_RANK else LEGACY.get(s)


def zero():
    """Fresh {level: 0} counter."""
    return {s: 0 for s in SEVS}


def clean_help(desc, url):
    """{desc, url} with desc control-free and <= HELP_DESC_MAX, url https-only and <= HELP_URL_MAX; None if both empty."""
    d = "".join(c for c in desc if ord(c) >= 32 and ord(c) != 127).strip()[:HELP_DESC_MAX] if isinstance(desc, str) else ""
    u = url if isinstance(url, str) and url.startswith("https://") and len(url) <= HELP_URL_MAX \
        and not _URL_BAD.search(url) else ""
    return {"desc": d, "url": u} if d or u else None
