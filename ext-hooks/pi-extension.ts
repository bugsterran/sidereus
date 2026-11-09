// Sidereus extension for pi (https://pi.dev): forwards session/tool events to the Sidereus hook scripts.
// Installed by Settings › "Diagnostics" › "Connect" (sidereus/hook_connect_pi.py renders the two placeholders below).
// ⚠Metadata only: payloads carry session id, cwd, event and tool name; only the bash command goes to pl_mark/pl_flow.
//   Prompt text and tool results are never sent.
// ⚠Never throws: every handler is wrapped, a missing Python or a slow script only drops that one event.
import { spawn } from "node:child_process";
import * as path from "node:path";

const PY: string = "<PYTHON>";
const CODE: string = "<MAILBOX_CODE_DIR>";
const TIMEOUT_MS = 5000;
const OUT_MAX = 64 * 1024;

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

  on("session_start", async (_event, ctx) => {
    send(base(ctx, "SessionStart"));
    const [a, b] = await Promise.all([
      run("hooks/invite_notice.py", base(ctx, "SessionStart")),
      run("hooks/pipelines_brief.py", base(ctx, "SessionStart")),
    ]);
    invite = contextOf(a);
    brief = contextOf(b);
  });

  on("before_agent_start", async (event, ctx) => {
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
  on("agent_settled", async (_event, ctx) => { send(base(ctx, "Stop")); });
  on("session_shutdown", async (_event, ctx) => { await send(base(ctx, "SessionEnd")); });
}
