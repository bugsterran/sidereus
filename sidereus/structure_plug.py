"""Language plug-in registry for the Structure tab: one spec per language, registered by sidereus/structure_lang_*.py.

Pure apart from `plug_load` (imports the plug-in modules). `structure_scan` loads them at import; the treemap
(`structure_lang._struct_one_file`) falls back to `lang_for(rel)` after its built-in languages.
Owns `LANGS` (name -> spec), `PLUG_DIR`, `_loaded`. Metadata only: hooks return names, kinds, paths, lines.
"""
import fnmatch
import glob
import importlib
import os
import re
from sidereus.warn import warn_once

PLUG_DIR = os.path.dirname(os.path.abspath(__file__))
PLUG_GLOB = "structure_lang_*.py"      # ⚠every sidereus file matching this is imported as a plug-in
LANGS = {}
_loaded = []
# exts · lang(rel, src) or str -> row lang · scan(src) -> treemap fns (None = parse failure) ·
# test/gen (regex, str or rel -> bool) · test_dirs (regex or dir names) · skip (dir names, fnmatch globs)
_KEYS = frozenset(("exts", "lang", "scan", "test", "test_dirs", "skip", "gen"))
_RX = ("test", "test_dirs", "gen")


def lang_register(name, spec):
    """Register language `name` (replaces an earlier spec of that name). Unknown keys or no `exts` raise ValueError."""
    bad = set(spec) - _KEYS
    if bad:
        raise ValueError("unknown plug-in spec keys: %s" % ", ".join(sorted(bad)))
    exts = tuple(spec.get("exts") or ())
    if not exts or not all(isinstance(e, str) and e.startswith(".") for e in exts):
        raise ValueError("plug-in %s: exts must be a non-empty tuple of '.ext'" % name)
    s = dict((k, None) for k in _KEYS)
    s.update(spec)
    s.update(name=name, exts=exts, skip=tuple(spec.get("skip") or ()))
    for k in _RX:                               # regex · pattern string · rel -> bool · (test_dirs) dir names
        v = s[k]
        if isinstance(v, str):
            v = s[k] = re.compile(v)
        if isinstance(v, (tuple, list, frozenset, set)):
            names = frozenset(x.lower() for x in v)
            s["_" + k] = (lambda nm: lambda seg: seg.lower() in nm)(names) if names else None
        else:
            s["_" + k] = v.search if hasattr(v, "search") else v
    LANGS[name] = s
    return s


def lang_for(rel):
    """Spec owning `rel` by extension (longest matching ext wins), or None."""
    best, n = None, 0
    for s in LANGS.values():
        for e in s["exts"]:
            if len(e) > n and rel.endswith(e):
                best, n = s, len(e)
    return best


def plug_exts():
    """All plug-in extensions, registration order, no repeats."""
    out = []
    for s in LANGS.values():
        out += [e for e in s["exts"] if e not in out]
    return tuple(out)


def plug_lang(spec, rel, src):
    """Row lang of one file (spec `lang`, default the plug-in name)."""
    return spec["lang"] if isinstance(spec["lang"], str) else spec["lang"](rel, src) if spec["lang"] else spec["name"]


def plug_test_pats():
    """Pattern strings of every plug-in `test` regex (structure_scan joins them into STRUCT_TEST_FILE)."""
    return [s["test"].pattern for s in LANGS.values() if isinstance(s["test"], re.Pattern)]


def plug_is_test(rel):
    """Test file by its own plug-in only: `test` on the path, `test_dirs` on each directory segment."""
    s = lang_for(rel)
    if s is None:
        return False
    if s["_test"] and s["_test"](rel):
        return True
    return bool(s["_test_dirs"]) and any(s["_test_dirs"](p) for p in rel.split("/")[:-1])


def plug_skip(rel):
    """True when the file's own plug-in drops it: a `skip` directory segment (fnmatch globs) or a `gen` match."""
    s = lang_for(rel)
    if s is None:
        return False
    if s["skip"] and any(fnmatch.fnmatchcase(p, g) for p in rel.split("/")[:-1] for g in s["skip"]):
        return True
    return bool(s["_gen"]) and bool(s["_gen"](rel))


def _import(mod):
    return importlib.import_module(mod)


def plug_load():
    """Import sidereus/structure_lang_*.py in sorted order, once each; a failing module is skipped with warn_once."""
    for p in sorted(glob.glob(os.path.join(PLUG_DIR, PLUG_GLOB))):
        mod = "sidereus." + os.path.basename(p)[:-3]
        if mod in _loaded:
            continue
        _loaded.append(mod)
        try:
            _import(mod)
        except Exception as e:      # ⚠one broken plug-in must not take the Structure tab down
            warn_once("plug:" + mod, "Structure language plug-in failed to load: {mod} ({err}) — that language is skipped",
                      vars={"mod": mod, "err": type(e).__name__})
    return list(_loaded)
