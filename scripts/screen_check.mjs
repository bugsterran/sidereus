#!/usr/bin/env node
// Headless screen regression check for the viewer, driven over CDP (Node 22 built-ins only, no packages).
// Runs the deterministic `--demo` world on a free port with a temp HOME/MAILBOX_DIR and a separate headless
// Chrome with a temp profile. ⚠Never touches the live viewer (config `port`, 8799 by default) or the user's Chrome profile.
//
//   node scripts/screen_check.mjs             compare against scripts/screen_baseline/*.json (exit 0/1)
//   node scripts/screen_check.mjs --update    rewrite the baseline
//   node scripts/screen_check.mjs --selftest  inject a 500, a JS exception and a text change; exit 0 only if all are caught
//   node scripts/screen_check.mjs --strict    tolerance 0: any changed text line fails (wording/translation migrations)
//
// FAIL on: JS exception, console error, HTTP >= 400, horizontal overflow, a SOFT_ERRS tag not in the baseline,
// or a masked-text snapshot diff beyond tolerance. Digits and time units are masked so demo clock drift is ignored.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASE_DIR = path.join(ROOT, 'scripts', 'screen_baseline');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PY = '/usr/bin/python3';   // same interpreter launchd uses (3.9)
const WIDTHS = [900, 1100, 1440];
const LANGS = ['ko', 'en'];
const HEIGHT = 900;
const DEADLINE_MS = 85000;
const CONCURRENCY = 3;
const args = new Set(process.argv.slice(2));
const UPDATE = args.has('--update');
const SELFTEST = args.has('--selftest');
const VERBOSE = args.has('--verbose');   // also print diffs that stayed within tolerance
const STRICT = args.has('--strict');
// Headless Chrome reports navigator.webdriver ⇒ hide the automation banner (98c) so it never enters the baseline.
const noBar = u => u + (u.includes('?') ? '&' : '?') + 'autobar=0&nosave=1';   // nosave: automation never writes prefs (app-head.js UIS)

