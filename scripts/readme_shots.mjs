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
// Exception: `crop` shots (pipeline-run, harness-flow) are one unframed panel cut from a 1440-wide page at 1x.
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
// Structure › Architecture, demo project's map loaded, then the named flow picked in «Flows» (lit on the map).
async function archFlow(P, name) {
  await P.wait(`!!document.querySelector('#mvw .mvb[data-mv="struct"]')`, 'struct tab');
  await P.ev(tab('struct'));
  await P.wait(`!!document.querySelector('.archtab select[data-arfl]')`, 'architecture map');
  await P.ev(`(() => { const s = document.querySelector('.archtab select[data-arfl]');
    const o = [...s.options].find(o => o.textContent.indexOf(${JSON.stringify(name)}) >= 0); if (!o) throw new Error('no flow ' + ${JSON.stringify(name)});
    s.value = o.value; s.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()`);
  await P.wait(`!!document.querySelector('.archtab [data-arseq]')`, 'flow lit');
}
// ⚠Accounts and pipeline runs arrive ~0.5s after first render, and a Timeline painted before that kept no account picker
// and no «Runs n» lane — so wait for the data before opening the tab, then for both on screen.
async function timeTab(P) {
  await P.wait(`typeof ACCTS !== 'undefined' && (ACCTS || []).length >= 2 && (SESS || []).some(x => x.plrun && x.plrun.length)`, 'accounts + runs data');
  await P.ev(tab('time'));
  await P.wait(`!!document.getElementById('acpk-time') && !!document.getElementById('tlplhb')`, 'timeline accounts + runs');
}
const SHOTS = [
  // tlnmW: the default name column (~290px at 1200px) truncates the row chips; the page clamps it to half the Gantt column.
  { name: 'timeline', prefs: { 'sidereus.tlgit': '1', 'sidereus.tlnmW': '400' }, async run(P) {
    await timeTab(P);
    await P.wait(`!!document.getElementById('tlgbm')`, 'changes rail');
    await P.ev(`(() => { const s = document.getElementById('tlgbm'); s.value = 'upstream'; s.dispatchEvent(new Event('change', {bubbles: true})); return 1; })()`);
    await P.wait(`/↑\\d/.test((document.getElementById('tlgit') || {}).innerText || '')`, 'upstream ahead/behind badge');
    await P.css('#tldrw{display:none!important}');
  } },
  // Architecture map with one flow lit (entry -> modules -> external), the flow list beside it and the minimap.
  // ⚠The layered map is ~920px tall: at zoom 1 the entry and PostgreSQL scroll off-screen, so shrink and drop the legend.
  { name: 'structure-arch', zoom: 0.62, async run(P) {
    await archFlow(P, 'Get an order');
    await P.css('.archtab .archleg,.archtab .archhint{display:none!important}');
    // Unfold the lit flow in the side list so its ordered steps show.
    await P.ev(`(() => { const b = [...document.querySelectorAll('.archtab button.archtnb[data-aet]')].find(b => b.textContent.indexOf('Get an order') >= 0);
      if (b && b.getAttribute('aria-expanded') !== 'true') b.click(); return 1; })()`);
    await P.wait(`[...document.querySelectorAll('.archtab button.archtnb[data-aet]')].some(b => b.textContent.indexOf('Get an order') >= 0 && b.getAttribute('aria-expanded') === 'true')`, 'flow unfolded');
    await sleep(300);
    await P.ev(`(document.querySelector('.archmap').scrollTop = 0, 1)`);
  } },
  // The same flow as a sequence diagram.
  { name: 'structure-flow', async run(P) {
    await archFlow(P, 'Pay for an order');
    await P.ev(`(document.querySelector('.archtab [data-arseq]').click(), 1)`);
    await P.wait(`!!document.querySelector('.archtab .archfdg')`, 'sequence diagram');
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
    await timeTab(P);
    await P.ev(`(document.getElementById('sesb').click(), 1)`);
    await P.wait(`document.getElementById('sesb').getAttribute('aria-expanded') === 'true'`, 'sessions drawer');
  } },
  // Pipelines: the demo change-flow run lit on the canvas (crop from the header to the «Running N» overview).
  { name: 'pipeline-run', crop: { from: '.plw', to: '.plw .plov' }, async run(P) {
    await P.ev(tab('pipe'));
    await P.wait(`!!document.querySelector('.plw .plcv .plcvi') && !!document.querySelector('.plw .plrunst.on') && !!document.querySelector('.plw .plov')`, 'lit run');
  } },
  // GUIDE.md only: «Tooling» › «Flow» strip (crop from the header to the seven boxes).
  { name: 'harness-flow', crop: { from: '.plw', to: '.plw .hnfrow' }, async run(P) {
    await P.ev(tab('pipe'));
    await P.wait(`!!document.querySelector('.wkrgb[data-plv="harness"]')`, 'Tooling toggle');
    await P.ev(`(document.querySelector('.wkrgb[data-plv="harness"]').click(), 1)`);
    await P.wait(`document.querySelectorAll('.plw .hnfrow .hnfn').length === 7`, 'flow strip');
  } },
  // GUIDE.md only: the status-bar layer (per-account quota + open sessions) opened from the bottom bar.
  { name: 'status-layer', async run(P) {
    await timeTab(P);
    await P.wait(`!!document.getElementById('sbar') && typeof QLAST !== 'undefined' && !!(QLAST && QLAST.q)`, 'status bar quota');
    await P.ev(`(document.getElementById('sbar').click(), 1)`);
    await P.wait(`(() => { const p = document.getElementById('sblpop'); return !!(p && !p.hidden && p.querySelector('.sbl-acc.sbl-me')); })()`, 'status layer');
  } },
];

// crop shots: one panel at the 1440 desktop width, 1x, no backdrop frame — `from` top/left/right to `to` bottom, PAD around.
const CW = 1440, CH = 1400, PAD = 8;
async function shootCrop(cdp, base, shot, lang) {
  const P = await openApp(cdp, base, { name: shot.name, lang, prefs: shot.prefs, w: CW, h: CH, dsf: 1 });
  await shot.run(P);
  await sleep(1200);
  const r = await P.ev(`(() => { const a = document.querySelector(${JSON.stringify(shot.crop.from)}).getBoundingClientRect(),
    b = document.querySelector(${JSON.stringify(shot.crop.to)}).getBoundingClientRect();
    return { x: a.left, y: a.top, w: a.width, h: b.bottom - a.top }; })()`);
  // ⚠a crop that runs past the viewport would capture blank rows; grow CH instead.
  if (r.y + r.h + PAD > CH) throw new Error(shot.name + ': crop taller than the viewport');
  const clip = { x: Math.max(0, Math.floor(r.x - PAD)), y: Math.max(0, Math.floor(r.y - PAD)), width: Math.ceil(r.w + 2 * PAD), height: Math.ceil(r.h + 2 * PAD), scale: 1 };
  const out = (await P.S('Page.captureScreenshot', { format: 'png', clip })).data;
  const file = path.join(OUT, shot.name + '-' + lang + '.png');
  fs.writeFileSync(file, Buffer.from(out, 'base64'));
  await P.close();
  return file;
}

async function shoot(cdp, base, shot, lang) {
  if (shot.crop) return shootCrop(cdp, base, shot, lang);
  // zoom < 1 = more CSS px in the same 2400x1500 capture (smaller text), for views taller than the viewport.
  const z = shot.zoom || 1;
  const P = await openApp(cdp, base, { name: shot.name, lang, prefs: shot.prefs, w: Math.round(VW / z), h: Math.round(VH / z), dsf: 2 * z });
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
