# Changelog

## 0.2.0 - 2026-10-13

- Renamed from `folder-accounts` to Orbit (plugin `orbit`, repo `bugsterran/orbit`). Reinstall:
  `/plugin uninstall folder-accounts@<marketplace>`, then `/plugin marketplace add bugsterran/orbit` and
  `/plugin install orbit@orbit`.
- The command is now `orbit`. `claude-account` stays as an alias (`bin/claude-account`, launcher function).
- Unchanged on disk: `~/.claude-accounts`, the rc markers `# >>> folder-accounts >>>`,
  `~/.local/share/folder-accounts/`, `FA_PY`. An existing setup keeps working without changes.
- `add` always prints a dry run first and writes only with `--yes`. When the shell block is missing, that one
  dry run covers the folder and the rc block. `add --shell` adds a reinstall to the plan. `shell install` still works.
- «remember for this folder? (Y/n)»: Enter now remembers.
- The launcher prints `→ <name> (not signed in yet: type /login)` for an account with no sign-in.
  `resolve` adds a third field only when the launcher asks; two-field output still works.
- The registry is ignored when it is not yours or is writable by group or others. New registries are `0600`.
- Registry lines with an invalid label or a control character in the folder are ignored; such paths are refused on write.
- Writes are refused when `HOME` is not owned by the current user (sudo).
- `--copy` recreates top-level symlinks instead of following them.
- Sign-in state is a bounded byte scan of `.claude.json`; the file is no longer parsed.
- Security: temp files are created `0600` with `O_EXCL | O_NOFOLLOW` and removed on failure (a planted symlink
  is refused); the rc backup is not written through a dangling symlink; `--copy settings` warns that `env` /
  `apiKeyHelper` may hold tokens and writes the copy `0600`; `/account` pre-approves only `orbit list`, so `--yes`
  runs need permission.
- README: quick start, how it works, registry format, uninstall. New `SECURITY.md` and `LICENSE`.

Upgrading: run `orbit shell install --yes` once (or `add <name> --shell --yes`) to refresh the
stable copy of `accounts.py`. The sign-in hint needs it.

## 0.1.0

- Registry `~/.claude-accounts`: `add`, `rename`, `map`, `unmap`, `default`, `remove`, `list`.
- `add --dir` registers any folder; `add --copy` copies settings, agents, skills, commands and MCP servers
  from `~/.claude`, never overwriting and never copying credentials.
- Shell launcher for zsh and bash: `-A` > folder map > default > prompt > `~/.claude`.
- `shell install|uninstall`: one marked rc block, a one-time backup, a byte-identical round trip.
- SessionStart hook warns when a session runs under another account than its folder's map.
