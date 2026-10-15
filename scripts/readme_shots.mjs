#!/usr/bin/env node
// README / GUIDE screenshots from the synthetic `--demo` world, over CDP (Node 22 built-ins only, no packages).
// Same isolation as scripts/screen_check.mjs: own demo server on a free port, temp HOME/MAILBOX_DIR, headless Chrome
// with a temp profile. ⚠Never points at the live viewer (8799) — every pixel must come from demo data.
//
//   node scripts/readme_shots.mjs              write docs/images/<name>-<en|ko>.png for every shot
//   node scripts/readme_shots.mjs timeline     only the named shot(s)
//
// Each shot: app viewport 1200x750 (16:10) at deviceScaleFactor 2, then laid into a padded backdrop frame
// (rounded corners, soft shadow) on a second blank page and captured at 1600x1000 — all images share size and framing.
import fs from 'node:fs';
import path from 'node:path';
import { ROOT, sleep, sandbox, CDP, openApp, frameHtml } from './readme_cdp.mjs';

const OUT = path.join(ROOT, 'docs', 'images');
const VW = 1200, VH = 750;                  // app viewport, 16:10
const FW = 1280, FH = 800, FDSF = 1.25;     // frame page, 16:10 ⇒ output 1600x1000
const IW = 1152, IH = 720;                  // app image inside the frame, 16:10
const DEADLINE_MS = 180000;
const { cleanup, startDemo, startChrome } = sandbox('readme-shots');

// ---- shots -------------------------------------------------------------------
// Focus comes from picking the view and state.
const tab = k => `(() => { const b = document.querySelector('#mvw .mvb[data-mv="${k}"]'); if (!b) throw new Error('no tab ${k}'); b.click(); return 1; })()`;
const SHOTS = [
  { name: 'pipelines', async run(P) {
    // ⚠Feature tabs render only after the first /api/state, so wait for the button before clicking.
    await P.wait(`!!document.querySelector('#mvw .mvb[data-mv="pipe"]')`, 'pipe tab');
    await P.ev(tab('pipe'));
    await P.wait(`document.querySelectorAll('.plw .plcv .plnd').length >= 3 && !!document.querySelector('.plrtb')`, 'pipeline canvas');
    // Run overview + run bar + lit canvas + «By stage» table; the editor side panels and palette are not the subject.
    await P.css('.plchips,.plapply,.plnames,.plpal,.plpan,.plcvt,.plw>.tkvs{display:none!important}'
      + '.plw .plgw{height:260px!important;min-height:0!important}'
      + '.plgw>.plcvw{height:260px!important;max-height:260px!important;min-height:0!important}'
      + '.plw .plcv{flex:1 1 0!important;min-height:0!important;height:auto!important}');
  } },
  // tlnmW: the default name column (~290px at 1200px) truncates the row chips; the page clamps it to half the Gantt column.
  { name: 'timeline', prefs: { 'sidereus.tlgit': '1', 'sidereus.tlnmW': '400' }, async run(P) {
    await P.ev(tab('time'));
    await P.wait(`!!document.getElementById('tlgbm')`, 'changes rail');
    await P.ev(`(() => { const s = document.getElementById('tlgbm'); s.value = 'upstream'; s.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()`);
    await P.wait(`/↑\\d/.test((document.getElementById('tlgit') || {}).innerText || '')`, 'upstream ahead/behind badge');
    await P.css('#tldrw{display:none!important}');
  } },
  { name: 'structure', async run(P) {
    await P.ev(tab('struct'));
    await P.wait(`[...document.querySelectorAll('#feed text.mmdtx')].some(t => t.textContent.trim() === 'order')`, 'module map');
    // Select one module: the map keeps only its edges and the side panel lists them with evidence.
    await P.ev(`(() => { const t = [...document.querySelectorAll('#feed text.mmdtx')].find(t => t.textContent.trim() === 'order');
      t.closest('g.mmdn').dispatchEvent(new MouseEvent('click', {bubbles: true})); return 1; })()`);
  } },
  { name: 'branches', async run(P) {
    await P.ev(tab('br'));
    await P.wait(`document.body.innerText.indexOf('cart-rounding') >= 0 && document.querySelectorAll('#feed svg circle').length > 5`, 'branch graph');
  } },
  { name: 'tokens', async run(P) {
    await P.ev(tab('token'));
    await P.wait(`/1\\.6B/.test(document.getElementById('feed').innerText)`, 'token cards');
  } },
  // GUIDE.md only: the session drawer stays in its own shot.
  { name: 'sessions-drawer', async run(P) {
    await P.ev(tab('time'));
    await P.ev(`(document.getElementById('sesb').click(), 1)`);
    await P.wait(`document.getElementById('sesb').getAttribute('aria-expanded') === 'true'`, 'sessions drawer');
  } },
  // GUIDE.md only: the status-bar layer (per-account quota + open sessions) opened from the bottom bar.
  { name: 'status-layer', async run(P) {
    await P.ev(tab('time'));
    await P.wait(`!!document.getElementById('sbar') && typeof QLAST !== 'undefined' && !!(QLAST && QLAST.q)`, 'status bar quota');
    await P.ev(`(document.getElementById('sbar').click(), 1)`);
    await P.wait(`(() => { const p = document.getElementById('sblpop'); return !!(p && !p.hidden && p.querySelector('.sbl-acc.sbl-me')); })()`, 'status layer');
  } },
];

