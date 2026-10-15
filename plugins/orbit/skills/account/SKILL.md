---
name: account
description: Pick a Claude Code account (CLAUDE_CONFIG_DIR folder) per project folder. `add <name>` registers an account and, the first time, installs the shell launcher; also rename, map, unmap, default, list, remove, shell install|uninstall.
argument-hint: add <name> | list | map|unmap|default|rename|remove|shell ...
disable-model-invocation: true
allowed-tools: Bash(orbit list), Bash(orbit)
---

Run the Orbit CLI from the project folder and relay its output to the user verbatim.

1. Run `orbit $ARGUMENTS` with the Bash tool from the project folder.
2. If the output starts with `dry run` (`add`, `shell install`, `shell uninstall`),
   nothing was written. Show the whole dry run (folder and rc block together), ask the user once whether to apply it,
   and only after they agree run the same command again with `--yes` appended.
3. After a successful `add`, tell the user to open a new shell and run `claude` in any folder.
4. With no arguments, run `orbit list`.

Only `orbit list` is pre-approved; every other command, and any `--yes` run, goes through the normal permission prompt.

Report only what the CLI printed. Do not read, print or move any file inside a config folder yourself.
