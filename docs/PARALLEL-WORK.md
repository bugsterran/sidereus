# Parallel workspaces

**English** · [Korean](PARALLEL-WORK.ko.md)

The Branches tab builds commands for running several branches at once, each in its own worktree and session.
Sidereus only copies the command to the clipboard; you run it in a terminal.

## Rules

- Sidereus never runs a shell, git or a session. Claude Code starts sessions (`claude -w <name> --tmux` creates a worktree, starts a session and opens a tmux/iTerm2 pane); Sidereus watches them.
- ⚠ No endpoint that spawns processes from the page. With Host and Origin checks, local HTTP would still be a path to remote code execution.
- ⚠ No checkout, merge, rebase or push. They change the working folder under a running agent. Use a terminal or Claude.

## Steps

| Step | You | Sidereus |
|---|---|---|
| Start | «＋ Parallel work», enter a name, paste the command into a terminal | `git worktree add … && claude` (see below) or `claude -w <name> --tmux` |
| Work | give each pane its task | worktree cards (sessions, 5-hour share, uncommitted, ahead/behind), attention list, «Conflict risk» |
| Merge | merge or open a PR from a terminal or Claude | «↑N» ahead of base on the card, session and cost per commit |
| Clean up | paste the cleanup command | `git -C <repo> worktree remove <path>` |

## git-flow

The form defaults to git-flow. Prefixes and the develop/master names come from `git flow init` (`gitflow.*`), else the defaults below.

| Type | Branch | Based on | Card compares to · PR target |
|---|---|---|---|
| feature | `feature/<name>` | develop | develop · develop |
| bugfix | `bugfix/<name>` | develop | develop · develop |
| release | `release/<name>` (e.g. `1.4.0`) | develop | master · master + develop |
| hotfix | `hotfix/<name>` | master | master · master + develop |

```sh
git -C '<repo>' worktree add '<repo>.wt/<type>-<name>' -b '<branch>' '<base>' && cd '<folder>' && claude
```

- ⚠ No local develop: the branch is based on master and the form shows «no develop — branching from <master>».
- develop or master only on the remote: `--no-track` is added and the form shows «no local branch — branching from remote <base>».
- «claude -w (from HEAD)» gives `cd '<repo>' && claude -w <name> --tmux`, for repos without git-flow.

## Form and cleanup

- «＋ Parallel work» sits next to the repo chip: one name field and a copy button.
- ⚠ Names: `[a-z0-9._-]`, starting with a letter or digit; no leading or trailing `.`, no `..`, no `.lock`. Anything else blocks the copy, because the shell parses the pasted command.
- A name that matches an existing worktree or branch gets a warning; copying still works.
- «Cleanup cmd» appears only on a non-main worktree card with no session.
- ⚠ It never adds `--force`. With uncommitted files the card shows «N uncommitted — removing loses them», and git refuses the removal.

## Not included

| Feature | Reason |
|---|---|
| Running commands from the page | path to remote code execution |
| A worktree per task, an agent picker | that is what Orca (stablyai/orca) and Conductor do |
| Commit search, blame, branch compare | GitKraken and the terminal do this |

Sidereus adds the view across sessions, however they were started (`claude -w`, Orca, a hand-made worktree):
quota share per worktree, sessions that need you, cross-session conflict alerts, the shared mailbox.

Code: `web/js/89-branch-worktree.js` (`brPw*`, `brWrmHtml`, `brWtHtml`, `brWtMeta`), `sidereus/git_wt.py` `wt_signals`.
