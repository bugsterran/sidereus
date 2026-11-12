// Sidereus extension for pi (https://pi.dev): forwards session/tool events to the Sidereus hook scripts.
// Installed by Settings › "Diagnostics" › "Connect" (sidereus/hook_connect_pi.py renders the three placeholders below).
// ⚠Metadata only: payloads carry session id, cwd, event, tool name and the extension rev (a child adds token counts
//   and model); only the bash command goes to pl_mark/pl_flow.
//   Prompt text and tool results are never sent.
// ⚠Never throws: every handler is wrapped, a missing Python or a slow script only drops that one event.
// Mail wake: one ext-hooks/pi_wake.py child per instance waits on the mailbox (no model turn while waiting) and asks
//   for one «[mailbox]» turn; it is sent with pi.sendUserMessage only while pi is idle (docs/HOOKS.md «pi»).
import { spawn } from "node:child_process";
import * as path from "node:path";

const PY: string = "<PYTHON>";
const CODE: string = "<MAILBOX_CODE_DIR>";
// Extension rev (sha256[:12] of the template, rendered by hook_connect_pi): Sidereus compares it to flag an old copy.
const REV: string = "<SIDEREUS_REV>";
const REV_RE = /^[0-9a-f]{12}$/;
const TIMEOUT_MS = 5000;
const OUT_MAX = 64 * 1024;
// Runaway cap: wakes in a row without a typed prompt (same env and default as the Codex wake).
const WAKE_MAX = (() => {
  const n = Number.parseInt(String(process.env.SIDEREUS_MAIL_WAIT_MAX ?? ""), 10);
  return Number.isFinite(n) ? Math.min(1e6, Math.max(0, n)) : 20;
})();
// hooks/mail_wait.STALE_S (15 s) + 1 s: a waiter lock left by a kill that skipped cleanup has gone stale by then.
const REARM_MS = 16000;
// Subagent child: a `pi -p` spawned by a parent pi's subagent tool inherits these (set only around that tool call).
const PARENT0: string = String(process.env.SIDEREUS_PARENT_SID ?? "");
const CHILD: boolean = process.env.SIDEREUS_PARENT_PLAT === "pi" && !!PARENT0;
const NAME_RE = /^[\w.-]{1,64}$/;
const PROMPT_RE = /^prompt-([\w.-]{1,64})\.md$/;

// Child label: the pi subagent's own prompt-file name, else the name the parent put in env.
// ⚠Reads only the argv element right after --append-system-prompt (its basename); the task argv is never read.
function childAgent(): string {
  try {
    const i = process.argv.indexOf("--append-system-prompt");
    if (i >= 0 && i + 1 < process.argv.length) {
      const m = PROMPT_RE.exec(path.basename(String(process.argv[i + 1])));
      if (m) return m[1];
    }
  } catch (_e) { /* fall through */ }
  const s = String(process.env.SIDEREUS_CHILD_AGENT ?? "").replace(/[^\w.-]+/g, "_").slice(0, 64);
  return NAME_RE.test(s) ? s : "";
}
const AGENT: string = CHILD ? childAgent() : "";

// ⚠Hook scripts get the env this process started with: the subagent window's own sid must not make this
//   session its own parent.
function hookEnv(): any {
  const e: any = Object.assign({}, process.env);
  if (PARENT0) e.SIDEREUS_PARENT_SID = PARENT0; else delete e.SIDEREUS_PARENT_SID;
  return e;
}

function run(script: string, payload: object): Promise<string> {
  return new Promise((resolve) => {
    let out = "";
    let done = false;
    let timer: any = null;
    const finish = () => {
      if (done) return;
      done = true;
      if (timer) clearTimeout(timer);
      resolve(out);
    };
    try {
      const child = spawn(PY, [path.join(CODE, script), "--platform", "pi"],
        { stdio: ["pipe", "pipe", "ignore"], windowsHide: true, env: hookEnv() });
      timer = setTimeout(() => { try { child.kill(); } catch (_e) { /* gone */ } finish(); }, TIMEOUT_MS);
      child.stdout.on("data", (d: any) => { if (out.length < OUT_MAX) out += String(d); });
      child.on("error", finish);
      child.on("close", finish);
      child.stdin.on("error", () => {});
      child.stdin.end(JSON.stringify(payload));
    } catch (_e) {
      finish();
    }
  });
}

