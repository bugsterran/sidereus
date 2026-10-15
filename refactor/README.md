# refactor/ — per-stage equivalence proof tools

Tools that measure that each stage of the `chat_server.py` split (1 PAGE extraction · 2 JS split · 3 Python modules) did not change behaviour.
⚠`snap/` holds live metadata — it is gitignored and never uploaded anywhere.

```
/usr/bin/python3 refactor/snap.py take base          # once, before stage 1 (already taken 2026-09-23)
# ... apply stage N, gates pass, orchestrator restarts the server ...
/usr/bin/python3 refactor/snap.py take stageN        # reuses base/params.json (same cwd/tid/sha inputs)
/usr/bin/python3 refactor/snap.py diff base stageN   # exit 0 = equivalent
```

- **pages** — body sha256 of `/` `/diff` `/work` `/brdiff`. If the bytes differ, it compares the «assembled» page with same-origin `<script src>`·stylesheet `<link>` inlined (for the stage 2 JS split). If still different, a 40-line unified diff.
- **api** — status · Content-Type · JSON **shape** (key set and types per path) of 22 `/api/*` routes + 4 error paths (400·404). Values are not compared.
- **names** — loads the modules with importlib (no threads start) and writes top-level names and kinds to `names.txt`. A missing name or a changed kind is a failure. ⚠The 09-23 re-export removal drops 656 names versus base (intended) — after it, compare snaps with each other only. ⚠Since 09-25 the scope is the union of chat_server + every loaded `sidereus.*` (by name; moving between modules is not a difference) · first line of `names.txt` is `# scope:` — snaps with different scopes get a warning.
- **shots** — screenshots in `snap/<name>/shots/` are manual (playwright, 1600x1000). The list is `shots.md`. No pixel comparison — compare by eye.

Normalisation (volatile values):
- Page: `const MY_BUILD = '<12hex>'` — it is sha256(PAGE), so it changes whenever the PAGE bytes change. The raw value is recorded in `meta.json` and masked in the comparison.
- Shape: `null` is compatible with any type · if one side is an empty array/map, paths below it are ignored · a dict whose keys are not identifiers folds into a data map (`{*}`).
- Optional keys in `volatile.json`: `/api/branches` `$.cached` (cache-hit flag) · `/api/state` `$.saver.stage/cap/pct` (varies with saver mode state).
- ⚠If a new difference comes from live state (confirmed in code), add it to `volatile.json`. If it comes from the refactor, fix it — do not grow the list to cover it.