async function shoot(cdp, base, shot, lang) {
  const P = await openApp(cdp, base, { name: shot.name, lang, prefs: shot.prefs, w: VW, h: VH, dsf: 2 });
  const S = P.S;
  await shot.run(P);
  await sleep(1200);   // let resize re-fits, polls and fades settle
  const raw = (await S('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data;
  // Frame: same tab, blank document holding the capture.
  await S('Emulation.setDeviceMetricsOverride', { width: FW, height: FH, deviceScaleFactor: FDSF, mobile: false });
  await S('Page.navigate', { url: 'about:blank' });
  await sleep(200);
  const { frameTree } = await S('Page.getFrameTree');
  // Neutral slate backdrop, 16:10 inner image; padding is proportional so the frame stays 16:10 too.
  await S('Page.setDocumentContent', { frameId: frameTree.frame.id, html: frameHtml(FW, FH, IW, IH, '<img id=s src="data:image/png;base64,' + raw + '">') });
  await P.wait(`(() => { const i = document.getElementById('s'); return !!(i && i.complete && i.naturalWidth); })()`, 'frame image');
  const out = (await S('Page.captureScreenshot', { format: 'png' })).data;
  const file = path.join(OUT, shot.name + '-' + lang + '.png');
  fs.writeFileSync(file, Buffer.from(out, 'base64'));
  await P.close();
  return file;
}

async function main() {
  const want = process.argv.slice(2);
  const shots = want.length ? SHOTS.filter(s => want.includes(s.name)) : SHOTS;
  if (!shots.length) throw new Error('unknown shot; names: ' + SHOTS.map(s => s.name).join(', '));
  const timer = setTimeout(() => { console.error('readme_shots: exceeded ' + DEADLINE_MS / 1000 + 's'); cleanup(); process.exit(1); }, DEADLINE_MS);
  const [base, wsUrl] = await Promise.all([startDemo(), startChrome()]);
  const cdp = new CDP(wsUrl); await cdp.open();
  fs.mkdirSync(OUT, { recursive: true });
  for (const s of shots) for (const lang of ['en', 'ko']) {
    const f = await shoot(cdp, base, s, lang);
    console.log(path.relative(ROOT, f) + '  ' + Math.round(fs.statSync(f).size / 1024) + 'KB');
  }
  clearTimeout(timer);
  cdp.close();
  return 0;
}

main().then(code => { cleanup(); process.exit(code); }, e => { console.error('FAIL readme_shots: ' + (e && e.stack || e)); cleanup(); process.exit(1); });