// hookSpecificOutput.additionalContext of a JSON reply, else the plain text.
function contextOf(out: string): string {
  const s = (out || "").trim();
  if (!s) return "";
  try {
    const t = JSON.parse(s)?.hookSpecificOutput?.additionalContext;
    return typeof t === "string" ? t : "";
  } catch (_e) {
    return s;
  }
}

function base(ctx: any, event: string): any {
  const p: any = { hook_event_name: event };
  try { p.session_id = ctx.sessionManager.getSessionId(); } catch (_e) { /* unknown */ }
  try { p.cwd = ctx.cwd; } catch (_e) { /* unknown */ }
  if (AGENT) p.agent_name = AGENT;
  if (REV_RE.test(REV)) p.ext_rev = REV;   // ⚠an unrendered template sends no rev
  return p;
}

// Agent name of one subagent call: `agent`, or the one name every tasks[]/chain[] item shares; else "".
function agentOf(input: any): string {
  try {
    if (typeof input?.agent === "string") return input.agent;
    const list = Array.isArray(input?.tasks) ? input.tasks : Array.isArray(input?.chain) ? input.chain : null;
    if (!list || !list.length) return "";
    const names = new Set(list.map((t: any) => String(t?.agent ?? "")));
    return names.size === 1 ? String([...names][0]) : "";
  } catch (_e) {
    return "";
  }
}

