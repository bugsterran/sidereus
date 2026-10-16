# Concept

**Sidereus** is named after Galileo's *Sidereus Nuncius* (1610), the "starry messenger".
Galileo watched the sky through a telescope, drew the Moon phase by phase, logged Jupiter's moons night by night, and published what he saw.
Sidereus does the same for AI coding sessions.

## Synopsis

A developer runs several agents in terminals: Claude Code in some, Codex in others. Each one streams its work.
Nobody reads the streams; the developer looks up when something stops.

Every tool shows a slice: a CLI its own sessions, a dashboard tokens, an app diffs. There is no one place to judge
from, and a request that needs the developer can sit unseen.

Sidereus sits beside the terminals and gives one screen to verify, judge and direct them from, by relaying instructions. It does not run the agents or take over a terminal. It checks two things:

- **the result** — did the gate pass, did a failing test turn green, did the pass hold, and can the gate catch a real defect at all;
- **the process** — did the run follow the declared stages, with the chosen agent and model, and what is each session doing now.

Three connected views carry both: pipelines (the order is declared once, sessions follow it, and each stage shows its progress and the gate evidence behind its verdict), the timeline (what each agent actually did, with the stages overlaid), and structure analysis (an AI-drawn architecture map checked against the code at a commit).

When an agent needs the developer — an answer, a permission, an approval — it rises to the top and stays there until
they act or its session is known to have ended. They act from the same screen, and what they send is kept. Their conversations never leave the machine:
metadata only, local, offline.

It is a foundation to fork and extend, not a finished product. Use it if it fits how you work. If it doesn't, fork it and change it, or leave it ([how this project works](../README.md#how-this-project-works)).

## Direction and what we won't build

Sidereus is an observatory, not a dashboard and not an ADE.

Where it aims:
- A verification layer for agent results: evidence per pipeline stage, and gate quality measured by seeded-defect catch rate, red checks and an unstable verdict ([PIPELINE.md](dev/PIPELINE.md#evaluation-seeds-red-check-flaky-gates)).
- A control view that doesn't miss what needs you. «Attention» ranks sessions from several vendors in one list by how much they block you (approval pending, then an open question, then the rest); tests in the full check keep blocked and asking sessions in the list and at the top. A click brings that session's terminal tab forward, and instructions go through the mailbox.
- One view over terminal CLIs. Claude Code reads from its transcripts; Codex CLI and Gemini CLI report through hooks. Cursor and other CLIs can use the same hook, not yet verified.

Next (planned):
- Pipeline evidence and gate evaluation at the centre of the first screen.
- Cursor and other hook-reporting CLIs verified on a real install.
- Evidence export in the OpenTelemetry GenAI format, so existing observability tools can read it. Sidereus feeds those tools; it does not replace them.

Won't build: running agents, worktrees, diff→PR flows, cloud execution, team or org governance, conversation tracing.
Other tools do these well, and each one conflicts with «metadata only, never drive the CLI».

## Three verbs

| | Galileo | Sidereus |
|---|---|---|
| **Watch** | The Moon and Jupiter's moons, every night | Every session on one screen, the ones waiting on you first |
| **Record** | Positions, with date and hour | Pipeline stage, gate, tests, commit, `file:line` evidence. "Verified by what", not "done" |
| **Relay** | The book | Your instruction to a session, through the mailbox, kept on record |

## The line we keep

An astronomer does not move the stars.

- Sidereus never runs an agent, opens a terminal, or injects input. Sessions run in your own terminal.
- Conversation content never reaches the page. It shows metadata only: path, session, model, task label.
- It writes no git history and no files outside its config allow-list.

## Where it sits

| Kind | Examples | Role |
|---|---|---|
| Cockpit / ADE | Agent Cockpit, Conductor, Vibe Kanban | You run agents inside it |
| Hook dashboard | claude-code-hooks observability, agents-observe | You read events |
| **Observatory** | **Sidereus** | Watch every agent, keep the evidence, relay your word |

What sets it apart: several platforms on one sky, pipeline stages with evidence, a relay that leaves a record, and metadata only.

## Look and voice

- **Mark:** the Moon as Galileo drew it in *Sidereus Nuncius*: a rough terminator, maria and a lit peak. The icon is his first-quarter plate; in the app the mark shows tonight's phase, with the phase and age on hover. When the connection is lost, the lit part dims and the disc gets a red edge.
- **Colour:** a dark night sky, with ivory for the lit Moon and slate for its night side. Keep accents restrained. Avoid AI sparkles and coral.
- **Motion:** one thing moves, the thing that needs you. The rest stays quiet.
- **Voice:** an observation log. State the time, what was seen, and what verified it. No hype.

## What we don't do

- ⚠ Do not build a terminal, a spawner, or a git writer into the core. If people ask for these, they belong in an opt-in extension that is off by default.
- ⚠ Do not use real platform logos inside the mark. Platform diversity shows on the map, not in the logo.
- ⚠ Do not reduce a session, a change or a gate to one grade. Attention points only order the list; security findings come from standard scanners run with the project's config (or the tools' defaults) and show with `file:line`. Show facts and evidence, not judgements.
- ⚠ Do not set up, store or switch accounts or credentials. Show whatever account layout is found.
