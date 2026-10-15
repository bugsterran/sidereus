<!-- Sidereus threat model for Anthropic OSS Scanner, filled from templates/oss-scanner/threat_model.md. Facts are from SECURITY.md and AGENTS.md (rules 1, 2, 7); keep them in sync. -->
# Threat model

## What this project does and where untrusted input enters
Sidereus is a local session-control viewer for Claude Code: a Python standard-library HTTP server (`chat_server.py`,
`sidereus/*.py`) plus an inline web page (`web/`) and a read-only MCP server (`mcp/sidereus_mcp.py`). It monitors
sessions from local transcripts and relays a person's instructions to sessions through a file-based mailbox. One user,
one machine, no external libraries, no auth beyond loopback.

Untrusted input enters through:
- **HTTP requests.** The server binds `127.0.0.1` only (hard-coded). Any web page the user visits can still aim
  requests at it, and any local process or OS user can call it directly.
- **Transcripts** under the Claude Code projects folder. Their content includes tool output, i.e. text from files,
  web pages and repos the sessions read. Rendered metadata (paths, task labels, model names) derives from them.
- **Git metadata** of the repos sessions work in (branch names, commit subjects, file paths), read through `git_argv`.
- **Mailbox messages** (DMs, rooms) written by other sessions, and project `.claude/pipelines/*.json` files.
- **Local POSTs without `Origin`**: OTel export (`/v1/logs`, `/v1/metrics`) and hooks (`/api/hook`).

## Components that matter most / least
In scope, most important:
- Request guards in `chat_server.py`: Host check on every request (`127.0.0.1:<port>` / `localhost:<port>` only,
  DNS-rebinding guard), Origin check on POST, `/api/*` GET refused with `Sec-Fetch-Site: cross-site` or `same-site`,
  `frame-ancestors 'none'` and `X-Frame-Options: DENY`.
- **Metadata only**: conversation content never reaches the page or the MCP tools. A row carries path, session id,
  model and the agent's one-line task label. The single exception is the work popup (`sidereus/work.py`
  `session_work` / `agent_work`), opened on click, limited to repos of sessions shown on screen (allowed-cwd list).
- **Config writes** (`sidereus/pipeline.py`, `sidereus/cc_settings.py`): project `.claude/pipelines/*.json` and three
  keys of each account's `settings.json` (`autoCompactEnabled`, `autoCompactWindow`, plus the port of a local
  `env.OTEL_EXPORTER_OTLP_ENDPOINT`). Each write needs diff preview + confirm, a backup first, the viewer Origin, and a
  path inside the allow-list. Delete moves the file to the backup folder.
- **Relay**: mailbox DMs go only to registered ids; only what a person pressed is sent.
- **Rendering** in `web/`: every interpolated value into `innerHTML` must pass `esc()`.
- **Git calls** go through `git_argv` with `core.fsmonitor=false` and `core.hooksPath=/dev/null`; Sidereus runs no
  git write commands.

Less important: `--demo` mode (synthetic data, nothing real read or written), `scripts/`, `plugins/`, docs.
Out of scope: `tests/`, `backup.sh`.

## How to exercise it
- `bash tests/run.sh` runs the unit tests offline (standard library only); `scripts/check.sh --fast` runs the gates.
- `python3 chat_server.py --demo --no-open --port 8799` serves a synthetic world; request it with `curl`, setting
  `Host`, `Origin` and `Sec-Fetch-Site` to test the guards.

## How you rate severity
- **Critical**: a page on another origin, or a crafted transcript / repo / mailbox message, gets code execution, a git
  write, a process spawn, or a write outside the config allow-list.
- **High**: a cross-origin page triggers a relay (mailbox send) or a config write, or reads any response body;
  conversation content reaches the page list, timeline, cards or MCP tools outside the work popup; XSS in the viewer
  from transcript, git or mailbox data; a path outside the allow-list read or written; the work popup serving a repo
  that is not on screen.
- **Medium**: bypassing preview + confirm or the backup on an allowed write; a crafted local file that stops the
  viewer (DoS); a secret shown unredacted in the work popup.
- **Low**: information about local paths or session ids reaching a cross-origin page without content.
- "Is post-auth SQLi high or critical?" does not apply: there is no SQL and no auth. A local process calling the API
  directly is not a privilege boundary (see below); the same bug reached from a web page is rated as above.

## Anything to leave alone
Documented in `SECURITY.md`; do not report:
- No auth beyond loopback: any local process or another OS user on the same machine can call the API, including the
  work-popup endpoints `/api/session/work` and `/api/agent/work`.
- POSTs without `Origin` are accepted (OTel export, curl, hooks).
- The opt-in quota lookup and paid probe to `api.anthropic.com` with the keychain OAuth token.
- The fixed AppleScript that brings a terminal tab to the front, `caffeinate`, and the read-only system commands
  (`ps`, `lsof`, `sysctl`, `pmset`, `git`, `ccusage`).
- Reading transcripts locally to derive metadata (the product itself).

## Report and patch preferences
- Report privately through GitHub private vulnerability reporting (Security tab, "Report a vulnerability").
- Include the commit tested, a `curl` or file reproducer, and what reached the page or disk.
- A minimal patch in the advisory is welcome. There is no promise of a reply or a fix; the project is shared as-is.