const T0 = Date.now();
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'screen-check-'));
const SHOTS = path.join(TMP, 'shots');
// A SIGKILLed run skips cleanup(); drop its chrome/home dirs (>10 min old) on the next run. Shots stay.
for (const n of fs.readdirSync(os.tmpdir())) {
  if (!n.startsWith('screen-check-')) continue;
  for (const d of ['chrome', 'home']) {
    const f = path.join(os.tmpdir(), n, d);
    try { if (Date.now() - fs.statSync(f).mtimeMs > 600000) fs.rmSync(f, { recursive: true, force: true }); } catch {}
  }
}
fs.mkdirSync(SHOTS);
const procs = [];
let cleaned = false;
function cleanup() {
  if (cleaned) return;
  cleaned = true;
  for (const p of procs) {
    try { process.kill(-p.pid, 'SIGKILL'); } catch { try { p.kill('SIGKILL'); } catch {} }
  }
  for (const d of ['chrome', 'home']) {
    try { fs.rmSync(path.join(TMP, d), { recursive: true, force: true }); } catch {}
  }
}
process.on('exit', cleanup);
for (const s of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(s, () => { cleanup(); process.exit(130); });
process.on('uncaughtException', e => { console.error('screen_check: ' + (e && e.stack || e)); cleanup(); process.exit(1); });
process.on('unhandledRejection', e => { console.error('screen_check: ' + (e && e.stack || e)); cleanup(); process.exit(1); });

const sleep = ms => new Promise(r => setTimeout(r, ms));
function freePort() {
  return new Promise((res, rej) => {
    const s = net.createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
  });
}
async function until(fn, ms, what) {
  const end = Date.now() + ms;
  for (;;) {
    try { const v = await fn(); if (v) return v; } catch {}
    if (Date.now() > end) throw new Error('timeout waiting for ' + what);
    await sleep(100);
  }
}

// ---- processes -------------------------------------------------------------
async function startDemo() {
  const port = await freePort();
  const home = path.join(TMP, 'home');
  fs.mkdirSync(path.join(home, 'data'), { recursive: true });
  // ⚠ SIGKILL/OOM of this node process skips every handler above ⇒ the child also exits on stdin EOF (pipe closes when node dies).
  const watchdog = 'import os,sys,threading,runpy\n'
    + 'threading.Thread(target=lambda: (sys.stdin.buffer.read(), os._exit(0)), daemon=True).start()\n'
    + 'sys.argv = sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name="__main__")\n';
  const p = spawn(PY, ['-c', watchdog, path.join(ROOT, 'chat_server.py'), '--demo', '--no-open', '--port', String(port)], {
    cwd: ROOT, detached: true, stdio: ['pipe', 'ignore', 'pipe'],
    env: { ...process.env, HOME: home, MAILBOX_DIR: path.join(home, 'data') },
  });
  procs.push(p);
  let err = '';
  p.stderr.on('data', d => { err += d; });
  const base = 'http://127.0.0.1:' + port;
  await until(async () => (await fetch(base + '/api/state')).ok, 15000, 'demo server (' + err.trim().slice(-300) + ')');
  return base;
}
async function startChrome() {
  const udd = path.join(TMP, 'chrome');
  fs.mkdirSync(udd);
  // ⚠ same SIGKILL gap as the demo ⇒ sh holds the stdin pipe; on EOF (node died) it SIGKILLs its own group (chrome + helpers).
  const p = spawn('/bin/sh', ['-c', '"$0" "$@" & cat >/dev/null; kill -9 0', CHROME, '--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + udd,
    '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--disable-sync',
    '--disable-background-networking', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows', '--hide-scrollbars', '--mute-audio', 'about:blank'],
    { detached: true, stdio: ['pipe', 'ignore', 'ignore'] });
  procs.push(p);
  const f = path.join(udd, 'DevToolsActivePort');
  const txt = await until(() => fs.existsSync(f) && fs.readFileSync(f, 'utf8').includes('\n') && fs.readFileSync(f, 'utf8'), 15000, 'chrome');
  const [port, wsPath] = txt.trim().split('\n');
  return 'ws://127.0.0.1:' + port + wsPath;
}

// ---- CDP over one browser websocket, flat sessions ---------------------------
class CDP {
  constructor(url) { this.url = url; this.id = 0; this.wait = new Map(); this.listeners = new Map(); }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => res();
      this.ws.onerror = e => rej(new Error('cdp ws error'));
      this.ws.onmessage = ev => {
        const m = JSON.parse(ev.data);
        if (m.id && this.wait.has(m.id)) {
          const { res, rej, method } = this.wait.get(m.id); this.wait.delete(m.id);
          m.error ? rej(new Error(method + ': ' + m.error.message)) : res(m.result);
        } else if (m.method) {
          const l = this.listeners.get(m.sessionId || '');
          if (l) l(m.method, m.params);
        }
      };
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const msg = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    return new Promise((res, rej) => { this.wait.set(id, { res, rej, method }); this.ws.send(JSON.stringify(msg)); });
  }
  close() { try { this.ws.close(); } catch {} }
}

// ---- text normalisation / diff ---------------------------------------------
const KO_UNIT = /#\s*(초|분|시간|일|주|개월|달|년)/g;
const EN_UNIT = /#\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?|years?|s|m|h|d|w|mo|y)\b/gi;
const WEEKDAY = /\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b|[월화수목금토일]요일|\((월|화|수|목|금|토|일)\)/g;
const MONTH = /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b/g;
function norm(text) {
  return String(text || '').split('\n').map(l => l
    .replace(/\d+/g, '#').replace(/#(?:[#.,:/\-]#)+/g, '#')
    // ⚠ bare ko weekday after a date: labels follow the real clock, demo values are seeded by day index; must run before KO_UNIT (Sunday char = day unit)
    .replace(/#\s+[월화수목금토일](?=\s)/g, '# <wd>')
    .replace(KO_UNIT,'#t').replace(EN_UNIT, '#t').replace(/#t(\s*#t)+/g, '#t')
    .replace(WEEKDAY, '<wd>').replace(MONTH, '<mon>').replace(/\b[AP]M\b|오전|오후/g, '<ap>')
    .replace(/\s+/g, ' ').trim()).filter(Boolean);
}
// LCS line diff -> list of {op:'-'|'+', line}
function diffLines(a, b) {
  const n = a.length, m = b.length;
  if (n * m > 4e6) return a.join('\n') === b.join('\n') ? [] : [{ op: '!', line: 'region too large to diff (' + n + 'x' + m + ')' }];
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
    dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push({ op: '-', line: a[i++] });
    else out.push({ op: '+', line: b[j++] });
  }
  while (i < n) out.push({ op: '-', line: a[i++] });
  while (j < m) out.push({ op: '+', line: b[j++] });
  return out;
}
// Tolerance: a region may change up to max(2, 3%) lines (drift in demo ages crossing a unit boundary, etc.)
const tol = n => STRICT ? 0 : Math.max(2, Math.ceil(n * 0.03));
// ⚠Timeline axis labels follow the wall clock (which hours/dates fall in the window, en «# <ap>» vs ko «#»);
// the demo server builds data from its own now, so freezing only the page clock would misplace bars ⇒ drop bare tick lines on both sides.
const AXIS_LINE = /^#(?: <ap>)?$/;
const cmpLines = (r, xs) => r === 'tab:time' ? xs.filter(l => !AXIS_LINE.test(l)) : xs;

// ---- page probing ----------------------------------------------------------
const JS_SNAP = `(() => {
  const t = s => { const e = document.querySelector(s); return e ? e.innerText : ''; };
  const vis = [...document.querySelectorAll('#tbar > .tbs')].filter(x => !x.hidden).map(x => x.innerText).join('\\n');
  const se = (typeof SOFT_ERRS === 'object' && SOFT_ERRS) ? Object.keys(SOFT_ERRS).sort() : [];
  const sw = document.scrollingElement ? document.scrollingElement.scrollWidth : 0;
  return JSON.stringify({ kn: !!document.querySelector('#kn,.kni'), sbar: t('#sbar'), tabs: t('#mvw'), feed: t('#feed'), tbar: vis, body: document.body ? document.body.innerText : '',
    soft: se, sw, iw: innerWidth });
})()`;

async function runCombo(cdp, base, width, lang, pop, inject) {
  const tag = width + '-' + lang;
  const issues = [];   // hard failures
  const { browserContextId } = await cdp.send('Target.createBrowserContext', { disposeOnDetach: true });
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId: sid } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => cdp.send(m, p, sid);
  cdp.listeners.set(sid, (method, p) => {
    if (method === 'Runtime.exceptionThrown') {
      const d = p.exceptionDetails || {};
      issues.push('exception: ' + ((d.exception && d.exception.description) || d.text || '?').split('\n')[0] + (d.url ? ' @' + d.url.replace(base, '') + ':' + d.lineNumber : ''));
    } else if (method === 'Runtime.consoleAPICalled' && (p.type === 'error' || p.type === 'assert')) {
      issues.push('console.error: ' + (p.args || []).map(a => a.value !== undefined ? String(a.value) : (a.description || a.type)).join(' ').slice(0, 200));
    } else if (method === 'Log.entryAdded' && p.entry.level === 'error') {
      if (!/status of \d{3}/.test(p.entry.text)) issues.push('log.error: ' + p.entry.text.slice(0, 200) + (p.entry.url ? ' ' + p.entry.url.replace(base, '') : ''));
    } else if (method === 'Network.responseReceived' && p.response.status >= 400) {
      issues.push('HTTP ' + p.response.status + ' ' + p.response.url.replace(base, ''));
    } else if (method === 'Network.loadingFailed' && !p.canceled) {
      issues.push('net fail: ' + p.errorText);
    } else if (method === 'Fetch.requestPaused') {
      S('Fetch.fulfillRequest', { requestId: p.requestId, responseCode: 500, body: Buffer.from('{"err":"selftest"}').toString('base64'),
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }] }).catch(() => {});
    }
  });
  await Promise.all([S('Page.enable'), S('Runtime.enable'), S('Log.enable'), S('Network.enable')]);
  if (inject) await S('Fetch.enable', { patterns: [{ urlPattern: '*/api/agents/timeline*', requestStage: 'Request' }] });
  await S('Emulation.setDeviceMetricsOverride', { width, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  // ⚠The tone default follows the OS and headless Chrome reports light — pin the dark tone the baselines were taken in.
  // ⚠UI prefs are server-backed (UIS): pin them through window.__UIP and swallow pref POSTs, so concurrent pages on one server never share state.
  await S('Page.addScriptToEvaluateOnNewDocument', { source: `try{const P={mbLang:${JSON.stringify(lang)},mbTone:'black'};let u=Object.assign({},P);`
    + `Object.defineProperty(window,'__UIP',{configurable:true,get(){return u;},set(v){u=Object.assign({},v||{},P);}});const f=window.fetch;`
    + `window.fetch=function(a,o){if(o&&o.method==='POST'&&String(a).indexOf('/api/ui-prefs')>=0)return Promise.resolve(new Response('{"ok":true}',{headers:{'Content-Type':'application/json'}}));return f.apply(this,arguments);};}catch(e){}` });
  const ev = async expr => {
    const r = await S('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('evaluate: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  };
  const snap = async () => JSON.parse(await ev(JS_SNAP));
  // Settle = the visible text stops changing for 2 consecutive 150ms samples (cap 2.5s).
  const settle = async (key = 'feed') => {
    let prev = null, same = 0; const end = Date.now() + 2500;
    while (Date.now() < end) {
      await sleep(150);
      const s = await snap();
      const cur = s[key] + '\u0000' + s.tbar;
      same = (cur === prev && cur.length) ? same + 1 : 0;
      prev = cur;
      if (same >= 2) return s;
    }
    return snap();
  };
  const shot = async name => {
    const r = await S('Page.captureScreenshot', { format: 'jpeg', quality: 60 });
    fs.writeFileSync(path.join(SHOTS, tag + '-' + name + '.jpg'), Buffer.from(r.data, 'base64'));
  };
  const overflow = (s, where) => { if (s.sw > s.iw) issues.push('overflow ' + where + ': scrollWidth ' + s.sw + ' > innerWidth ' + s.iw); };

  const regions = {}; const soft = new Set();
  await S('Page.navigate', { url: base + noBar('/') });
  await until(async () => await ev(`document.readyState==='complete' && document.querySelectorAll('#mvw .mvb').length>0 && !!document.querySelector('#sbar') && document.querySelector('#sbar').innerText.trim().length>0`), 10000, tag + ' first render');
  let s = await settle();
  regions.tabs = norm(s.tabs);
  // The header KPI strip was removed; its return is a regression.
  if (s.kn) issues.push('header KPI strip (#kn/.kni) is back');
  const keys = await ev(`[...document.querySelectorAll('#mvw .mvb')].map(b => b.dataset.mv)`);
  if (!keys.length) issues.push('no tabs found in #mvw');
  if (inject) await ev(`setTimeout(() => { throw new Error('selftest injected exception'); }, 0), 1`);
  for (const k of keys) {
    await ev(`(() => { const b = document.querySelector('#mvw .mvb[data-mv="${k}"]'); if (!b) throw new Error('tab ${k} gone'); b.click(); return 1; })()`);
    s = await settle();
    if (inject && k === keys[keys.length - 1]) { await ev(`(document.getElementById('feed').insertAdjacentHTML('afterbegin','<div>SELFTEST CHANGED LINE A</div><div>SELFTEST CHANGED LINE B</div><div>SELFTEST CHANGED LINE C</div>'), 1)`); s = await snap(); }
    regions['tab:' + k] = norm(s.tbar + '\n' + s.feed);
    s.soft.forEach(x => soft.add(x));
    overflow(s, 'tab ' + k);
    await shot('tab-' + k);
  }
  // Popups: same document on /diff and /work with query params (see web/js/00-core.js ISPOP/ISWP).
  for (const [name, url] of [['diff', pop.diff], ['work', pop.work], ['sess', pop.sess]]) {
    await S('Page.navigate', { url: base + noBar(url) });
    await until(async () => await ev(`document.readyState==='complete'`), 10000, tag + ' ' + name + ' popup');
    // Session work view: the «컨텍스트» line is fetched lazily (35d-ctxsrc.js) — wait for it, left collapsed.
    if (name === 'sess') await until(async () => await ev(`!!document.querySelector('details.ctxs')`), 8000, tag + ' sess ctx line');
    s = await settle('body');
    regions['pop:' + name] = norm(s.body);
    s.soft.forEach(x => soft.add(x));
    overflow(s, 'popup ' + name);
    await shot('pop-' + name);
  }
  await cdp.send('Target.closeTarget', { targetId }).catch(() => {});
  await cdp.send('Target.disposeBrowserContext', { browserContextId }).catch(() => {});
  cdp.listeners.delete(sid);
  return { tag, issues: [...new Set(issues)], data: { regions, soft: [...soft].sort() } };
}

function compare(res) {
  const f = path.join(BASE_DIR, res.tag + '.json');
  const fails = [...res.issues];
  const notes = [];
  if (!fs.existsSync(f)) { fails.push('no baseline ' + path.relative(ROOT, f) + ' (run with --update)'); return { fails, notes }; }
  const b = JSON.parse(fs.readFileSync(f, 'utf8'));
  const newSoft = res.data.soft.filter(x => !(b.soft || []).includes(x));
  if (newSoft.length) fails.push('new SOFT_ERRS: ' + newSoft.join(', '));
  const names = new Set([...Object.keys(b.regions), ...Object.keys(res.data.regions)]);
  for (const r of names) {
    const a0 = b.regions[r], c0 = res.data.regions[r];
    if (!a0) { fails.push('region added: ' + r); continue; }
    if (!c0) { fails.push('region missing: ' + r); continue; }
    const a = cmpLines(r, a0), c = cmpLines(r, c0);
    const d = diffLines(a, c);
    const changed = Math.max(d.filter(x => x.op === '-').length, d.filter(x => x.op === '+').length, d.some(x => x.op === '!') ? Infinity : 0);
    if (!changed) continue;
    const msg = r + ': ' + changed + ' line(s) differ (tolerance ' + tol(a.length) + ')\n' +
      d.slice(0, 20).map(x => '      ' + x.op + ' ' + x.line.slice(0, 160)).join('\n') + (d.length > 20 ? '\n      ... ' + (d.length - 20) + ' more' : '');
    (changed > tol(a.length) ? fails : notes).push(msg);
  }
  return { fails, notes };
}

async function pool(items, n, fn) {
  const out = new Array(items.length); let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k]); }
  }));
  return out;
}

