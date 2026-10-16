# Orbit

Keeps your Claude Code accounts from mixing: enter a folder, type `claude`, and it runs under that
folder's account. Each account is its own config folder (`CLAUDE_CONFIG_DIR`); a small shell function
picks it, and a session-start hook warns when a session runs under a different account than the
folder's map (folders with no map get no warning).

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

## Other tools

| Tool | Form | Per-folder pin | Notes |
|---|---|---|---|
| Orbit | Claude Code plugin + shell function | `map` in the registry; in a terminal, an unmapped folder with no default and more than one account prompts once, Enter/Y saves it | Plain `claude`. Mismatch warning. No auto-switch, no history sharing, never reads credentials. |
| [claude-swap](https://github.com/realiti4/claude-swap) | CLI `cswap` + TUI | `cswap map`, used by `cswap run`; subfolders follow the nearest mapped parent | Auto-switches near the 5h/7d limit (`cswap auto`, default 90%). Optional `--share-history`. macOS, Linux, Windows. |
| [claude-code-profiles](https://github.com/quinnjr/claude-code-profiles) | Shell wrapper `claude-profile` | `.claude-profile` file, nearest wins, switches on `cd` | One config folder per profile. |
| [claude-account-switch](https://github.com/ftery0/claude-account-switch) | npm, `CLAUDE_CONFIG_DIR` | No; picker or `cpf <name>` | Switch by command. |
| [claude-account-switcher](https://github.com/ukogan/claude-account-switcher) | Shell wrapper + `/switch-profile`, `/whoami` | No; `claude <profile>` or per shell | Shares settings via symlinks. |
| [claude-switch](https://github.com/SIRTHEO/claude-switch) | npm `@sirtheo/claude-switch` | Committed `.claude-switch` per repo; can match accounts by email domain | Aimed at teams sharing one repo rule. |
| direnv / mise | Env loader | One line: `export CLAUDE_CONFIG_DIR=~/.claude-work` in `.envrc`, or under `[env]` in `mise.toml` | No prompt, no mismatch warning. |

claude-swap helps you get more out of several accounts (rotation, shared history); Orbit keeps them
apart. Closest to Orbit is claude-code-profiles (also a `claude()` wrapper, default profile, Windows,
a skills pool; it covers more platforms and features). Orbit keeps folder maps in one registry
(`~/.claude-accounts`) and writes nothing into your project folders, so a work repo gets no file to
commit or ignore; it adds the mismatch warning at session start and the remember-once prompt, and
installs as a Claude Code plugin. Use claude-swap if you want rotation, claude-switch if a team needs one committed repo rule,
direnv or mise if you already use them and need nothing more.

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
