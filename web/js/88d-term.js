// ── «To terminal» — bring a session's iTerm2 / Terminal tab to the front (POST /api/term/focus) ──────────
// Sessions run in a terminal (iTerm2) with Sidereus instead of an ADE, so a card needs a one-click way back to that tab.
// ⚠Focus only — never type into the tab (AGENTS.md rule 7: no pty / send-keys). Anything else falls back to copying the server's `cmd`.
// ⚠First use triggers the macOS Automation prompt; a denied prompt comes back as how 'error' with -1743 in err.
const TERM_APPS = ['auto', 'iterm', 'apple', 'orca', 'off'];
let TERM_APP = 'auto', TERM_PEND = false;
// Poll (95-poll) hands over state().cfg.termApp; skipped while our own save is in flight so it does not flip back.
function termCfg(v){ if(!TERM_PEND && TERM_APPS.includes(v)) TERM_APP = v; }
function termLive(x){ return !!(x && x.sid && x.state !== 'done' && x.state !== 'gone'); }
// true = the server can raise the tab; false = the button will only copy a command.
function termCanFocus(x){
  if(TERM_APP === 'off') return false;
  if(TERM_APP === 'iterm' || TERM_APP === 'apple' || TERM_APP === 'orca') return true;
  return !!(x && x.term && (x.term.app === 'iterm' || x.term.app === 'apple' || x.term.app === 'orca'));
}
// kind: 'sx' session row chip · 'bd' board card · 'at' attention row. '' for sessions that are not live.
function termBtnHtml(x, kind){
  if(!termLive(x)) return '';
  const f = termCanFocus(x);
  const tip = esc(T(f ? "Bring this session's terminal tab to the front" : 'The terminal tab cannot be reached — click to copy a command that opens it'));
  const lbl = esc(T(f ? 'Terminal' : 'Copy command'));
  if(kind === 'sx') return '<button class="stm' + (f ? '' : ' cp') + '" data-term="' + esc(x.sid) + '" title="' + tip + '" aria-label="' + lbl + '">›_</button>';
  return '<button class="' + (kind === 'at' ? 'atb ' : '') + 'tmgo' + (f ? '' : ' cp') + '" data-term="' + esc(x.sid) + '" title="' + tip + '">' + lbl + '</button>';
}
async function termGo(sid, btn){
  if(!sid) return;
  if(btn) btn.disabled = true;
  let r = null;
  try { r = await postJSON('/api/term/focus', { sid: sid }); }
  catch(e){ r = e.body || null; softErr('termFocus', e); }
  finally { if(btn) btn.disabled = false; }
  if(!r || !r.how) return note(T('Could not switch to the terminal — check the server'));
  if(r.how === 'focused') return note(T('Switched to the terminal'));
  const cmd = String(r.cmd || ''), ok = cmd ? await copyText(cmd) : false;
  const tail = cmd ? ': ' + cmd : '';
  if(cmd && !ok) return note(T('Could not copy the command') + tail);
  // Orca without its CLI (or with a handle from before an Orca restart): only the app came forward.
  if(r.how === 'app') return note(T(r.hint === 'handle' ? 'Brought the Orca app forward only — the tab handle expired (reopen the session after an Orca restart)'
    : 'Brought the Orca app forward only — install the CLI in Orca settings to reach the exact tab') + (cmd ? ' · ' + T('Copy command') + tail : ''));
  const more = cmd ? ' · ' + T('Copy command') + tail : '';
  // ⚠Only an AppleScript "not authorized" (-1743) is a permission problem; timeouts and other errors have their own text.
  if(r.how === 'error' && /-1743|not authori[sz]ed|not allowed/i.test(String(r.err || ''))) return note(T('No permission to control the terminal — allow iTerm2 (or Terminal) under System Settings › Privacy & Security › Automation') + more);
  if(r.how === 'error') return note(T('Could not control the terminal app') + more);
  if(r.how === 'timeout') return note(T('The terminal app did not answer in time (busy or many windows) — try again') + more);
  if(r.how === 'notfound') return note(T("Session's terminal not found — it may have closed or the list is refreshing") + more);
  if(!cmd) return note(T('Terminal tab not found'));
  note(T('This terminal is not supported — copied a command instead') + tail);
}
// Gear setting (90-settings «Terminal link»). Optimistic; reverts and notes on failure.
function termSet(v){
  if(!TERM_APPS.includes(v) || v === TERM_APP) return;
  const prev = TERM_APP;
  TERM_APP = v; TERM_PEND = true;
  postJSON('/api/term/set', { termApp: v })
    .then(r => { if(r && r.ok === false) throw new Error(r.err || 'term/set'); if(r && TERM_APPS.includes(r.termApp)) TERM_APP = r.termApp; })
    .catch(e => { TERM_APP = prev; softErr('termSet', e); note(T('Could not save the terminal setting')); })
    .finally(() => { TERM_PEND = false; paintCfg(); });
}
// ⚠One capture-phase listener: rows are morph-patched / repainted every poll, and stopping here keeps the row, card and
//   attention handlers (open work log, open review, dismiss) from also firing on the same click.
document.addEventListener('click', e => {
  const b = e.target && e.target.closest && e.target.closest('[data-term]');
  if(!b) return;
  e.preventDefault(); e.stopPropagation();
  termGo(b.getAttribute('data-term'), b);
}, true);