export default function (pi: any) {
  let invite = "";
  let brief = "";
  let queue: Promise<unknown> = Promise.resolve();
  const commands = new Map<string, string>();
  let waiter: any = null;
  let quietW = false;   // the live waiter wakes only on mail newer than what it found pending
  let ended = false;
  let wakes = 0;
  let retry: any = null;
  // Subagent window: env the subagent tool's spawned `pi -p` inherits; saved values come back when the last call ends.
  const subCalls = new Set<string>();
  let saved: any = null;
  const ENV_KEYS = ["SIDEREUS_PARENT_SID", "SIDEREUS_PARENT_PLAT", "SIDEREUS_CHILD_AGENT"];
  const openSub = (id: string, ctx: any, input: any) => {
    // ⚠A parented pi is never a top-level row, so children pointing at it would vanish: keep the outer parent.
    if (PARENT0 || process.env.CLAUDE_CODE_SESSION_ID) return;
    let sid = "";
    try { sid = String(ctx.sessionManager.getSessionId() || ""); } catch (_e) { sid = ""; }
    if (!sid || subCalls.has(id)) return;
    if (!subCalls.size) {
      saved = {};
      for (const k of ENV_KEYS) saved[k] = process.env[k];
    }
    subCalls.add(id);
    process.env.SIDEREUS_PARENT_SID = sid;
    process.env.SIDEREUS_PARENT_PLAT = "pi";
    const name = agentOf(input);
    if (name) process.env.SIDEREUS_CHILD_AGENT = name; else delete process.env.SIDEREUS_CHILD_AGENT;
  };
  const closeSub = (id: string) => {
    if (!subCalls.delete(id) || subCalls.size || !saved) return;
    for (const k of ENV_KEYS) {
      if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k];
    }
    saved = null;
  };

  // ⚠ext_hook calls go through one queue: a fast tool's PostToolUse must not reach the viewer before its PreToolUse.
  const send = (payload: any): Promise<unknown> => {
    queue = queue.then(() => run("ext-hooks/ext_hook.py", payload), () => undefined);
    return queue;
  };
  const on = (name: string, fn: (event: any, ctx: any) => any) => {
    pi.on(name, async (event: any, ctx: any) => {
      try { return await fn(event, ctx); } catch (_e) { return undefined; }
    });
  };

  const stopWaiter = () => {
    if (retry) { clearTimeout(retry); retry = null; }
    const c = waiter;
    waiter = null;
    if (!c) return;
    try { c.stdin.end(); } catch (_e) { /* gone */ }
    try { c.kill(); } catch (_e) { /* gone */ }
  };
  const onWaiterLine = (child: any, line: string, ctx: any) => {
    if (waiter !== child) return;
    let m: any = null;
    try { m = JSON.parse(line); } catch (_e) { return; }
    if (m && m.end === "timeout") {
      waiter = null;
      arm(ctx, false, quietW);   // lifetime over: re-arm silently, no model turn, same quiet flag
      return;
    }
    if (!m || typeof m.wake !== "string") return;
    // ⚠Detach before sending: sendUserMessage fires `input`, whose stopWaiter would kill the child before its "ok".
    waiter = null;
    let ok = false;
    try { ok = !ended && wakes < WAKE_MAX && ctx.isIdle() && !ctx.hasPendingMessages(); } catch (_e) { ok = false; }
    if (ok) {
      try { wakes += 1; pi.sendUserMessage(m.wake); } catch (_e) { wakes -= 1; ok = false; }
    }
    // ⚠Only "ok" marks the mail surfaced; "no" leaves it for the next wake or turn end.
    try { child.stdin.end(ok ? "ok\n" : "no\n"); } catch (_e) { /* gone */ }
    // ⚠An idle session never fires agent_settled: without a waiter its .watch heartbeat stops and the presence is
    //   pruned. A quiet waiter keeps the heartbeat and wakes only on newer mail (a normal one would re-fire in 1 s).
    if (!ok && !ended) arm(ctx, false, true);
  };
  const arm = (ctx: any, again = false, quiet = false) => {
    if (CHILD || ended || waiter) return;   // one waiter per instance; a subagent child never waits on mail
    if (retry) { clearTimeout(retry); retry = null; }
    let sid = "";
    let cwd = "";
    try { sid = String(ctx.sessionManager.getSessionId() || ""); } catch (_e) { sid = ""; }
    try { cwd = String(ctx.cwd || ""); } catch (_e) { cwd = ""; }
    if (!sid || !cwd) return;
    let child: any = null;
    try {
      const argv = [path.join(CODE, "ext-hooks", "pi_wake.py"), sid, cwd];
      if (quiet) argv.push("quiet");
      child = spawn(PY, argv, { stdio: ["pipe", "pipe", "ignore"], windowsHide: true });
    } catch (_e) {
      return;
    }
    waiter = child;
    quietW = quiet;
    let buf = "";
    let said = false;
    const gone = () => {
      if (waiter !== child) return;
      waiter = null;
      // ⚠Exit with no line = slot «busy» (on Windows kill() is TerminateProcess, so the killed waiter's lock stays
      //   fresh for STALE_S): retry once after it goes stale, never in a loop.
      if (said || again || ended) return;
      retry = setTimeout(() => {
        retry = null;
        try { if (!ended && ctx.isIdle()) arm(ctx, true, quiet); } catch (_e) { /* stale ctx */ }
      }, REARM_MS);
      try { retry.unref(); } catch (_e) { /* no unref */ }
    };
    child.on("error", gone);
    child.on("close", gone);
    child.stdin.on("error", () => {});
    child.stdout.on("data", (d: any) => {
      if (buf.length < OUT_MAX) buf += String(d);
      let i = buf.indexOf("\n");
      while (i >= 0) {
        const line = buf.slice(0, i);
        buf = buf.slice(i + 1);
        said = true;
        try { onWaiterLine(child, line, ctx); } catch (_e) { /* never throw */ }
        i = buf.indexOf("\n");
      }
    });
  };

  on("session_start", async (_event, ctx) => {
    ended = false;   // pi rebinds a fresh instance per session; reset anyway, as its docs advise for in-memory state
    wakes = 0;
    arm(ctx);
    send(base(ctx, "SessionStart"));
    const [a, b] = await Promise.all([
      CHILD ? Promise.resolve("") : run("hooks/invite_notice.py", base(ctx, "SessionStart")),
      run("hooks/pipelines_brief.py", base(ctx, "SessionStart")),
    ]);
    invite = contextOf(a);
    brief = contextOf(b);
  });

  on("input", async (event, _ctx) => {
    if (event?.source !== "extension") wakes = 0;   // a typed or RPC prompt resets the runaway cap
    stopWaiter();
  });

  on("before_agent_start", async (event, ctx) => {
    stopWaiter();
    send(base(ctx, "UserPromptSubmit"));
    const b = contextOf(await run("hooks/pipelines_brief.py", base(ctx, "UserPromptSubmit")));
    if (b) brief = b;   // silent = unchanged since the last brief
    const text = [invite, brief].filter((x) => x).join("\n\n");
    const sections = event?.systemPromptOptions?.sections;
    // ⚠A prompt section, not a persisted message or a systemPrompt replace: pi patches only changed sections.
    if (text && sections && typeof sections === "object") sections.sidereus = text;
  });

  on("tool_call", async (event, ctx) => {
    const tool = String(event?.toolName || "");
    send(Object.assign(base(ctx, "PreToolUse"), { tool_name: tool }));
    if (tool === "subagent") openSub(String(event?.toolCallId || ""), ctx, event?.input);
    if (tool !== "bash") return undefined;
    const command = String(event?.input?.command ?? "");
    if (event?.toolCallId) commands.set(String(event.toolCallId), command);
    const p = Object.assign(base(ctx, "PreToolUse"), { tool_name: tool, tool_input: { command } });
    run("hooks/pl_mark.py", p);
    const out = await run("hooks/pl_flow.py", p);
    let h: any = null;
    try { h = JSON.parse(out.trim() || "{}")?.hookSpecificOutput; } catch (_e) { h = null; }
    if (h && h.permissionDecision === "deny") {
      return { block: true, reason: String(h.permissionDecisionReason || "Denied by the Sidereus pipeline flow") };
    }
    return undefined;
  });

  on("tool_execution_end", async (event, ctx) => {
    const tool = String(event?.toolName || "");
    if (tool === "subagent") closeSub(String(event?.toolCallId || ""));
    send(Object.assign(base(ctx, "PostToolUse"), { tool_name: tool }));
    if (tool !== "bash") return;
    const id = String(event?.toolCallId || "");
    const command = commands.has(id) ? commands.get(id) : String(event?.args?.command ?? "");
    commands.delete(id);
    run("hooks/pl_flow.py", Object.assign(base(ctx, "PostToolUse"), { tool_name: tool, tool_input: { command } }));
  });

  // ⚠A `pi -p --no-session` child writes no session file, so its token counts ride a pi-only Usage event (counts,
  //   generation id, model only; parents read their file and never send it). Not Stop: that would flip row state per message.
  let gens = 0;
  const genBase = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  on("message_end", async (event, ctx) => {
    const m = event?.message;
    const u = m?.usage;
    if (!CHILD || m?.role !== "assistant" || !u || typeof u !== "object") return;
    const rid = typeof m.responseId === "string" && /^[\w-]{1,64}$/.test(m.responseId) ? m.responseId : "";
    const p: any = Object.assign(base(ctx, "Usage"), {
      generation_id: rid || `${genBase}-${++gens}`,
      input_tokens: u.input, output_tokens: u.output, cache_read_tokens: u.cacheRead, cache_write_tokens: u.cacheWrite,
    });
    if (typeof m.model === "string" && m.model) p.model = m.model.slice(0, 40);
    send(p);
  });

  on("ui_prompt_start", async (_event, ctx) => { send(base(ctx, "Notification")); });
  // ⚠agent_end is not final (retry, compaction, queued messages follow); agent_settled is.
  on("agent_start", async (_event, _ctx) => { stopWaiter(); });
  on("agent_settled", async (_event, ctx) => {
    send(base(ctx, "Stop"));
    if (waiter && quietW) stopWaiter();   // ⚠a quiet waiter would hide the refused mail at turn end; arm() skips while one lives
    arm(ctx);
  });
  on("session_shutdown", async (_event, ctx) => {
    ended = true;   // ⚠no re-arm after shutdown: a reload/new session gets a fresh extension instance
    stopWaiter();
    for (const id of [...subCalls]) closeSub(id);   // ⚠a reload must not leave this sid in the shared process env
    await send(base(ctx, "SessionEnd"));
  });
}