async function main() {
  const [base, wsUrl] = await Promise.all([startDemo(), startChrome()]);
  const st = await (await fetch(base + '/api/state')).json();
  const ses = (st.sessions || []).find(x => x.cwd && (x.sub || []).length) || (st.sessions || [])[0];
  if (!ses) throw new Error('demo /api/state has no sessions');
  const tid = ((ses.sub || [])[0] || {}).tid || 'demo';
  const pop = { diff: '/diff?cwd=' + encodeURIComponent(ses.cwd), work: '/work?cwd=' + encodeURIComponent(ses.cwd) + '&tid=' + encodeURIComponent(tid),
    sess: '/work?cwd=' + encodeURIComponent(ses.cwd) + '&tid=' + encodeURIComponent('sess:' + ses.cwd + '|' + ses.sid) };
  const cdp = new CDP(wsUrl); await cdp.open();
  const combos = SELFTEST ? [[1100, 'ko']] : WIDTHS.flatMap(w => LANGS.map(l => [w, l]));
  const timer = setTimeout(() => { console.error('FAIL screen_check: exceeded ' + DEADLINE_MS / 1000 + 's'); cleanup(); process.exit(1); }, DEADLINE_MS);
  const results = await pool(combos, CONCURRENCY, ([w, l]) => runCombo(cdp, base, w, l, pop, SELFTEST));
  clearTimeout(timer);
  cdp.close();
  const secs = ((Date.now() - T0) / 1000).toFixed(1);

  if (UPDATE && !SELFTEST) {
    fs.mkdirSync(BASE_DIR, { recursive: true });
    let bad = 0;
    for (const r of results) {
      fs.writeFileSync(path.join(BASE_DIR, r.tag + '.json'), JSON.stringify(r.data, null, 1) + '\n');
      const n = Object.values(r.data.regions).reduce((a, x) => a + x.length, 0);
      if (r.issues.length) bad++;
      console.log((r.issues.length ? 'WARN ' : 'SAVED ') + r.tag + ': ' + Object.keys(r.data.regions).length + ' regions, ' + n + ' lines'
        + (r.issues.length ? '\n    ' + r.issues.join('\n    ') : ''));
    }
    console.log('baseline written to ' + path.relative(ROOT, BASE_DIR) + ' in ' + secs + 's · screenshots ' + SHOTS);
    return bad ? 1 : 0;
  }
  let failed = 0;
  const ev = [];
  for (const r of results) {
    const { fails, notes } = compare(r);
    if (fails.length) failed++;
    const [w, lang] = r.tag.split('-');
    ev.push({ w: +w, lang, ok: !fails.length, diff: fails.length });
    console.log((fails.length ? 'FAIL ' : 'PASS ') + r.tag + (fails.length ? ': ' + fails.length + ' problem(s)' : '')
      + (notes.length ? ' (' + notes.length + ' region(s) within tolerance)' : ''));
    for (const x of fails) console.log('    ' + x);
    if (VERBOSE) for (const x of notes) console.log('    (ok) ' + x);
  }
  console.log('screenshots: ' + SHOTS + ' · ' + secs + 's');
  // Per-combo counts for check.sh's evidence record (compare runs only; metadata, no diff text).
  if (!SELFTEST && process.env.SIDEREUS_EV_SCREEN) {
    try { fs.writeFileSync(process.env.SIDEREUS_EV_SCREEN, JSON.stringify(ev) + '\n'); } catch {}
  }
  if (SELFTEST) {
    const all = results.flatMap(r => compare(r).fails).join('\n');
    const want = { 'HTTP 500': /HTTP 500 \/api\/agents\/timeline/, 'exception': /exception: .*selftest injected/, 'text diff': /SELFTEST CHANGED LINE/ };
    const miss = Object.keys(want).filter(k => !want[k].test(all));
    console.log(miss.length ? 'SELFTEST FAILED: not detected -> ' + miss.join(', ') : 'SELFTEST OK: injected ' + Object.keys(want).join(', ') + ' all detected as FAIL');
    return miss.length ? 1 : 0;
  }
  return failed ? 1 : 0;
}

main().then(code => { cleanup(); process.exit(code); }, e => { console.error('FAIL screen_check: ' + (e && e.stack || e)); cleanup(); process.exit(1); });
