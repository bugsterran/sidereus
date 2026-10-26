# First-run checklist

Install to the first lit pipeline stage, per OS. Source: [GETTING-STARTED.md](../GETTING-STARTED.md) (#25).
⚠Action counts are estimates read from the docs and UI code, not from a real run. Confirm each with a timed run on a clean machine; the reduction target is set after that.
Prerequisites (Python 3.9+, Git, Claude Code) are not counted.

## macOS — ~14 actions (typed 5 · clicks ~8 · typed field 1)

1. `pipx install git+https://github.com/bugsterran/sidereus`
2. `sidereus start --open` — the viewer opens on Pipelines.
3. In Claude Code: `/plugin marketplace add bugsterran/sidereus`
4. `/plugin install sidereus@sidereus`
5. `claude` in the project folder (new session, so the plugin hooks load).
6. Viewer: pick the project.
7. «+ New pipeline» or «Start from a template» → «Open draft» → «Save this draft» → «Confirm — create» (4 clicks, 1 typed field: the name).
8. Open «Run» → «Send a run request» → «Confirm — send» (3 clicks).
9. Done when the session picks up the request and the first stage lights.

## Windows — ~16 actions (macOS + 2)

1. Same as macOS 1–2 (PowerShell; no pipx yet: `py -m pip install --user pipx`, `py -m pipx ensurepath`, reopen).
2. Before the plugin: `setx SIDEREUS_PYTHON py`, then close and reopen PowerShell and Claude Code (+2).
   ⚠Without it `claude mcp list` shows `plugin:sidereus:sidereus ... ✘ Failed to connect`.
3. Same as macOS 3–9. Git for Windows is required (the plugin hooks run through Git Bash).

## Linux — ~14 actions (same as macOS)

1. Same steps as macOS 1–9; `python3 -m pip install --user pipx` if pipx is missing.
2. ⚠Not measured on a real machine yet; CI runs only the demo smoke test (`.github/workflows/ci.yml`).

## Headline features visible — per OS

⚠Tick each on a real run; a feature that is off on one OS must show here, not hide in a doc line.

| Feature | macOS | Windows | Linux |
|---|---|---|---|
| Sessions (list, timeline) | yes | yes (2026-10-17) | not measured |
| Pipelines (stages light) | yes | not measured | not measured |
| Structure (map, sizes) | yes | not measured | not measured |
| Quota (5h/7d in the status bar, or its reason) | yes (keychain) | `.credentials.json`, not measured | `.credentials.json`, not measured |
