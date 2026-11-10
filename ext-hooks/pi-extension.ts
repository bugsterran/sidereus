// Sidereus extension for pi (https://pi.dev): forwards session/tool events to the Sidereus hook scripts.
// Installed by Settings › "Diagnostics" › "Connect" (sidereus/hook_connect_pi.py renders the two placeholders below).
// ⚠Metadata only: payloads carry session id, cwd, event and tool name; only the bash command goes to pl_mark/pl_flow.
//   Prompt text and tool results are never sent.
// ⚠Never throws: every handler is wrapped, a missing Python or a slow script only drops that one event.
// Mail wake: one ext-hooks/pi_wake.py child per instance waits on the mailbox (no model turn while waiting) and asks
//   for one «[mailbox]» turn; it is sent with pi.sendUserMessage only while pi is idle (docs/HOOKS.md «pi»).
import { spawn } from "node:child_process";
import * as path from "node:path";

const PY: string = "<PYTHON>";
const CODE: string = "<MAILBOX_CODE_DIR>";
const TIMEOUT_MS = 5000;
const OUT_MAX = 64 * 1024;
// Runaway cap: wakes in a row without a typed prompt (same env and default as the Codex wake).
const WAKE_MAX = (() => {
  const n = Number.parseInt(String(process.env.SIDEREUS_MAIL_WAIT_MAX ?? ""), 10);
  return Number.isFinite(n) ? Math.min(1e6, Math.max(0, n)) : 20;
})();
// hooks/mail_wait.STALE_S (15 s) + 1 s: a waiter lock left by a kill that skipped cleanup has gone stale by then.
const REARM_MS = 16000;

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
        { stdio: ["pipe", "pipe", "ignore"], windowsHide: true });
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
  return p;
}

export default function (pi: any) {
  let invite = "";
  let brief = "";
  let queue: Promise<unknown> = Promise.resolve();
  const commands = new Map<string, string>();
  let waiter: any = null;
  let ended = false;
  let wakes = 0;
  let retry: any = null;

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
      arm(ctx);   // lifetime over: re-arm silently, no model turn
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
  };
  const arm = (ctx: any, again = false) => {
    if (ended || waiter) return;   // one waiter per instance
    if (retry) { clearTimeout(retry); retry = null; }
    let sid = "";
    let cwd = "";
    try { sid = String(ctx.sessionManager.getSessionId() || ""); } catch (_e) { sid = ""; }
    try { cwd = String(ctx.cwd || ""); } catch (_e) { cwd = ""; }
    if (!sid || !cwd) return;
    let child: any = null;
    try {
      child = spawn(PY, [path.join(CODE, "ext-hooks", "pi_wake.py"), sid, cwd],
        { stdio: ["pipe", "pipe", "ignore"], windowsHide: true });
    } catch (_e) {
      return;
    }
    waiter = child;
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
        try { if (!ended && ctx.isIdle()) arm(ctx, true); } catch (_e) { /* stale ctx */ }
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
      run("hooks/invite_notice.py", base(ctx, "SessionStart")),
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
    send(Object.assign(base(ctx, "PostToolUse"), { tool_name: tool }));
    if (tool !== "bash") return;
    const id = String(event?.toolCallId || "");
    const command = commands.has(id) ? commands.get(id) : String(event?.args?.command ?? "");
    commands.delete(id);
    run("hooks/pl_flow.py", Object.assign(base(ctx, "PostToolUse"), { tool_name: tool, tool_input: { command } }));
  });

  on("ui_prompt_start", async (_event, ctx) => { send(base(ctx, "Notification")); });
  // ⚠agent_end is not final (retry, compaction, queued messages follow); agent_settled is.
  on("agent_start", async (_event, _ctx) => { stopWaiter(); });
  on("agent_settled", async (_event, ctx) => { send(base(ctx, "Stop")); arm(ctx); });
  on("session_shutdown", async (_event, ctx) => {
    ended = true;   // ⚠no re-arm after shutdown: a reload/new session gets a fresh extension instance
    stopWaiter();
    await send(base(ctx, "SessionEnd"));
  });
}
