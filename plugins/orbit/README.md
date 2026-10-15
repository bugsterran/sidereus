# Orbit

Pick a Claude Code account by folder. Each account is its own config folder (`CLAUDE_CONFIG_DIR`);
a small shell function picks the right one when you type `claude`.

## Quick start

1. Install the plugin:
   ```
   /plugin marketplace add bugsterran/orbit
   /plugin install orbit@orbit
   ```
2. Add an account: `/account add work`. It shows what it will write (the folder `~/.claude-work`
   and, the first time, the launcher block in your shell rc), asks once, then does it.
3. Open a new shell and run `claude` anywhere. The first run in a folder asks which account to use
   and remembers it. A new account prints `→ work (not signed in yet: type /login)`.

## How it works

- One account is one config folder. `~/.claude` stays your primary account, named `default`.
- `claude` is a shell function. It asks `accounts.py resolve` for a folder, sets
  `CLAUDE_CONFIG_DIR`, and runs the real `claude` with your arguments.
- Order: `claude -A <name>` > nearest folder map > `default` line > the only account > a prompt
  (terminal only) > `~/.claude`. An exported `CLAUDE_CONFIG_DIR` wins unless you pass `-A`.
- The prompt asks «remember for this folder? (Y/n)». Enter remembers. `claude -p` and non-terminal
  runs never prompt.
- The shell block sits between `# >>> folder-accounts >>>` and `# <<< folder-accounts <<<` in
  `~/.zshrc` or `~/.bashrc`. It sources the launcher and points `FA_PY` at a stable copy of
  `accounts.py` in `~/.local/share/folder-accounts/`. These names predate the rename to Orbit and are
  kept so existing installs keep working.
- A SessionStart hook warns when a session runs under a different account than its folder's map.

## More

| Command | What it does |
|---|---|
| `add <name> [--dir PATH]` | Register a folder (default `~/.claude-<name>`). The name is only a label. |
| `add <name> --copy settings,agents,skills,commands,mcp` | Copy those from `~/.claude`, never overwriting. |
| `add <name> --shell` | Also reinstall the shell block (after a plugin update). Still needs `--yes`. |
| `rename <old> <new>` | Relabel; maps and default follow. The folder is not moved. |
| `map [folder] <name>` / `unmap [folder]` | Pin a folder and everything below it. |
| `default <name>` | Account for folders with no map. |
| `list` | Accounts, maps, sign-in state, unregistered `~/.claude-*` folders. |
| `remove <name>` | Unregister. The folder is kept. |
| `shell install` / `shell uninstall` | Add or remove the rc block on its own. |
| `claude -A <name>` | One-off override. |

`add` and `shell` print a dry run first; add `--yes` to apply. Outside Claude Code the same
commands run as `orbit ...` (`claude-account` still works as an alias). Sign in once per account with `/login`.

## Registry

`~/.claude-accounts`, plain text, one entry per line. Edit it by hand if you like; comments and
unknown lines are kept.

```
# my accounts
account default ~/.claude
account work ~/.claude-work
map ~/src/acme work
default work
```

## What it touches

See [SECURITY.md](SECURITY.md) for the full table. In short: the registry, the account folders you
add, one marked block in your rc file (backed up once), and a copy of `accounts.py`. It reads
`.claude.json` only to see whether an `oauthAccount` key exists. It never reads or copies
credentials, the keychain, or history, and makes no network calls.

## Limits

- macOS and Linux with zsh or bash only. Windows is not supported.
- Terminal CLI only. Desktop and the VS Code extension ignore `CLAUDE_CONFIG_DIR` (claude-code #25762, #30538).
- Plugins and marketplaces partly ignore it (#15071); install plugins per account. Sharing one `plugins` dir across accounts
  also shares plugin caches that are not per account (e.g. the oh-my-claudecode HUD can show another account's usage).
- A new account folder starts empty. `--copy mcp` copies MCP server `env` values too, and `--copy settings` copies
  `env` and `apiKeyHelper`; both may hold tokens. Both copies are `0600`.
- Credentials are never copied or swapped. Each account signs in on its own.
- ⚠ From another account folder, `~/.claude/CLAUDE.md` is just a parent-directory file: Claude Code reads it as a project
  `CLAUDE.md` for every folder under home and then skips `AGENTS.md`. In that account's `settings.json` add
  `"claudeMdExcludes": ["/Users/<you>/.claude/CLAUDE.md"]` and copy the file into the account folder instead of `@import`ing it
  (the exclude also drops an import). Never put that exclude in `~/.claude/settings.json`: it drops your global rules there.

## Alternatives

- [ftery0/claude-account-switch](https://github.com/ftery0/claude-account-switch): switch accounts by command.
- direnv or mise: `export CLAUDE_CONFIG_DIR=~/.claude-work` in the folder's `.envrc`.

This plugin adds the folder map, «remember for this folder», the mismatch warning and `list`.

## Updating

After `/plugin update`, run `orbit shell install --yes` once. The launcher runs a stable copy of
`accounts.py` in `~/.local/share/folder-accounts/`, and only this refreshes it (and the rc block).

## Uninstall

Run `/logout` in each account first, so its sign-in is revoked rather than left on disk.

```
orbit shell uninstall --yes               # removes only the marked block
rm ~/.claude-accounts                     # the registry
rm -r ~/.local/share/folder-accounts      # the stable copy
/plugin uninstall orbit@orbit
```

These stay and must be deleted by hand:

- Account folders (`~/.claude-work` ...). They may hold `.credentials.json`, `.claude.json` and copied settings.
- macOS keychain items `Claude Code-credentials-*` created by each account's sign-in (Keychain Access).
- `~/.zshrc.bak-folder-accounts` / `~/.bashrc.bak-folder-accounts`: a copy of your rc from before the first install.
  It may contain tokens you exported there.
