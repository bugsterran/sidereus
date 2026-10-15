"""Svelte language plug-in: puts `.svelte` in the Structure walk and treemap (script blocks, lines kept).
Rows carry lang ts/js; this spec only adds the extension, the treemap scan and the skip dirs.
⚠Loaded while `structure_scan` is importing: imports only `structure_plug`/`structure_lang`.
"""
import re
from sidereus.structure_lang import _js_scan, html_scripts
from sidereus.structure_plug import lang_register

_TS = re.compile("<" + r"script\b[^>]*\blang\s*=\s*[\"']ts[\"']", re.I)


def svelte_scan(src):
    """Treemap functions of the script blocks (markup blanked, so line numbers match the file)."""
    return _js_scan(html_scripts(src), 1)


lang_register("svelte", {"exts": (".svelte",), "scan": svelte_scan,
                         "lang": lambda rel, src: "ts" if _TS.search(src) else "js",
                         "test": r"\.(?:test|spec)\.svelte$", "skip": (".svelte-kit",)})
