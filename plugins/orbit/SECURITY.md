# Security

Orbit only chooses which config folder `claude` starts with. It never handles credentials.
The code is one Python file (`scripts/accounts.py`, stdlib only) and one shell function (`shell/launcher.sh`).

## What it touches

| Path | Read / write | When |
|---|---|---|
| `~/.claude-accounts` (registry) | read, write | every `claude` run reads it; `add` `rename` `map` `unmap` `default` `remove` and «remember for this folder» write it |
| account folders (`~/.claude-<name>` or `--dir`) | create, write | `add` creates a new folder; `--copy` copies into it, never overwriting |
| `settings.json` `agents/` `skills/` `commands/` in `~/.claude` | read | `add --copy` only |
| `mcpServers` from `~/.claude.json` (or the source folder's `.claude.json`) | read, write | `add --copy mcp` only; written to the new folder's `.claude.json` with no other keys |
| `.claude.json` of each account (`~/.claude.json` for `~/.claude`) | read | `list`, and `resolve` from the launcher; a byte scan for the `"oauthAccount":` key, never parsed, at most 64 MB; nothing from it is printed |
| `~/.zshrc` or `~/.bashrc` (or `--rc FILE`) | read, write | `shell install` / `uninstall` and the first `add --yes`; only the marked block |
| `<rc>.bak-folder-accounts` | write | once, before the first rc change |
| `~/.local/share/folder-accounts/accounts.py` | write | `shell install` and the first `add --yes`; a copy of the plugin's `accounts.py` |
| `/dev/tty` | read, write | the account prompt, only in an interactive terminal |
| `~/.claude-*` folder names | list | `list`, to show unregistered folders |
| SessionStart hook input | read | stdin JSON `cwd` and env `CLAUDE_CONFIG_DIR`; prints a warning, writes nothing |

Never touched: `.credentials.json`, the macOS keychain, OAuth tokens, `projects/` (conversations),
`history.jsonl`, `plugins/`. These names are skipped even inside a copied folder. There is no network
code and no subprocess call in `accounts.py`. The launcher runs only `python3` and `claude`.

## Permissions

- Registry: `0600` when created; an existing file keeps its mode.
- New account folder: `0700`. An existing folder is left as it is.
- `.claude.json` from `--copy mcp` and `settings.json` from `--copy settings`: `0600`. Other copied files keep their source mode.
- rc file: an existing file keeps its mode; a new one is `0644`. A symlinked rc keeps its link and the target is rewritten.
- Every write goes to `<file>.tmp-folder-accounts` first and is then renamed into place. The temp file is created
  `0600` with `O_EXCL | O_NOFOLLOW`, so an existing symlink there is refused, never written through.
- The rc backup is skipped when anything (even a dangling symlink) already has its name.

## How to audit

```
cat ~/.claude-accounts
sed -n '/# >>> folder-accounts >>>/,/# <<< folder-accounts <<</p' ~/.zshrc
orbit list
orbit shell uninstall            # dry run: shows what would be removed
diff ~/.local/share/folder-accounts/accounts.py <plugin>/scripts/accounts.py
```

## Threat notes

- **rc injection.** The rc block is fixed text: the markers, one `export FA_PY=...` line with a constant
  path, and the launcher file. No account name or path from the registry is ever written to the rc.
- **Registry hand edits.** Paths may contain spaces. A label that is not `a-z 0-9 _ -` (max 32) or a folder
  with a control character (tab, newline) is ignored. The launcher only ever uses the name and folder as
  quoted strings (`printf '%s'`, `CLAUDE_CONFIG_DIR="$dir"`); nothing is `eval`ed.
- **Someone else's registry.** The registry decides which `settings.json` and hooks you run with. It is
  ignored (primary `~/.claude` only) when it is not owned by you or is writable by group or others,
  for example under `sudo` with your `HOME`. `list` says so.
- **Symlinked account folders.** Folders are compared by real path. `add` refuses `/`, your home folder or
  any parent of it, and a folder already registered under another name, after resolving symlinks.
  `--copy` recreates symlinks instead of following them, both for the top-level items and inside folders.
- **Control characters.** A path with a control character (newline, tab, DEL) is refused on every write
  (`add --dir`, `map`, «remember for this folder»), so it cannot add lines to the registry.
- **sudo.** Every write is refused when `HOME` is not owned by the current user, so files never end up
  owned by root in your home. Reading (`list`, `resolve`) still works.
- **MCP env values and settings.** `--copy mcp` copies server `env` values as they are, and `--copy settings`
  copies `env` and `apiKeyHelper`. They may hold tokens; the dry run says so and both target files are `0600`.
- **Skill pre-approval.** `/account` pre-approves only `orbit list`. Every other command, and every `--yes`,
  goes through the normal permission prompt, so the model cannot write an rc or folder unasked.
- **Platform.** macOS and Linux with zsh or bash only. Windows is not supported.

## Uninstall

See the README «Uninstall». Run `/logout` per account first. Account folders (`.credentials.json`), macOS keychain
items `Claude Code-credentials-*`, `<rc>.bak-folder-accounts` (may hold exported tokens) and
`~/.local/share/folder-accounts/` stay until you delete them.

## Reporting

Open an issue with the steps and the output of `orbit list`. Remove any paths or names you do not want public.
