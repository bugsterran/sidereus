---
name: sidereus-test
description: How to load, measure and unit-test the Sidereus viewer (~/.mailbox-mcp) without touching the running server — importlib recipe, which module to patch, tests/run.sh and single-file runs. Use when writing or running Sidereus tests or measuring before/after a change.
---

# Testing Sidereus

`main()` sits behind `if __name__ == "__main__"`, so loading the file as a module **starts none of the 8 background threads
and leaves the running server alone.** This is the standard way to measure before/after a change.

```python
import importlib.util, sys
spec = importlib.util.spec_from_file_location("cs", "chat_server.py")   # run from the repo root
cs = importlib.util.module_from_spec(spec); sys.modules["cs"] = cs
spec.loader.exec_module(cs)
```

- `cs` holds only the names `chat_server.py` uses directly (`Handler` · `state` · `PAGE` · the 27 it imports) — re-exports were removed on 09-23.
  Read every other name from its owning module (`sidereus("quota").quota`). Function bodies live in `sidereus/<module>.py`.
- ⚠To test with a changed value, `cs.X = …` has no effect — patch **the module of the function that reads the value** (`f.__globals__`, e.g. `sidereus.live.X = …`).

## Running

```
bash tests/run.sh                                     # all
/usr/bin/python3 -m unittest tests.test_quota -v      # one file
```

- Loader: `load()` in `tests/_load.py` · `sidereus("burn")` — runs the importlib recipe above only once.
- ⚠Tests never use live files, the clock or the network — monkeypatch the module attributes of any function that reads or writes.
- Always `/usr/bin/python3` (3.9.6, what launchd runs).
