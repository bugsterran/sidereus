"""Harness «Next step» guides (GET /api/verdict-guide): one file per verdict id in docs/verdicts/<id>.md (+ <id>.ko.md).

Format: fixed `## Meaning` / `## Why it matters` / `## Who acts` (self|ai|owner) / `## Next step` headings, optional
`## Safe to ignore when` (required for owner) and `## Pipeline` (a pipeline name). A fork adds a verdict guide by adding a file.
⚠Read from ASSET_DIR (the repo or the installed bundle), never HOME; files are read once per language and cached.
⚠A bad file (bad id, missing field, bad `who`, too large) is skipped whole; ko falls back to en per id.
"""
import os
import re

from sidereus.config import ASSET_DIR

VG_DIR = os.path.join(ASSET_DIR, "docs", "verdicts")
VG_ID = re.compile(r"^[a-z][a-z0-9_-]{0,40}$")
VG_PIPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
VG_FIELD_MAX = 300
VG_READ_MAX = 16 * 1024
VG_FILES_MAX = 200
VG_LANGS = ("en", "ko")
VG_WHO = ("self", "ai", "owner")
VG_HEADS = {"meaning": "Meaning", "why": "Why it matters", "who": "Who acts", "next": "Next step",
            "ignore": "Safe to ignore when", "pipeline": "Pipeline"}
_VG_KEY = dict((v.lower(), k) for k, v in VG_HEADS.items())
_VG_CACHE = {}


def parse(text):
    """{meaning, why, who, next, ignore, pipeline} from one guide file, or None when a required field is missing or bad."""
    out, cur = {}, None
    for ln in text.splitlines():
        if ln.startswith("## "):
            cur = _VG_KEY.get(ln[3:].strip().lower())
            if cur is not None:
                out[cur] = []
            continue
        if ln.startswith("# "):
            cur = None
        elif cur is not None and ln.strip():
            out[cur].append(ln.strip())
    g = dict((k, " ".join(v)[:VG_FIELD_MAX]) for k, v in out.items())
    if any(not g.get(k) for k in ("meaning", "why", "who", "next")) or g["who"] not in VG_WHO:
        return None
    if g["who"] == "owner" and not g.get("ignore"):
        return None
    if g.get("pipeline") and not VG_PIPE.fullmatch(g["pipeline"]):
        return None
    return {"meaning": g["meaning"], "why": g["why"], "who": g["who"], "next": g["next"],
            "ignore": g.get("ignore") or "", "pipeline": g.get("pipeline") or ""}


def _read(lang):
    """{id: guide} for files of one language (en = <id>.md, ko = <id>.ko.md)."""
    try:
        names = sorted(os.listdir(VG_DIR))[:VG_FILES_MAX * 2]
    except OSError:
        return {}
    out = {}
    for f in names:
        if lang == "en":
            if not f.endswith(".md") or f.endswith(".ko.md"):
                continue
            vid = f[:-3]
        elif f.endswith(".ko.md"):
            vid = f[:-6]
        else:
            continue
        p = os.path.join(VG_DIR, f)
        if not VG_ID.fullmatch(vid) or os.path.islink(p) or not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as fh:
                raw = fh.read(VG_READ_MAX + 1)
            if len(raw) > VG_READ_MAX:
                continue
            g = parse(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if g:
            out[vid] = g
    return out


def load(lang="en"):
    """{id: {meaning, why, who, next, ignore, pipeline}} for `lang` (unknown = en); ko falls back to en per id."""
    lang = lang if lang in VG_LANGS else "en"
    key = (VG_DIR, lang)
    if key not in _VG_CACHE:
        out = _read("en")
        if lang != "en":
            out.update(_read(lang))
        _VG_CACHE[key] = out
    return dict(_VG_CACHE[key])
