// Shared by scripts/readme_shots.mjs and scripts/readme_gif.mjs (Node 22 built-ins only, no packages).
// Own demo server on a free port, temp HOME/MAILBOX_DIR, headless Chrome with a temp profile, a minimal CDP client.
// ⚠Never points at the live viewer (8799) — every pixel must come from the synthetic `--demo` world.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PY = '/usr/bin/python3';

export const sleep = ms => new Promise(r => setTimeout(r, ms));
function freePort() {
  return new Promise((res, rej) => {
    const s = net.createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
  });
}
export async function until(fn, ms, what) {
  const end = Date.now() + ms;
  for (;;) {
    try { const v = await fn(); if (v) return v; } catch {}
    if (Date.now() > end) throw new Error('timeout waiting for ' + what);
    await sleep(100);
  }
}

// One temp dir + child processes per run; cleanup() kills them and removes the dir (also on exit and signals).
export function sandbox(prefix) {
  const TMP = fs.mkdtempSync(path.join(os.tmpdir(), prefix + '-'));
  const procs = [];
  let cleaned = false;
  function cleanup() {
    if (cleaned) return;
    cleaned = true;
    for (const p of procs) { try { process.kill(-p.pid, 'SIGKILL'); } catch { try { p.kill('SIGKILL'); } catch {} } }
    try { fs.rmSync(TMP, { recursive: true, force: true }); } catch {}
  }
  process.on('exit', cleanup);
  for (const s of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(s, () => { cleanup(); process.exit(130); });

  async function startDemo() {
    const port = await freePort();
    const home = path.join(TMP, 'home');
    fs.mkdirSync(path.join(home, 'data'), { recursive: true });
    // The child exits on stdin EOF too, so a SIGKILLed node never leaves the demo server behind.
    const watchdog = 'import os,sys,threading,runpy\n'
      + 'threading.Thread(target=lambda: (sys.stdin.buffer.read(), os._exit(0)), daemon=True).start()\n'
      + 'sys.argv = sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name="__main__")\n';
    // ⚠CLAUDE_CONFIG_DIR (set when run from a Claude Code session) would point the demo at the real Claude root.
    const env = { ...process.env, HOME: home, MAILBOX_DIR: path.join(home, 'data') };
    delete env.CLAUDE_CONFIG_DIR;
    const p = spawn(PY, ['-c', watchdog, path.join(ROOT, 'chat_server.py'), '--demo', '--no-open', '--port', String(port)], {
      cwd: ROOT, detached: true, stdio: ['pipe', 'ignore', 'pipe'], env,
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
    const p = spawn('/bin/sh', ['-c', '"$0" "$@" & cat >/dev/null; kill -9 0', CHROME, '--headless=new', '--remote-debugging-port=0', '--user-data-dir=' + udd,
      '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--disable-sync', '--disable-background-networking',
      '--hide-scrollbars', '--mute-audio', '--force-color-profile=srgb', '--font-render-hinting=none', 'about:blank'],
      { detached: true, stdio: ['pipe', 'ignore', 'ignore'] });
    procs.push(p);
    const f = path.join(udd, 'DevToolsActivePort');
    const txt = await until(() => fs.existsSync(f) && fs.readFileSync(f, 'utf8').includes('\n') && fs.readFileSync(f, 'utf8'), 15000, 'chrome');
    const [port, wsPath] = txt.trim().split('\n');
    return 'ws://127.0.0.1:' + port + wsPath;
  }
  return { TMP, cleanup, startDemo, startChrome };
}

export class CDP {
  constructor(url) { this.url = url; this.id = 0; this.wait = new Map(); }
  open() {
    return new Promise((res, rej) => {
      this.ws = new WebSocket(this.url);
      this.ws.onopen = () => res();
      this.ws.onerror = () => rej(new Error('cdp ws error'));
      this.ws.onmessage = ev => {
        const m = JSON.parse(ev.data);
        if (m.id && this.wait.has(m.id)) {
          const { res, rej, method } = this.wait.get(m.id); this.wait.delete(m.id);
          m.error ? rej(new Error(method + ': ' + m.error.message)) : res(m.result);
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

// Fresh browser context + tab on the demo app: language + dark tone (+ prefs) pinned, pref POSTs swallowed (as screen_check.mjs does).
// `boot` = extra script run before the page's own (readme_gif uses it to rewrite /api/state). Returns the page handle P.
export async function openApp(cdp, base, { name, lang, prefs, w, h, dsf, boot = '' }) {
  const { browserContextId } = await cdp.send('Target.createBrowserContext', { disposeOnDetach: true });
  const { targetId } = await cdp.send('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId: sid } = await cdp.send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => cdp.send(m, p, sid);
  const ev = async expr => {
    const r = await S('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(name + ': ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  };
  const P = {
    S, ev,
    wait: (expr, what) => until(() => ev(expr), 10000, name + '-' + lang + ' ' + what),
    css: async txt => {
      await ev(`(() => { const s = document.createElement('style'); s.textContent = ${JSON.stringify(txt)}; document.head.appendChild(s); dispatchEvent(new Event('resize')); return 1; })()`);
    },
    close: async () => {
      await cdp.send('Target.closeTarget', { targetId }).catch(() => {});
      await cdp.send('Target.disposeBrowserContext', { browserContextId }).catch(() => {});
    },
  };
  await Promise.all([S('Page.enable'), S('Runtime.enable')]);
  await S('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: dsf, mobile: false });
  const all = Object.assign({ mbLang: lang, mbTone: 'black' }, prefs || {});
  await S('Page.addScriptToEvaluateOnNewDocument', { source: `try{const P=${JSON.stringify(all)};let u=Object.assign({},P);`
    + `Object.defineProperty(window,'__UIP',{configurable:true,get(){return u;},set(v){u=Object.assign({},v||{},P);}});const f=window.fetch;`
    + `window.fetch=function(a,o){if(o&&o.method==='POST'&&String(a).indexOf('/api/ui-prefs')>=0)return Promise.resolve(new Response('{"ok":true}',{headers:{'Content-Type':'application/json'}}));`
    + `return f.apply(this,arguments);};}catch(e){}` });
  if (boot) await S('Page.addScriptToEvaluateOnNewDocument', { source: boot });
  // tour=0: no first-run tour · autobar=0: no automation banner.
  await S('Page.navigate', { url: base + '/?autobar=0&tour=0&nosave=1' });
  await P.wait(`document.readyState === 'complete' && document.querySelectorAll('#mvw .mvb').length > 0 && !!document.querySelector('#sbar') && document.querySelector('#sbar').innerText.trim().length > 0`, 'first render');
  return P;
}

// Backdrop frame page: neutral slate gradient, 16:10 inner box of iw x ih with rounded corners and a soft shadow.
// `inner` = the <img> or <div> that fills the box (readme_gif renders it as solid black and white to derive a mask).
export function frameHtml(fw, fh, iw, ih, inner) {
  return '<!doctype html><html><head><style>html,body{margin:0;width:' + fw + 'px;height:' + fh + 'px;overflow:hidden}'
    + 'body{display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#4a5366 0%,#2c3240 55%,#232833 100%)}'
    + '#s{width:' + iw + 'px;height:' + ih + 'px;display:block;border-radius:12px;'
    + 'box-shadow:0 0 0 1px rgba(255,255,255,.10),0 18px 40px rgba(0,0,0,.45),0 4px 12px rgba(0,0,0,.30)}'
    + '</style></head><body>' + inner + '</body></html>';
}
